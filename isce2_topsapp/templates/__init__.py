import json
from pathlib import Path


def read_netcdf_packaging_template():
    data_dir = Path(__file__).parents[0].absolute()
    data = json.load(open(data_dir/'nc_packaging_template.json', 'r'))
    return data
