import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
import requests

from isce2_topsapp import burstio

# from unittest import mock


URL_BASE = 'https://datapool.asf.alaska.edu/SLC'

"""Request Format:
curl --get \
     --verbose \
     --data-urlencode "zip_url=https://datapool.asf.alaska.edu/SLC/SA/S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.zip" \
     --data-urlencode "image_number=1" \
     --data-urlencode "burst_number=1" \
     --header "Authorization: Bearer $EDL_TOKEN" \
     --location \
     --output metatdata.xml \
    https://g6rmelgj3m.execute-api.us-west-2.amazonaws.com/metadata
"""


@pytest.fixture(scope='module')
def metadata():
    metadata_path = Path(__file__).parent.absolute() / 'test_data' / 'metadata.xml'
    xml = ET.parse(metadata_path).getroot()
    return xml


@pytest.fixture(scope='module')
def burst_metadata(metadata):
    safe_url = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.zip'
    burst_metadata = burstio.BurstMetadata(safe_url, 1, 1, metadata)
    return burst_metadata


def test_create_gcp_df(burst_metadata):
    n_bursts = int(burst_metadata.annotation.findall('.//burstList')[0].attrib['count'])
    lines_per_burst = int(burst_metadata.annotation.findtext('.//{*}linesPerBurst'))
    points = burst_metadata.annotation.findall('.//{*}geolocationGridPoint')

    gcp_df = burst_metadata.create_gcp_df(points)
    assert np.all(gcp_df.columns == ['line', 'pixel', 'latitude', 'longitude', 'height'])
    assert gcp_df.line.min() == 0
    assert gcp_df.line.max() == (n_bursts * lines_per_burst) - 1


def test_create_geometry(burst_metadata):
    lines_per_burst = int(burst_metadata.annotation.findtext('.//{*}linesPerBurst'))
    points = burst_metadata.annotation.findall('.//{*}geolocationGridPoint')
    burst_number = 1
    real_box = (54.2590366824552, 28.43224815746974, 55.1845015633973, 28.74861632985042)

    gcp_df = burst_metadata.create_gcp_df(points)
    box = burst_metadata.create_geometry(gcp_df, lines_per_burst)[1]
    assert burst_metadata.burst_number == burst_number
    assert np.all([np.isclose(a, b) for a, b in zip(box, real_box)])


def test_create_job_xml():
    job_xml = burstio.create_job_xml('a.SAFE', 'b.SAFE', 2, 'vv', [0, 1, 2, 3], False, 3, 7)
    assert ET.fromstring(job_xml)


# TODO figure out how to obtain OK response without downloading data
@pytest.mark.skip(reason="api gateway is down")
def test_create_burst_request(burst_metadata):
    params = burst_metadata.create_burst_request(content='metadata')
    response = requests.get(**params)
    assert response.ok


@pytest.mark.parametrize(
    'pattern',
    (
        '*SAFE',
        '*SAFE/annotation/*xml',
        '*SAFE/annotation/calibration/calibration*xml',
        '*SAFE/annotation/calibration/noise*xml',
    ),
)
def test_spoof_safe(burst_metadata, tmpdir, pattern):
    tmpdir = Path(tmpdir)
    burstio.spoof_safe(burst_metadata, tmpdir)
    assert len(list(tmpdir.glob(pattern))) == 1


@pytest.mark.skip(reason="api gateway is down")
def test_prep_burst_job():
    base_path = Path('~/Data/tmp')
    url_ref = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.zip'
    url_sec = f'{URL_BASE}/SA/S1A_IW_SLC__1SDV_20200616T022252_20200616T022319_033036_03D3A3_5D11.zip'
    image_number = 1
    burst_number = 1
    ref_dict = {'safe_url': url_ref, 'image_number': image_number, 'burst_number': burst_number}
    sec_dict = {'safe_url': url_sec, 'image_number': image_number, 'burst_number': burst_number}

    burstio.prep_burst_job(ref_dict, sec_dict, base_path)
    ref_path = base_path / 'S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.SAFE'
    sec_path = base_path / 'S1A_IW_SLC__1SDV_20200616T022252_20200616T022319_033036_03D3A3_5D11.SAFE'

    assert (ref_path / 'manifest.safe').exists()
    assert (sec_path / 'manifest.safe').exists()
