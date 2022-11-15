import datetime
import subprocess
from pathlib import Path

import numpy as np
from jinja2 import Template

TEMPLATE_DIR = Path(__file__).parent/'templates'


def tropo_processing(*,
                     acq_datetime: datetime.datetime,
                     weather_model_name: str,
                     bounding_box: list,
                     orbit_path: str | Path,
                     cube_spacing_in_m: float = 2_000,
                     output_epsg_number: int = 4326) -> Path:

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

    with open('run_raider.yml', "w") as file:
        file.write(raider_yml)

    cmd = 'raiderDelay.py run_raider.yml'
    result = subprocess.run(cmd,
                            shell=True)

    if result.returncode:
        raise ValueError('Raider failed; check logs and standard i/o')

    d = acq_datetime.strftime('%Y%m%d')
    t = acq_datetime.strftime('%H:%M:%S')
    out_nc = Path(f'{weather_model_name}_tropo_{d}T{t}_std.nc')

    if not out_nc.exists():
        raise ValueError(f'Expected netcdf was not generated for given inputs: {out_nc}')
    return out_nc
