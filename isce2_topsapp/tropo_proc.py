import datetime
import subprocess
from pathlib import Path

import numpy as np
import xarray as xr
from jinja2 import Template

TEMPLATE_DIR = Path(__file__).parent/'templates'


def calculate_tropo_acq_delay(*,
                              acq_datetime: datetime.datetime,
                              orbit_path: str | Path,
                              weather_model_name: str,
                              bounding_box: list,
                              cube_spacing_in_m: float = 2_000,
                              output_epsg_number: int = 4326,
                              yml_name: str = 'run_raider') -> Path:

    with open(TEMPLATE_DIR/'raider_template.yml', 'r') as file:
        template = Template(file.read())

    xmin, ymin, xmax, ymax = bounding_box
    xmin = int(np.floor(xmin))
    ymin = int(np.floor(ymin))

    ymax = int(np.ceil(ymax))
    xmax = int(np.ceil(xmax))

    bounds_isce_str = f'{ymin} {ymax} {xmin} {xmax}'

    raider_yml = template.render(date=acq_datetime.strftime('%Y%m%d'),
                                 time=acq_datetime.strftime('%H:%M:%S'),
                                 weather_model_name=weather_model_name,
                                 bounding_box_str=bounds_isce_str,
                                 cube_spacing_in_m=cube_spacing_in_m,
                                 output_epsg_number=output_epsg_number,
                                 orbit_path=orbit_path
                                 )

    with open(f'{yml_name}.yml', "w") as file:
        file.write(raider_yml)

    cmd = 'raiderDelay.py run_raider.yml'
    result = subprocess.run(cmd,
                            shell=True)

    if result.returncode:
        raise ValueError('Raider failed; check logs and standard i/o')

    d = acq_datetime.strftime('%Y%m%d')
    t = acq_datetime.strftime('%H%M%S')
    out_nc = Path(f'{weather_model_name}_tropo_{d}T{t}_std.nc')

    if not out_nc.exists():
        raise ValueError(f'Expected netcdf was not generated for given inputs: {out_nc}')
    return out_nc


def compute_tropo_delay_for_insar_pair(*,
                                       ref_acq_datetime: datetime.datetime,
                                       sec_acq_datetime: datetime.datetime,
                                       ref_orbit_path: str | Path,
                                       sec_orbit_path: str | Path,
                                       weather_model_name: str,
                                       bounding_box: list,
                                       cube_spacing_in_m: float = 2_000,
                                       output_epsg_number: int = 4326) -> Path:

    ref_delay_cube_path = calculate_tropo_acq_delay(acq_datetime=ref_acq_datetime,
                                                    orbit_path=ref_orbit_path,
                                                    weather_model_name=weather_model_name,
                                                    bounding_box=bounding_box,
                                                    cube_spacing_in_m=cube_spacing_in_m,
                                                    output_epsg_number=output_epsg_number,
                                                    yml_name='reference_raider.yml'
                                                    )

    sec_delay_cube_path = calculate_tropo_acq_delay(acq_datetime=sec_acq_datetime,
                                                    orbit_path=sec_orbit_path,
                                                    weather_model_name=weather_model_name,
                                                    bounding_box=bounding_box,
                                                    cube_spacing_in_m=cube_spacing_in_m,
                                                    output_epsg_number=output_epsg_number,
                                                    yml_name='secondary_raider.yml'
                                                    )

    ds_ref = xr.open_dataset(ref_delay_cube_path, engine='rasterio')
    ds_sec = xr.open_dataset(sec_delay_cube_path, engine='rasterio')

    # Wavelenth of S1 in meters according to
    # https://sentinels.copernicus.eu/web/sentinel/technical-guides/sentinel-1-sar/sar-instrument
    lambda_s1 = .055465763
    ds_delay = (ds_ref - ds_sec) * (lambda_s1) / (4 * np.pi)
    out_path = 'tropo_delay.nc'
    ds_delay.to_netcdf(out_path)
    return out_path
