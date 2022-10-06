import io
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Tuple, Union

import pandas as pd
import requests
from jinja2 import Template  # noqa
from shapely import geometry


URL_BASE = 'https://datapool.asf.alaska.edu/SLC'
TEMPLATE_DIR = Path(__file__).parent / 'templates'

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


@dataclass
class BurstParams:
    """Class that contains the parameters nessecary to request a burst from the API."""

    safe_url: str
    image_number: int
    burst_number: int


class BurstMetadata:
    def __init__(self, metadata: ET.Element, manifest: ET.Element, burst_params: BurstParams):
        self.safe_url = burst_params.safe_url
        self.image_number = burst_params.image_number
        self.burst_number = burst_params.burst_number
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
        pattern = f'^./measurement/s1.*{self.image_number}.tiff$'
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


def create_burst_request(burst_params: BurstParams, content: str) -> dict:
    urls = {
        'metadata': 'https://g6rmelgj3m.execute-api.us-west-2.amazonaws.com/metadata',
        'geotiff': 'https://g6rmelgj3m.execute-api.us-west-2.amazonaws.com/geotiff',
    }
    url = urls[content]

    cookie = os.environ['EDL_COOKIE']
    cookies = {'asf-urs': cookie}

    params = {
        'zip_url': burst_params.safe_url,
        'image_number': str(burst_params.image_number),
        'burst_number': str(burst_params.burst_number),
    }
    request_params = {
        'url': url,
        'cookies': cookies,
        'params': params,
    }
    return request_params


def download_metadata(burst_params: BurstParams, out_file: Union[Path, str] = None) -> ET.Element:
    request_params = create_burst_request(burst_params, content='metadata')
    with requests.get(**request_params) as r:
        if not r.ok:
            raise (RuntimeError('Response is not OK'))

        metadata = ET.fromstring(r.content)
        if out_file:
            ET.ElementTree(metadata).write(out_file, encoding='UTF-8', xml_declaration=True)

    return metadata


def download_geotiff(burst_params: BurstParams, out_file: Union[Path, str]) -> str:
    request_params = create_burst_request(burst_params, content='geotiff')

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

    return str(out_file)


def download_manifest(safe_url: str, out_file: Union[Path, str] = None) -> ET.Element:
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


def download_swath(safe_url: str, measurement_path: Path, measurement_name: str) -> str:
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

    return str(out_path)


def spoof_safe(burst: BurstMetadata, base_path: Path = Path('.'), download_strategy: str = 'single_burst') -> Path:
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
def get_region_of_interest(poly1: geometry.Polygon, poly2: geometry.Polygon, asc: bool = True) -> Tuple[float]:
    bbox1 = geometry.box(*poly1.bounds)
    bbox2 = geometry.box(*poly2.bounds)
    intersection = bbox1.intersection(bbox2)
    bounds = intersection.bounds

    x, y = (0, 1) if asc else (2, 1)
    roi = geometry.Point(bounds[x], bounds[y]).buffer(0.005)
    minx, miny, maxx, maxy = roi.bounds
    return (minx, miny, maxx, maxy)


def download_bursts(param_list: Iterator[BurstParams], base_path: Path = Path.cwd()) -> List[BurstMetadata]:
    """Steps
    For each burst:
        1. Download metadata
        2. Create BurstMetadata object
        3. Create directory structure
        4. Write metadata
        5. Download and write geotiff
    """
    bursts = []
    for i, params in enumerate(param_list):
        print(f'Creating SAFE {i+1}...')
        manifest = download_manifest(params.safe_url)
        metadata = download_metadata(params)
        burst = BurstMetadata(metadata, manifest, params)
        bursts.append(burst)
        spoof_safe(burst, download_strategy='swath')

    print('SAFEs created!')

    return bursts


def create_job_xml(
    reference_safe: str,
    secondary_safe: str,
    swath: int,
    polarization: str,
    bbox: Iterator[float],
    do_esd: bool,
    range_looks: int = 7,
    azimuth_looks: int = 3,
) -> ET.Element:
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
            <property name="range looks">{range_looks}</property>
            <property name="azimuth looks">{azimuth_looks}</property>
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


def prep_isce2_burst_job(ref_params: BurstParams, sec_params: BurstParams, base_path: Path = Path.cwd()) -> Path:
    """Steps
    1. Spoof SAFE for each burst
    2. Create and write job xml
    """
    ref_burst, sec_burst = download_bursts([ref_params, sec_params], base_path)

    asc = ref_burst.orbit_direction == 'ascending'
    roi = get_region_of_interest(ref_burst.footprint, sec_burst.footprint, asc)
    roi_isce = [roi[k] for k in [1, 3, 0, 2]]  # Expects SNWE

    # new way
    with open(TEMPLATE_DIR / 'topsapp_template.xml', 'r') as file:
        template = Template(file.read())

    topsApp_xml = template.render(
        orbit_directory='',
        output_reference_directory='reference',
        output_secondary_directory='secondary',
        ref_zip_file=ref_burst.safe_name,
        sec_zip_file=sec_burst.safe_name,
        region_of_interest=roi_isce,
        demFilename='',
        geocodeDemFilename='',
        do_esd=False,
        filter_strength=0.5,
        do_unwrap=True,
        use_virtual_files=True,
        esd_coherence_threshold=-1,
        azimuth_looks=4,
        range_looks=20,
        swaths=[ref_burst.swath],
    )
    with open(base_path / 'topsApp.xml', "w") as file:
        file.write(topsApp_xml)

    # # old way
    # job_xml = create_job_xml(
    #     ref_burst.safe_name,
    #     sec_burst.safe_name,
    #     ref_burst.swath,
    #     ref_burst.polarisation,
    #     [roi[k] for k in [1, 3, 0, 2]],  # Expects SNWE
    #     False,
    #     20,
    #     4,
    # )
    # ET.ElementTree(job_xml).write(base_path / 'topsApp.xml', encoding='UTF-8', xml_declaration=True)

    return base_path


if __name__ == '__main__':
    # Iran
    url_ref = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.zip'
    url_sec = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200616T022252_20200616T022319_033036_03D3A3_5D11.zip'
    image_number = 5
    burst_number = 8  # have to be careful with this, depends on ascending vs descending

    # # Greece
    # url_ref = f'{URL_BASE}/SA/S1B_IW_SLC__1SDV_20201115T162313_20201115T162340_024278_02E29D_5C54.zip'
    # url_sec = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20201203T162353_20201203T162420_035524_042744_6D5C.zip'
    # image_number = 5
    # burst_number = 1  # have to be careful with this, depends on ascending vs descending

    # ref_dict = {'url': url_ref, 'image_number': image_number, 'burst_number': burst_number}
    # sec_dict = {'url': url_sec, 'image_number': image_number, 'burst_number': burst_number}

    ref_params = BurstParams(
        safe_url=url_ref,
        image_number=image_number,
        burst_number=burst_number,
    )
    sec_params = BurstParams(
        safe_url=url_sec,
        image_number=image_number,
        burst_number=burst_number,
    )
    start = time.time()
    working_path = prep_isce2_burst_job(ref_params, sec_params)
    end = time.time()
    print(f'Took {end-start:.0f} seconds')
