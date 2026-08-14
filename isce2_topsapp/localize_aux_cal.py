import zipfile
from io import BytesIO
from pathlib import Path

import requests


S1A_AUX_URL = 'https://d3g9emy65n853h.cloudfront.net/AUX_CAL/S1A_AUX_CAL_20241128.zip'
S1B_AUX_URL = 'https://d3g9emy65n853h.cloudfront.net/AUX_CAL/S1B_AUX_CAL_20241128.zip'
# SAR-MPC API for satellites not yet bundled on the ASF CloudFront CDN
SAR_MPC_API_URL = "https://sar-mpc.eu/api/v1/"



def _download_platform(url: str, aux_cal_dir: Path) -> None:
    """Download and remove nested structure of the aux cal files.

    Updated from Forrest Williams's code to handle the nested structure of the new aux cal files.
    """
    response = requests.get(url)
    response.raise_for_status()

    content = BytesIO(response.content)
    with zipfile.ZipFile(content) as zip_file:
        for zip_info in zip_file.infolist():
            # remove leading directories, i.e. extract S1A/AUX_CAL/2019/02/28/foo.SAFE/* to foo.SAFE/*
            if not zip_info.is_dir() and '.SAFE/' in zip_info.filename:
                zip_info.filename = '/'.join(zip_info.filename.split('/')[5:])
                zip_file.extract(zip_info, aux_cal_dir)


def _download_platform_from_sar_mpc(mission: str, aux_cal_dir: Path):
    """Download all AUX_CAL files for a mission from the ESA SAR-MPC API.

    The ASF CloudFront bundles include all AUX_CAL versions (active + inactive)
    because ISCE2 selects the correct calibration file based on acquisition date.
    To be consistent, we download all entries from SAR-MPC, not just active ones.

    Each entry is a .SAFE.zip file. The zip contains files directly under
    <name>.SAFE/ (no additional nesting unlike the ASF bundles).
    """
    results = []
    page_url = SAR_MPC_API_URL
    params = {
        "product_type": "AUX_CAL",
        "sentinel1__mission": mission,
        "mode": "extended",
        "page_size": 100,
    }

    # Paginate through all results
    response = requests.get(page_url, params=params, timeout=120)
    response.raise_for_status()
    data = response.json()
    results.extend(data.get("results", []))
    while data.get("next"):
        response = requests.get(data["next"], timeout=120)
        response.raise_for_status()
        data = response.json()
        results.extend(data.get("results", []))

    if not results:
        print(f"No AUX_CAL files found for {mission} on SAR-MPC - skipping")
        return

    for entry in results:
        download_url = entry["remote_url"]
        product_name = entry["product_name"]

        # Skip if already extracted
        safe_dir = aux_cal_dir / f"{product_name}.SAFE"
        if safe_dir.exists():
            continue

        resp = requests.get(download_url, timeout=300)
        resp.raise_for_status()

        content = BytesIO(resp.content)
        with zipfile.ZipFile(content) as zip_file:
            for zip_info in zip_file.infolist():
                if not zip_info.is_dir() and ".SAFE/" in zip_info.filename:
                    # ESA zips are flat: <name>.SAFE/file - extract as-is
                    zip_file.extract(zip_info, aux_cal_dir)

    print(f"Downloaded {len(results)} AUX_CAL files for {mission} from SAR-MPC")


def download_aux_cal(aux_cal_dir: Union[str, Path] = "aux_cal"):
    if not isinstance(aux_cal_dir, Path):
        aux_cal_dir = Path(aux_cal_dir)

    aux_cal_dir.mkdir(exist_ok=True, parents=True)

    # S1A and S1B: use ASF CloudFront bundles as baseline (fast, single download)
    for url in (S1A_AUX_URL, S1B_AUX_URL):
        _download_platform(url, aux_cal_dir)

    # Supplement all missions from ESA SAR-MPC API.
    # - S1A/S1B: picks up any entries newer than the ASF bundle date
    # - S1C/S1D: primary source (no ASF bundle available yet)
    # The skip-if-exists check avoids re-downloading what the ASF bundle provided.
    for mission in ("S1A", "S1B", "S1C", "S1D"):
        try:
            _download_platform_from_sar_mpc(mission, aux_cal_dir)
        except Exception as e:
            print(f"Warning: could not download AUX_CAL for {mission}: {e}")

    return {"aux_cal_dir": str(aux_cal_dir)}
