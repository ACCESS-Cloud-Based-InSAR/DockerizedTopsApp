import io
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely import geometry

URL_BASE = 'https://datapool.asf.alaska.edu/SLC'

"""Request Format:
curl --get \
     --data-urlencode "zip_url=https://datapool.asf.alaska.edu/SLC/SA/S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.zip" \
     --data-urlencode "image_number=5" \
     --data-urlencode "burst_number=1" \
     --header "Authorization: Bearer $EDL_TOKEN" \
     --location \
     --output tmp.tif \
    https://g6rmelgj3m.execute-api.us-west-2.amazonaws.com/geotiff && gdalinfo tmp.tif
"""


class BurstMetadata:
    def __init__(self, metadata, manifest, safe_url, image_number, burst_number):
        self.safe_url = safe_url
        self.image_number = image_number
        self.burst_number = burst_number
        self.safe_name = Path(self.safe_url).with_suffix('.SAFE').name

        image_numbers = [int(x.attrib['source_filename'].split('-')[-1][2]) for x in metadata]
        products = [x.tag for x in metadata]
        combos = list(zip(image_numbers, products))

        files = {'product': 'annotation', 'calibration': 'calibration', 'noise': 'noise'}
        for name in files:
            elem = metadata[combos.index((self.image_number, name))]
            content = elem.find('content')
            content.tag = 'product'
            setattr(self, files[name], content)
            setattr(self, f'{files[name]}_name', elem.attrib['source_filename'])

        self.manifest = manifest
        self.manifest_name = 'manifest.safe'

        file_paths = [x.attrib['href'] for x in manifest.findall('.//fileLocation')]
        pattern = f'^./measurement/s1.*{image_number}.tiff$'
        self.measurement_name = [Path(x).name for x in file_paths if re.search(pattern, x)][0]

        self.gcp_df = self.create_gcp_df()
        self.footprint = self.create_geometry(self.gcp_df)[0]
        self.swath = int(self.annotation.findtext('.//{*}adsHeader/swath')[2])
        self.polarisation = self.annotation.findtext('.//{*}adsHeader/polarisation')
        self.orbit_direction = self.manifest.findtext('.//{*}pass').lower()

    @staticmethod
    def reformat_gcp(point):
        attribs = ['line', 'pixel', 'latitude', 'longitude', 'height']
        values = {}
        for attrib in attribs:
            values[attrib] = float(point.find(attrib).text)
        return values

    def create_gcp_df(self):
        points = self.annotation.findall('.//{*}geolocationGridPoint')
        gcp_df = pd.DataFrame([self.reformat_gcp(x) for x in points])
        gcp_df = gcp_df.sort_values(['line', 'pixel']).reset_index(drop=True)
        return gcp_df

    def create_geometry(self, gcp_df):
        burst_index = self.burst_number - 1
        lines = int(self.annotation.findtext('.//{*}linesPerBurst'))
        first_line = gcp_df.loc[gcp_df['line'] == burst_index * lines, ['longitude', 'latitude']]
        second_line = gcp_df.loc[gcp_df['line'] == (burst_index + 1) * lines, ['longitude', 'latitude']]
        x1 = first_line['longitude'].tolist()
        y1 = first_line['latitude'].tolist()
        x2 = second_line['longitude'].tolist()
        y2 = second_line['latitude'].tolist()
        x2.reverse()
        y2.reverse()
        x = x1 + x2
        y = y1 + y2
        footprint = geometry.Polygon(zip(x, y))
        centroid = tuple([x[0] for x in footprint.centroid.xy])
        return footprint, footprint.bounds, centroid


def create_burst_request(safe_url, image_number, burst_number, content):
    urls = {
        'metadata': 'https://g6rmelgj3m.execute-api.us-west-2.amazonaws.com/metadata',
        'geotiff': 'https://g6rmelgj3m.execute-api.us-west-2.amazonaws.com/geotiff',
    }
    url = urls[content]

    # token = os.environ['EDL_TOKEN']
    # headers = {'Authorization': f'Bearer {token}'}

    cookie = os.environ['EDL_COOKIE']
    cookies = {'asf-urs': cookie}

    params = {
        'zip_url': safe_url,
        'image_number': str(image_number),
        'burst_number': str(burst_number),
    }
    request_params = {
        'url': url,
        # 'headers': headers,
        'cookies': cookies,
        'params': params,
    }
    return request_params


