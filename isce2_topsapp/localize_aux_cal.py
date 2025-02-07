import zipfile
from io import BytesIO
from pathlib import Path
from typing import Union

import requests

S1A_AUX_URL = "https://sar-mpc.eu/files/S1A_AUX_CAL_20241128.zip"
S1B_AUX_URL = "https://sar-mpc.eu/files/S1B_AUX_CAL_20241128.zip"


def _download_platform(url: str, aux_cal_dir: Path):
    """Download and remove nested structure of the aux cal files

    Updated from Forrest Williams's code to handle the nested structure of the new aux cal files."""
    response = requests.get(url)
    response.raise_for_status()

    content = BytesIO(response.content)
    with zipfile.ZipFile(content) as zip_file:
        for zip_info in zip_file.infolist():
            # remove leading directories, i.e. extract S1A/AUX_CAL/2019/02/28/foo.SAFE/* to foo.SAFE/*
            if not zip_info.is_dir() and ".SAFE/" in zip_info.filename:
                zip_info.filename = "/".join(zip_info.filename.split("/")[5:])
                zip_file.extract(zip_info, aux_cal_dir)


def download_aux_cal(aux_cal_dir: Union[str, Path] = "aux_cal"):
    if not isinstance(aux_cal_dir, Path):
        aux_cal_dir = Path(aux_cal_dir)

    aux_cal_dir.mkdir(exist_ok=True, parents=True)
    for url in (S1A_AUX_URL, S1B_AUX_URL):
        _download_platform(url, aux_cal_dir)

    return {"aux_cal_dir": str(aux_cal_dir)}
