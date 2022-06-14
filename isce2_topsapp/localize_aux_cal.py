import zipfile
from pathlib import Path
from typing import Union

import requests

S1A_AUX_URL = 'https://sar-mpc.eu/download/55282da1-679d-4ecf-aeef-d06b024451cf'
S1B_AUX_URL = 'https://sar-mpc.eu/download/3c8b7c8d-d3de-4381-a19d-7611fb8734b9'


def download_aux_cal(aux_cal_dir: Union[str, Path] = None):
    aux_cal_dir = aux_cal_dir or 'aux_cal'
    aux_cal_dir = Path(aux_cal_dir)
    aux_cal_dir.mkdir(exist_ok=True, parents=True)

    def download_one(url):
        resp = requests.get(url)
        file_name = url.split('/')[-1]
        out_path = aux_cal_dir/file_name

        with open(out_path, 'wb') as file:
            file.write(resp.content)
        return out_path

    s1a_path = download_one(S1A_AUX_URL)
    s1b_path = download_one(S1B_AUX_URL)

    with zipfile.ZipFile(s1a_path) as zip_file:
        zip_file.extractall(aux_cal_dir)
    with zipfile.ZipFile(s1b_path) as zip_file:
        zip_file.extractall(aux_cal_dir)

    return {'aux_cal_dir': str(aux_cal_dir)}