def download_metadata(safe_url, image_number, burst_number, out_file=None):
    request_params = create_burst_request(safe_url, image_number, burst_number, content='metadata')
    with requests.get(**request_params) as r:
        if not r.ok:
            raise (RuntimeError('Response is not OK'))

        metadata = ET.fromstring(r.content)
        if out_file:
            ET.ElementTree(metadata).write(out_file, encoding='UTF-8', xml_declaration=True)

    return metadata


def download_geotiff(safe_url, image_number, burst_number, out_file):
    request_params = create_burst_request(safe_url, image_number, burst_number, content='geotiff')

    i = 1
    downloaded = False
    while (not downloaded) & (i <= 4):
        print(f'Download attempt #{i}')
        r = requests.get(**request_params)
        downloaded = r.ok
        i += 1

    if not downloaded:
        raise (RuntimeError('Download failed three times'))

    with open(out_file, 'wb') as f:
        f.write(r.content)

    return out_file


def download_manifest(safe_url, out_file=None):
    import netrc

    import aiohttp
    import fsspec

    safe_name = Path(safe_url).with_suffix('.SAFE').name

    my_netrc = netrc.netrc()
    username, _, password = my_netrc.authenticators('urs.earthdata.nasa.gov')
    auth = aiohttp.BasicAuth(username, password)
    storage_options = {'client_kwargs': {'trust_env': True, 'auth': auth}}

    http_fs = fsspec.filesystem('https', **storage_options)
    with http_fs.open(safe_url) as fo:
        safe_zip = fsspec.filesystem('zip', fo=fo)
        with safe_zip.open(str(Path(safe_name) / 'manifest.safe')) as f:
            manifest = f.read()

    if out_file:
        with open(out_file, 'wb') as f:
            f.write(manifest)

    manifest = ET.parse(io.BytesIO(manifest)).getroot()
    return manifest


def download_swath(safe_url, measurement_path, measurement_name):
    import netrc

    import aiohttp
    import fsspec

    safe_name = Path(safe_url).with_suffix('.SAFE').name
    swath_path = safe_name / Path('measurement') / measurement_name
    out_path = measurement_path / measurement_name

    my_netrc = netrc.netrc()
    username, _, password = my_netrc.authenticators('urs.earthdata.nasa.gov')
    auth = aiohttp.BasicAuth(username, password)
    storage_options = {'client_kwargs': {'trust_env': True, 'auth': auth}}

    http_fs = fsspec.filesystem('https', **storage_options)
    with http_fs.open(safe_url) as fo:
        safe_zip = fsspec.filesystem('zip', fo=fo)
        with safe_zip.open(str(swath_path)) as f:
            swath = f.read()

    with open(out_path, 'wb') as f:
        f.write(swath)

    return out_path


def spoof_safe(burst, base_path=Path('.'), download_strategy='single_burst'):
    """Creates this file structure:
    SLC.SAFE/
    ├── manifest.safe
    ├── measurement/
    │   └── burst.tif
    └── annotation/
        ├── annotation.xml
        └── calbiration/
            ├── calibration.xml
            └── noise.xml
    """
    safe_path = base_path / burst.safe_name
    annotation_path = safe_path / 'annotation'
    calibration_path = safe_path / 'annotation' / 'calibration'
    measurement_path = safe_path / 'measurement'
    paths = [annotation_path, calibration_path, measurement_path]
    for p in paths:
        if not p.exists():
            p.mkdir(parents=True)

    et_args = {'encoding': 'UTF-8', 'xml_declaration': True}

    ET.ElementTree(burst.annotation).write(annotation_path / burst.annotation_name, **et_args)
    ET.ElementTree(burst.calibration).write(calibration_path / burst.calibration_name, **et_args)
    ET.ElementTree(burst.noise).write(calibration_path / burst.noise_name, **et_args)
    ET.ElementTree(burst.manifest).write(safe_path / 'manifest.safe', **et_args)

    if download_strategy == 'single_burst':
        download_geotiff(
            burst.safe_url, burst.image_number, burst.burst_number, measurement_path / burst.measurement_name
        )
    elif download_strategy == 'surrounding_burst':
        n_bursts = len(burst.annotation.find('.//burstList'))
        names = {
            'burst_pre.tiff': burst.burst_number - 1,
            burst.measurement_name: burst.burst_number,
            'burst_post.tiff': burst.burst_number + 1,
        }
        names = {k: v for k, v in names.items() if (v > 0) & (v <= n_bursts)}
        for n in names:
            download_geotiff(burst.safe_url, burst.image_number, names[n], measurement_path / n)
    elif download_strategy == 'swath':
        download_swath(
            burst.safe_url,
            measurement_path,
            burst.measurement_name,
        )
    else:
        raise NotImplementedError(f'Download strategy {download_strategy} is not implemented, check spelling.')

    return safe_path


