import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests
from shapely import geometry

URL_BASE = 'https://datapool.asf.alaska.edu/SLC'


class BurstMetadata:
    def __init__(self, safe_url, image_number, burst_number, metadata):
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

        self.bounds = self.get_bounding_box()

    def reformat_gcp(self, point):
        attribs = ['line', 'pixel', 'latitude', 'longitude', 'height']
        values = {}
        for attrib in attribs:
            values[attrib] = float(point.find(attrib).text)
        return values

    def create_gcp_df(self, points):
        gcp_df = pd.DataFrame([self.reformat_gcp(x) for x in points])
        gcp_df = gcp_df.sort_values(['line', 'pixel']).reset_index(drop=True)
        return gcp_df

    def create_geometry(self, gcp_df, lines_per_burst):
        line_start = self.burst_number * lines_per_burst
        line_end = (self.burst_number + 1) * lines_per_burst
        first_line = gcp_df.loc[gcp_df['line'] == line_start, ['longitude', 'latitude']]
        second_line = gcp_df.loc[gcp_df['line'] == line_end, ['longitude', 'latitude']]

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

    def get_bounding_box(self):
        lines_per_burst = int(self.annotation.findtext('.//{*}linesPerBurst'))
        points = self.annotation.findall('.//{*}geolocationGridPoint')

        gcp_df = self.create_gcp_df(points)
        bounds = self.create_geometry(gcp_df, lines_per_burst)[1]
        return bounds


def create_burst_request(safe_url, image_number, burst_number, content):
    token = os.environ['EDL_TOKEN']
    urls = {
        'metadata': 'https://g6rmelgj3m.execute-api.us-west-2.amazonaws.com/metadata',
        'data': 'https://g6rmelgj3m.execute-api.us-west-2.amazonaws.com/geotiff',
    }

    url = urls[content]
    headers = {'Authorization': f'Bearer {token}'}
    params = {
        'zip_url': safe_url,
        'image_number': str(image_number),
        'burst_number': str(burst_number),
    }
    return {'url': url, 'headers': headers, 'params': params}


def download_metadata(safe_url, image_number, burst_number, out_file=None):
    request_params = create_burst_request(safe_url, image_number, burst_number, content='metadata')
    response = requests.get(**request_params)
    if not response.ok:
        raise (RuntimeError('Response is not OK'))
    metadata = ET.fromstring(response.content)
    if out_file:
        ET.ElementTree(metadata).write(out_file, encoding='UTF-8', xml_declaration=True)
    return BurstMetadata(metadata, safe_url, image_number, burst_number)


def download_manifest(safe_url, out_path):
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
    breakpoint()
    with open(out_path, 'wb') as f:
        f.write(manifest)

    return out_path


def spoof_safe(burst, base_path=Path('.')):
    """Creates this file structure:
    SLC.SAFE/
    ├── measurement/
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

    ET.ElementTree(burst.annotation).write(
        annotation_path / burst.annotation_name, encoding='UTF-8', xml_declaration=True
    )
    ET.ElementTree(burst.calibration).write(
        calibration_path / burst.calibration_name, encoding='UTF-8', xml_declaration=True
    )
    ET.ElementTree(burst.noise).write(calibration_path / burst.noise_name, encoding='UTF-8', xml_declaration=True)

    download_manifest(burst.safe_url, safe_path / 'manifest.safe')
    # ET.ElementTree(manifest).write(safe_path / 'manifest.safe', encoding='UTF-8', xml_declaration=True)

    return safe_path


def create_job_xml(reference_safe, secondary_safe, swath, polarization, bbox, do_esd, range_looks, azimuth_looks):
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
            <property name="do denseoffsets">True</property>
            <property name="do ESD">{do_esd}</property>
            <property name="do unwrap">True</property>
            <property name="unwrapper name">snaphu_mcf</property>
            <property name="geocode list">{geocode_list}</property>
        </component>
    </topsApp>
    '''
    return config


def prep_burst_job(reference_dict, secondary_dict, base_path):
    """Steps
    1. Download + parse metadata
    2. Create directory structure
    3. Extract and write metadata files
    4. (Optional) download manifest.safe(s)
    5. Download geotiffs
    6. Create and write job xml
    """
    return None


if __name__ == '__main__':
    url_ref = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.zip'
    url_sec = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200616T022252_20200616T022319_033036_03D3A3_5D11.zip'
    image_number = 1
    burst_number = 1
    metadata_path = Path(__file__).parent.parent.absolute() / 'tests' / 'test_data' / 'metadata.xml'
    xml = ET.parse(metadata_path).getroot()
    burst = BurstMetadata(url_ref, image_number, burst_number, xml)
    # burst = download_metadata(url_ref, image_number, burst_number)

    safe_path = spoof_safe(burst)
