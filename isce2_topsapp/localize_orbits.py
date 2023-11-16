import os
from pathlib import Path

import requests
from hyp3lib import get_orb


def _spoof_orbit_download(
    scene, _, providers=('ESA', 'ASF'), orbit_types=('AUX_POEORB', 'AUX_RESORB'), esa_credentials=('name', 'password')
):
    for orbit_type in orbit_types:
        for provider in providers:
            try:
                orbit_url = get_orb.get_orbit_url(scene, orbit_type=orbit_type, provider=provider)
            except requests.RequestException:
                continue

            if orbit_url is not None:
                return orbit_url, None
    return None, None


def download_orbits(
    reference_scenes: list, secondary_scenes: list, orbit_directory: str = None, dry_run: bool = False
) -> dict:
    esa_credentials = (os.environ['ESA_USERNAME'], os.environ['ESA_PASSWORD'])

    orbit_directory = orbit_directory or 'orbits'
    orbit_dir = Path(orbit_directory)
    orbit_dir.mkdir(exist_ok=True)

    orbit_fetcher = _spoof_orbit_download if dry_run else get_orb.downloadSentinelOrbitFile

    reference_orbits = []
    for scene in reference_scenes:
        orbit_file, _ = orbit_fetcher(scene, str(orbit_dir), esa_credentials=esa_credentials)
        reference_orbits.append(orbit_file)

    secondary_orbits = []
    for scene in secondary_scenes:
        orbit_file, _ = orbit_fetcher(scene, str(orbit_dir), esa_credentials=esa_credentials)
        secondary_orbits.append(orbit_file)

    reference_orbits = list(set(reference_orbits))
    secondary_orbits = list(set(secondary_orbits))

    return {
        'orbit_directory': orbit_directory,
        'reference_orbits': reference_orbits,
        'secondary_orbits': secondary_orbits,
    }
