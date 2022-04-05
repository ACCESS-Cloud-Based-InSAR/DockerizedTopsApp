import warnings
from importlib.metadata import PackageNotFoundError, version

from isce2_topsapp.delivery_prep import prepare_for_delivery
from isce2_topsapp.localize_aux_cal import download_aux_cal
from isce2_topsapp.localize_dem import download_dem_for_isce2
from isce2_topsapp.localize_orbits import download_orbits
from isce2_topsapp.localize_slc import download_slcs
from isce2_topsapp.packaging import package_gunw_product
from isce2_topsapp.topsapp_proc import topsapp_processing


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
    'download_dem_for_isce2',
    'download_aux_cal',
    'topsapp_processing',
    'package_gunw_product',
    'prepare_for_delivery',
    '__version__',
]
