import os
import site
import subprocess
from pathlib import Path

from jinja2 import Template
from tqdm import tqdm

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

GEOCODE_LIST_BASE = ['merged/phsig.cor',
                     'merged/filt_topophase.unw',
                     'merged/los.rdr',
                     'merged/topophase.flat',
                     'merged/filt_topophase.flat',
                     'merged/filt_topophase_2stage.unw',
                     'merged/topophase.cor',
                     'merged/filt_topophase.unw.conncomp']


def topsapp_processing(*,
                       reference_slc_zips: list,
                       secondary_slc_zips: list,
                       orbit_directory: str,
                       extent: list,
                       dem_for_proc: str,
                       dem_for_geoc: str,
                       estimate_ionosphere_delay: bool,
                       swaths: list = None,
                       dry_run: bool = False,
                       do_esd: bool = False,
                       esd_coherence_threshold: float = .7,
                       output_resolution: int = 90,
                       do_dense_offsets: bool = False,
                       ampcor_window_size: int = 64):
    swaths = swaths or [1, 2, 3]
    # for [ymin, ymax, xmin, xmax]
    extent_isce = [extent[k] for k in [1, 3, 0, 2]]

    if output_resolution == 90:
        azimuth_looks = 7
        range_looks = 19
    elif output_resolution == 30:
        azimuth_looks = 3
        range_looks = 7
    else:
        raise ValueError('Output resolution must be "30" or "90"')

    # Update PATH with ISCE2 applications
    isce_application_path = Path(f'{site.getsitepackages()[0]}'
                                 '/isce/applications/')
    os.environ['PATH'] += (':' + str(isce_application_path))

    with open(TEMPLATE_DIR/'topsapp_template.xml', 'r') as file:
        template = Template(file.read())

    geocode_list = GEOCODE_LIST_BASE.copy()
    if estimate_ionosphere_delay:
        geocode_list.append('merged/topophase.ion')

    if do_dense_offsets:
        geocode_list.append('merged/dense_offsets.bil')

    topsApp_xml = template.render(orbit_directory=orbit_directory,
                                  output_reference_directory='reference',
                                  output_secondary_directory='secondary',
                                  ref_zip_file=reference_slc_zips,
                                  sec_zip_file=secondary_slc_zips,
                                  region_of_interest=extent_isce,
                                  demFilename=dem_for_proc,
                                  geocodeDemFilename=dem_for_geoc,
                                  filter_strength=.5,
                                  do_unwrap=True,
                                  use_virtual_files=True,
                                  do_esd=do_esd,
                                  esd_coherence_threshold=esd_coherence_threshold,
                                  estimate_ionosphere_delay=estimate_ionosphere_delay,
                                  azimuth_looks=azimuth_looks,
                                  range_looks=range_looks,
                                  swaths=swaths,
                                  geocode_list=geocode_list,
                                  do_dense_offsets=do_dense_offsets,
                                  ampcor_height=ampcor_window_size,
                                  ampcor_width=ampcor_window_size
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
