import io
import re
import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Tuple, Union

import pandas as pd
import requests
from shapely import geometry


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
            content = copy.deepcopy(elem.find('content'))
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
    payload = {
        'zip_url': burst_params.safe_url,
        'image_number': str(burst_params.image_number),
        'burst_number': str(burst_params.burst_number),
    }
    return {
        'url': urls[content],
        'params': payload,
    }


def download_metadata(
        asf_session: requests.Session,
        burst_params: BurstParams,
        out_file: Union[Path, str] = None) -> ET.Element:
    burst_request = create_burst_request(burst_params, content='metadata')
    burst_request['cookies'] = {'asf-urs':asf_session.cookies['asf-urs']}

    response = asf_session.get(**burst_request)
    response.raise_for_status()

    metadata = ET.fromstring(response.content)

    if out_file:
        ET.ElementTree(metadata).write(out_file, encoding='UTF-8', xml_declaration=True)

    return metadata


def download_geotiff(
        asf_session: requests.Session,
        burst_params: BurstParams,
        out_file: Union[Path, str]) -> str:
    burst_request = create_burst_request(burst_params, content='metadata')
    burst_request['cookies'] = {'asf-urs':asf_session.cookies['asf-urs']}

    for ii in range(1, 4):
        print(f'Download attempt #{ii}')
        response = asf_session.get(**burst_request)
        if (downloaded := response.ok):
            break

    if not downloaded:
        raise RuntimeError('Download failed three times')

    with open(out_file, 'wb') as f:
        f.write(response.content)

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


def spoof_safe(
        asf_session: requests.Session,
        burst: BurstMetadata,
        base_path: Path = Path('.'),
        download_strategy: str = 'single_burst') -> Path:
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
        burst_params = BurstParams(
            safe_url=burst.safe_url, image_number=burst.image_number, burst_number=burst.burst_number
        )
        download_geotiff(
            asf_session, burst_params, measurement_path / burst.measurement_name
        )
    elif download_strategy == 'surrounding_burst':
        n_bursts = len(burst.annotation.find('.//burstList'))
        names = {
            'burst_pre.tiff': burst.burst_number - 1,
            burst.measurement_name: burst.burst_number,
            'burst_post.tiff': burst.burst_number + 1,
        }
        names = {k: v for k, v in names.items() if 0 < v <= n_bursts}
        for n in names:
            burst_params = BurstParams(
                safe_url=burst.safe_url, image_number=burst.image_number, burst_number=names[n]
            )
            download_geotiff(asf_session, burst_params, measurement_path / n)
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
def get_region_of_interest(
        poly1: geometry.Polygon,
        poly2: geometry.Polygon,
        asc: bool = True) -> Tuple[float, float, float, float]:
    bbox1 = geometry.box(*poly1.bounds)
    bbox2 = geometry.box(*poly2.bounds)
    intersection = bbox1.intersection(bbox2)
    bounds = intersection.bounds

    x, y = (0, 1) if asc else (2, 1)
    roi = geometry.Point(bounds[x], bounds[y]).buffer(0.005)
    minx, miny, maxx, maxy = roi.bounds
    return minx, miny, maxx, maxy


def get_asf_session() -> requests.Session:
    # requests will automatically use the netrc file:
    # https://requests.readthedocs.io/en/latest/user/authentication/#netrc-authentication
    session = requests.Session()
    payload = {
        'response_type': 'code',
        'client_id': 'BO_n7nTIlMljdvU6kRRB3g',
        'redirect_uri': 'https://auth.asf.alaska.edu/login',
    }
    response = session.get('https://urs.earthdata.nasa.gov/oauth/authorize', params=payload)
    response.raise_for_status()
    return session


def download_bursts(param_list: Iterator[BurstParams]) -> List[BurstMetadata]:
    """Steps
    For each burst:
        1. Download metadata
        2. Create BurstMetadata object
        3. Create directory structure
        4. Write metadata
        5. Download and write geotiff
    """
    asf_session = get_asf_session()
    bursts = []
    for i, params in enumerate(param_list):
        print(f'Creating SAFE {i+1}...')
        manifest = download_manifest(params.safe_url)
        metadata = download_metadata(asf_session, params)
        burst = BurstMetadata(metadata, manifest, params)
        bursts.append(burst)
        spoof_safe(asf_session, burst, download_strategy='swath')

    print('SAFEs created!')

    return bursts
