from pathlib import Path
import requests
import tarfile

S1A_AUX_URL = 'https://qc.sentinel1.groupcls.com/product/S1A/AUX_CAL/2019/02/28/S1A_AUX_CAL_V20190228T092500_G20210104T141310.SAFE.TGZ'
S1B_AUX_URL = 'https://qc.sentinel1.groupcls.com/product/S1B/AUX_CAL/2019/05/14/S1B_AUX_CAL_V20190514T090000_G20210104T140612.SAFE.TGZ'


def download_aux_cal(aux_cal_dir: str = None):
    aux_cal_dir = aux_cal_dir or 'aux_cal'
    aux_cal_dir = Path(aux_cal_dir)
    aux_cal_dir.mkdir(exist_ok=True, parents=True)

    def download_one(url):
        resp = requests.get(S1A_AUX_URL)
        file_name = url.split('/')[-1]
        out_path = aux_cal_dir/file_name

        with open(out_path, 'wb') as file:
            file.write(resp.content)
        return out_path

    s1a_path = download_one(S1A_AUX_URL)
    s1b_path = download_one(S1B_AUX_URL)

    with tarfile.open(s1a_path) as tar:
        tar.extractall(path=aux_cal_dir)
    with tarfile.open(s1b_path) as tar:
        tar.extractall(path=aux_cal_dir)

    return {'aux_cal_dir': str(aux_cal_dir)}
