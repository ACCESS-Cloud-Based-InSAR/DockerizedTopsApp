from jinja2 import Template
import site
from tqdm import tqdm
import subprocess
from pathlib import Path
import os


TOPSAPP_STEPS = ['startup',
                 'preprocess',
                 'computeBaselines',
                 'verifyDEM',
                 'topo',
                 'subsetoverlaps',
                 'coarseoffsets',
                 'coarseresamp',
                 'overlapifg', 'prepesd',
                 'esd', 'rangecoreg',
                 'fineoffsets', 'fineresamp', 'ion',
                 'burstifg',
                 'mergebursts',
                 'filter', 'unwrap', 'unwrap2stage',
                 'geocode', 'denseoffsets',
                 'filteroffsets', 'geocodeoffsets']

TEMPLATE_DIR = Path(__file__).parent/'templates'


def topsapp_processing(*,
                       reference_slc_zips: list,
                       secondary_slc_zips: list,
                       orbit_directory: str,
                       extent: list,
                       dem_for_proc: str,
                       dem_for_geoc: str,
                       swaths: list = None,
                       dry_run: bool = False):
    swaths = swaths or [1, 2, 3]
    # for [ymin, ymax, xmin, xmax]
    extent_isce = [extent[k] for k in [1, 3, 0, 2]]

    # Update PATH with ISCE2 applications
    isce_application_path = Path(f'{site.getsitepackages()[0]}'
                                 '/isce/applications/')
    os.environ['PATH'] += (':' + str(isce_application_path))

    with open(TEMPLATE_DIR/'topsapp_template.xml', 'r') as file:
        template = Template(file.read())

    topsApp_xml = template.render(orbit_directory=orbit_directory,
                                  output_reference_directory='reference',
                                  output_secondary_directory='secondary',
                                  ref_zip_file=reference_slc_zips,
                                  sec_zip_file=secondary_slc_zips,
                                  region_of_interest=extent_isce,
                                  demFilename=dem_for_proc,
                                  geocodeDemFilename=dem_for_geoc,
                                  do_esd=False,
                                  filter_strength=.5,
                                  do_unwrap=True,
                                  use_virtual_files=True,
                                  esd_coherence_threshold=-1,
                                  azimuth_looks=7,
                                  range_looks=19,
                                  swaths=swaths
                                  )
    with open('topsApp.xml', "w") as file:
        file.write(topsApp_xml)

    tops_app_cmd = f'{isce_application_path}/topsApp.py'
    for step in tqdm(TOPSAPP_STEPS, desc='TopsApp Steps'):
        step_cmd = f'{tops_app_cmd} --dostep={step}'
        result = subprocess.run(step_cmd,
                                shell=True)
        if result.returncode != 0:
            raise ValueError(f'TopsApp failed at step: {step}')
        if dry_run and (step == 'topo'):
            break

    return result.returncode
