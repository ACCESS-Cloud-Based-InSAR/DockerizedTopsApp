from six.moves.urllib.parse import urlparse
from urllib3.util.retry import Retry
import requests
import re
from requests.adapters import HTTPAdapter
from lxml import html, etree
from pathlib import Path


ORBIT_TYPES = ['AUX_RESORB', 'AUX_POEORB']
PLATFORMS = ['S1A', 'S1B']


def get_asf_orbit_url(orbit_type: str,
                      platform: str,
                      timestamp: str) -> str:
    """Source:

    https://github.com/ASFHyP3/hyp3-lib/blob/develop/hyp3lib/get_orb.py

    Parameters
    ----------
    orbit_type : str
        Must be 'AUX_RESORB' or 'AUX_POEORB'
    platform : str
        Must be 'S1A' or 'S1B'
    timestamp : str
        Obtained from granule id e.g.
        `start_time, end_time = re.split('_+', GRANULE_ID)[4:6]`

    Returns
    -------
    str
        The url of said container
    """
    assert(orbit_type in ORBIT_TYPES)
    assert(platform in PLATFORMS)

    search_url = f'https://s1qc.asf.alaska.edu/{orbit_type.lower()}/'

    hostname = urlparse(search_url).hostname
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=10,
        status_forcelist=[429, 500, 503, 504],
    )
    session.mount(str(hostname), HTTPAdapter(max_retries=retries))
    response = session.get(search_url)
    response.raise_for_status()
    tree = html.fromstring(response.content)
    file_list = [file for file in tree.xpath('//a[@href]//@href')
                 if file.startswith(platform) and file.endswith('.EOF')]

    d1 = 0.
    best = None
    for file in file_list:
        file = file.strip()
        t = re.split('_', file.replace('T', '').replace('V', ''))
        if len(t) > 7:
            start = t[6]
            end = t[7].replace('.EOF', '')
            if start < timestamp < end:
                d = ((int(timestamp) - int(start))
                     + (int(end) - int(timestamp))) / 2
                if d > d1:
                    best = file
                    d1 = d

    if best is not None:
        return search_url + best

    return ''


def extract_metadata(scene_id: str) -> dict:
    """Source:

    https://github.com/ASFHyP3/hyp3-lib/blob/develop/hyp3lib/get_orb.py
    """
    start_time, end_time = re.split('_+', scene_id)[4:6]
    return {'platform': scene_id[:3],
            'start_time': start_time.replace('T', ''),
            'end_time': end_time.replace('T', '')}


def get_most_accurate_orbit_url(metadata: dict) -> str:
    orbit_url = (get_asf_orbit_url('AUX_POEORB',
                                   metadata['platform'],
                                   metadata['start_time']) or
                 get_asf_orbit_url('AUX_RESORB',
                                   metadata['platform'],
                                   metadata['start_time'])
                 )
    return orbit_url


def download_orbits(reference_scenes: list,
                    secondary_scenes: list,
                    orbit_directory: str = None,
                    dry_run: bool = False) -> dict:
    orbit_directory = orbit_directory or 'orbits'
    orbit_dir = Path(orbit_directory)
    orbit_dir.mkdir(exist_ok=True)

    ref_metadata = extract_metadata(reference_scenes[0])
    sec_metadata = extract_metadata(secondary_scenes[0])

    ref_orbit_url = get_most_accurate_orbit_url(ref_metadata)
    sec_orbit_url = get_most_accurate_orbit_url(sec_metadata)

    def download_one_orbit(orbit_url):

        orbit_path = orbit_dir/orbit_url.split('/')[-1]
        if not dry_run:
            resp = requests.get(orbit_url)
            orbit_data = resp.content
            etree.fromstring(orbit_data)
            with open(orbit_path, 'wb') as file:
                file.write(orbit_data)
        return orbit_path

    ref_orbit_path = download_one_orbit(ref_orbit_url)
    sec_orbit_path = download_one_orbit(sec_orbit_url)
    return {'ref_orbit': ref_orbit_path,
            'sec_orbit': sec_orbit_path
            }
