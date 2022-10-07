import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
import requests
from shapely import geometry

from isce2_topsapp import localize_burst

URL_BASE = 'https://datapool.asf.alaska.edu/SLC'


@pytest.fixture()
def ref_metadata():
    metadata_path = Path(__file__).parent.absolute() / 'test_data' / 'ref_metadata.xml'
    xml = ET.parse(metadata_path).getroot()
    return xml


@pytest.fixture()
def ref_manifest():
    metadata_path = Path(__file__).parent.absolute() / 'test_data' / 'ref_manifest.xml'
    xml = ET.parse(metadata_path).getroot()
    return xml


@pytest.fixture()
def ref_burst(ref_metadata, ref_manifest):
    safe_url = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.zip'
    params = localize_burst.BurstParams(safe_url, 5, 8)
    burst = localize_burst.BurstMetadata(ref_metadata, ref_manifest, params)
    return burst


@pytest.fixture()
def sec_metadata():
    metadata_path = Path(__file__).parent.absolute() / 'test_data' / 'sec_metadata.xml'
    xml = ET.parse(metadata_path).getroot()
    return xml


@pytest.fixture()
def sec_manifest():
    metadata_path = Path(__file__).parent.absolute() / 'test_data' / 'sec_manifest.xml'
    xml = ET.parse(metadata_path).getroot()
    return xml


@pytest.fixture()
def sec_burst(sec_metadata, sec_manifest):
    safe_url = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200616T022252_20200616T022319_033036_03D3A3_5D11.zip'
    params = localize_burst.BurstParams(safe_url, 5, 8)
    burst = localize_burst.BurstMetadata(sec_metadata, sec_manifest, params)
    return burst


def test_create_gcp_df(ref_burst):
    n_bursts = int(ref_burst.annotation.findall('.//burstList')[0].attrib['count'])
    lines_per_burst = int(ref_burst.annotation.findtext('.//{*}linesPerBurst'))

    gcp_df = ref_burst.create_gcp_df()
    assert np.all(gcp_df.columns == ['line', 'pixel', 'latitude', 'longitude', 'height'])
    assert gcp_df.line.min() == 0
    assert gcp_df.line.max() == (n_bursts * lines_per_burst) - 1


def test_create_geometry(ref_burst):
    burst_number = 8
    real_box = (53.17067752190982, 27.51599975559423, 54.13361604403157, 27.83356711546872)

    gcp_df = ref_burst.create_gcp_df()
    box = ref_burst.create_geometry(gcp_df)[1]
    assert ref_burst.burst_number == burst_number
    assert np.all([np.isclose(a, b) for a, b in zip(box, real_box)])


# TODO figure out how to obtain OK response without downloading data
@pytest.mark.skip(reason='Can be slow, only run if you have time')
def test_burst_request():
    safe_url = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200616T022252_20200616T022319_033036_03D3A3_5D11.zip'
    params = localize_burst.BurstParams(safe_url, 5, 8)
    data_params, cookie_params = localize_burst.create_burst_request(params, content='metadata')

    with requests.Session() as session:
        cookie_response = session.get(**cookie_params)
        assert cookie_response.ok

        data_params['cookies']['asf-urs'] = session.cookies['asf-urs']
        data_response = session.get(**data_params)

        assert data_response.ok


# @pytest.mark.skip(reason='Can be slow, only run if you have time')
@pytest.mark.parametrize(
    'pattern',
    (
        '*SAFE',
        '*SAFE/annotation/*xml',
        '*SAFE/annotation/calibration/calibration*xml',
        '*SAFE/annotation/calibration/noise*xml',
    ),
)
def test_spoof_safe(ref_burst, tmpdir, mocker, pattern):
    tmpdir = Path(tmpdir)
    mocker.patch('isce2_topsapp.localize_burst.download_geotiff', return_value='')
    localize_burst.spoof_safe(requests.Session(), ref_burst, tmpdir)
    assert len(list(tmpdir.glob(pattern))) == 1


def test_get_region_of_interest(ref_burst, sec_burst, ref_metadata, ref_manifest):
    safe_url = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200616T022252_20200616T022319_033036_03D3A3_5D11.zip'
    burst_7 = localize_burst.BurstMetadata(
        ref_metadata,
        ref_manifest,
        localize_burst.BurstParams(safe_url, 5, 7),
    )
    burst_8 = localize_burst.BurstMetadata(
        ref_metadata,
        ref_manifest,
        localize_burst.BurstParams(safe_url, 5, 8),
    )
    burst_9 = localize_burst.BurstMetadata(
        ref_metadata,
        ref_manifest,
        localize_burst.BurstParams(safe_url, 5, 9),
    )
    asc = ref_burst.orbit_direction == 'ascending'
    roi = geometry.box(*localize_burst.get_region_of_interest(ref_burst.footprint, sec_burst.footprint, asc))

    assert roi.intersects(geometry.box(*burst_8.footprint.bounds))
    assert not roi.intersects(geometry.box(*burst_7.footprint.bounds))
    assert not roi.intersects(geometry.box(*burst_9.footprint.bounds))
