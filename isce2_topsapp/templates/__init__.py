import json
from pathlib import Path


def read_netcdf_packaging_template(product="GUNW"):
    data_dir = Path(__file__).parents[0].absolute()
    if product == "GUNW":
        data = json.load(open(data_dir / "nc_packaging_template_gunw.json", "r"))
    elif product == "COSEIS_SAR":
        data = json.load(open(data_dir / "nc_packaging_template_coseis-sar.json", "r"))
    return data
