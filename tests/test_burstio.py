import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
import requests

from isce2_topsapp import burstio


@pytest.fixture(scope='module')
def annotation():
    annotation_path = Path(__file__).parent.absolute() / 'test_data' / 'annotation.xml'
    annotation = ET.parse(annotation_path).getroot()
    return annotation


def test_create_gcp_df(annotation):
    n_bursts = int(annotation.findall('.//burstList')[0].attrib['count'])
    lines_per_burst = int(annotation.findtext('.//{*}linesPerBurst'))
    gcp_df = burstio.create_gcp_df(annotation)
    assert np.all(gcp_df.columns == ['line', 'pixel', 'latitude', 'longitude', 'height'])
    assert gcp_df.line.min() == 0
    assert gcp_df.line.max() == (n_bursts * lines_per_burst) - 1


@pytest.mark.parametrize(
    'index, real_box',
    [
        (0, (53.39892830515005, 28.68119969132844, 54.3716989017821, 28.99795274730827)),
        (8, (53.17067752190982, 27.51599975559423, 54.09849123017585, 27.66669346258735)),
    ],
)
def test_create_geometry(index, real_box, annotation):
    lines_per_burst = int(annotation.findtext('.//{*}linesPerBurst'))
    gcp_df = burstio.create_gcp_df(annotation)
    box = burstio.create_geometry(gcp_df, index, lines_per_burst)[1]
    assert np.all([np.isclose(a, b) for a, b in zip(box, real_box)])


def test_create_job_xml():
    job_xml = burstio.create_job_xml('a.SAFE', 'b.SAFE', 2, 'vv', [0, 1, 2, 3], False, 3, 7)
    assert ET.fromstring(job_xml)


def test_generate_burst_request():
    safe_url = (
        "https://datapool.asf.alaska.edu/SLC/SA/S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.zip"
    )
    image_number = 2
    burst_number = 3
    params = burstio.generate_burst_request(safe_url, image_number, burst_number, 'metadata')
    response = requests.head(**params)
    assert response.ok
