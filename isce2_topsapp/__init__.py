import logging
import os
import warnings
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

# ----------------------------------------------------------------------------------------------------------------------
# Handling ISCE2 idiosyncrasies; At least the logging fix should be done BEFORE most other imports
# ----------------------------------------------------------------------------------------------------------------------
import isce   # noqa: F401
# This ensures all ISCE2 paths and environment variables are set when using this module, see:
# https://github.com/isce-framework/isce2/blob/main/__init__.py#L41-L50

# ISCE2 sets the root logger to DEBUG resulting in excessively verbose logging, see:
# https://github.com/isce-framework/isce2/issues/258
root_logger = logging.getLogger()
root_logger.setLevel('WARNING')

# ISCE2 also needs its applications to be on the system path, even though they say it's only "for convenience", see:
# https://github.com/isce-framework/isce2#setup-your-environment
ISCE_APPLICATIONS = str(Path(os.environ['ISCE_HOME']) / 'applications')
if ISCE_APPLICATIONS not in (PATH := os.environ['PATH'].split(os.pathsep)):
    os.environ['PATH'] = os.pathsep.join([ISCE_APPLICATIONS] + PATH)
# ----------------------------------------------------------------------------------------------------------------------

from isce2_topsapp.delivery_prep import prepare_for_delivery  # noqa: E402
from isce2_topsapp.localize_aux_cal import download_aux_cal  # noqa: E402
from isce2_topsapp.localize_burst import BurstParams, download_bursts, get_region_of_interest  # noqa: E402
from isce2_topsapp.localize_dem import download_dem_for_isce2  # noqa: E402
from isce2_topsapp.localize_mask import download_water_mask  # noqa: E402
from isce2_topsapp.localize_orbits import download_orbits  # noqa: E402
from isce2_topsapp.localize_slc import download_slcs, get_asf_slc_objects  # noqa: E402
from isce2_topsapp.packaging import package_gunw_product  # noqa: E402
from isce2_topsapp.topsapp_params import topsappParams  # noqa: E402
from isce2_topsapp.topsapp_proc import topsapp_processing  # noqa: E402


try:
    __version__ = version(__name__)
except PackageNotFoundError:
    __version__ = None
    warnings.warn('package is not installed!\n'
                  'Install in editable/develop mode via (from the top of this repo):\n'
                  '   python -m pip install -e .\n', RuntimeWarning)

__all__ = [
    'download_orbits',
    'download_slcs',
    'get_asf_slc_objects',
    'get_region_of_interest',
    'download_dem_for_isce2',
    'download_water_mask',
    'download_aux_cal',
    'download_bursts',
    'BurstParams',
    'topsapp_processing',
    'topsappParams',
    'package_gunw_product',
    'prepare_for_delivery',
    '__version__',
]
