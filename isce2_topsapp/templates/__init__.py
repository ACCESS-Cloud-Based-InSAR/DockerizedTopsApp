import json
from pathlib import Path


def read_netcdf_packaging_template(product: str = 'GUNW') -> dict:
    data_dir = Path(__file__).parents[0].absolute()
    if product == 'GUNW':
        with (data_dir / 'nc_packaging_template_gunw.json').open() as f:
            data = json.load(f)
    elif product == 'COSEIS_SAR':
        with (data_dir / 'nc_packaging_template_coseis-sar.json').open() as f:
            data = json.load(f)
    return data
