import shutil

import rasterio
from affine import Affine
from rasterio.crs import CRS

from isce2_topsapp.solid_earth_tides import update_gunw_with_solid_earth_tide


def test_set_workflow(isce_data_dir_for_set,
                      gunw_path_for_set,
                      tmp_path):
    tmp_gunw = tmp_path / 'temp.nc'
    shutil.copy(gunw_path_for_set, tmp_gunw)

    update_gunw_with_solid_earth_tide(tmp_gunw, 'reference', isce_data_dir_for_set)
    # update_gunw_with_solid_earth_tide(tmp_gunw, 'secondary', isce_data_dir_for_set)

    for acq_type in ['reference']:  # , 'secondary']:
        group = f'/science/grids/corrections/external/tides/solidEarth/{acq_type}'
        variable = 'solidEarthTide'
        with rasterio.open(f'netcdf:{tmp_gunw}:{group}/{variable}') as ds:
            # Check nodata and CRS
            assert ds.nodata == 0
            assert ds.crs == CRS.from_epsg(4326)

            # Transform should not be the identity
            t = ds.transform
            assert t != Affine(1, 0, 0, 0, 1, 0)