# TODO currently only validated for descending orbits
def get_region_of_interest(poly1, poly2, asc=True):
    bbox1 = geometry.box(*poly1.bounds)
    bbox2 = geometry.box(*poly2.bounds)
    intersection = bbox1.intersection(bbox2)
    bounds = intersection.bounds

    x, y = (0, 1) if asc else (2, 1)
    roi = geometry.Point(bounds[x], bounds[y]).buffer(0.005)
    return roi


def prep_isce2_burst_job(reference_dict, secondary_dict, base_path=Path.cwd()):
    """Steps
    For each burst:
        1. Download metadata
        2. Create BurstMetadata object
        3. Create directory structure
        4. Write metadata
        5. Download and write geotiff
    6. Create and write job xml
    """
    bursts = []
    for i, params in enumerate([reference_dict, secondary_dict]):
        print(f'Creating SAFE {i+1}...')
        manifest = download_manifest(params['url'])
        metadata = download_metadata(params['url'], params['image_number'], params['burst_number'])
        burst = BurstMetadata(metadata, manifest, params['url'], params['image_number'], params['burst_number'])
        bursts.append(burst)
        spoof_safe(burst, download_strategy='swath')

    print('SAFEs created!')
    asc = bursts[0].orbit_direction == 'ascending'
    roi = get_region_of_interest(bursts[0].footprint, bursts[0].footprint, asc)
    minx, miny, maxx, maxy = roi.bounds

    gdf = gpd.GeoDataFrame(
        data=pd.DataFrame({'component': ['reference', 'secondary', 'roi']}),
        geometry=[bursts[0].footprint, bursts[1].footprint, roi],
        crs='EPSG:4326',
    )
    gdf.to_file('geometries.geojson')

    # topsApp expects bbox to be in order [S, N, W, E]
    job_xml = create_job_xml(
        bursts[0].safe_name,
        bursts[1].safe_name,
        bursts[0].swath,
        bursts[0].polarisation,
        (miny, maxy, minx, maxx),
        False,
        7,
        3,
    )

    ET.ElementTree(job_xml).write(base_path / 'topsApp.xml', encoding='UTF-8', xml_declaration=True)

    return base_path


def create_job_xml(reference_safe, secondary_safe, swath, polarization, bbox, do_esd, range_looks, azimuth_looks):
    bbox = list(bbox)
    geocode_list = [
        'merged/phsig.cor',
        'merged/filt_topophase.unw',
        'merged/los.rdr',
        'merged/topophase.flat',
        'merged/filt_topophase.flat',
        'merged/topophase.cor',
        'merged/filt_topophase.unw.conncomp',
    ]

    config = f'''<?xml version="1.0" encoding="UTF-8"?>
    <topsApp>
        <component name="topsinsar">
            <property name="Sensor name">SENTINEL1</property>
            <component name="reference">
                <property name="output directory">reference</property>
                <property name="polarization">'{polarization.lower()}'</property>
                <property name="safe">{reference_safe}</property>
            </component>
            <component name="secondary">
                <property name="output directory">secondary</property>
                <property name="polarization">'{polarization.lower()}'</property>
                <property name="safe">{secondary_safe}</property>
            </component>
            <property name="swaths">[{swath}]</property>
            <property name="range looks">7</property>
            <property name="azimuth looks">3</property>
            <property name="region of interest">{bbox}</property>
            <property name="do denseoffsets">False</property>
            <property name="do ESD">{do_esd}</property>
            <property name="do unwrap">True</property>
            <property name="unwrapper name">snaphu_mcf</property>
            <property name="geocode list">{geocode_list}</property>
        </component>
    </topsApp>
    '''
    return ET.fromstring(config)


if __name__ == '__main__':
    url_ref = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.zip'
    url_sec = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200616T022252_20200616T022319_033036_03D3A3_5D11.zip'
    image_number = 5  # for Iran
    burst_number = 8  # have to be careful with this, depends on ascending vs descending (should be 8 for Iran)
    ref_dict = {'url': url_ref, 'image_number': image_number, 'burst_number': burst_number}
    sec_dict = {'url': url_sec, 'image_number': image_number, 'burst_number': burst_number}
    start = time.time()
    working_path = prep_isce2_burst_job(ref_dict, sec_dict)
    end = time.time()
    print(f'Took {end-start:.0f} seconds')
