import shutil

import rasterio
from affine import Affine
from rasterio.crs import CRS
import xarray as xr
import numpy as np
from numpy.testing import assert_almost_equal

from isce2_topsapp.solid_earth_tides import update_gunw_with_solid_earth_tide, get_azimuth_time_array


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


def test_azimuth_time(isce_data_dir_for_set, gunw_path_for_set):
    group = 'science/grids/imagingGeometry'
    with xr.open_dataset(gunw_path_for_set, group=group) as ds:
        lon_res, lat_res = ds.rio.resolution()
        lat_res = -lat_res

        # Need upper left corner rather than pixel center
        hgt = ds.heightsMeta.data
        lat = ds.latitudeMeta.data + lat_res / 2.
        lon = ds.longitudeMeta.data - lon_res / 2.

    hgt_mesh, lat_mesh, lon_mesh = np.meshgrid(hgt, lat, lon, indexing='ij')
    # Azimuth time array
    X = get_azimuth_time_array(product_dir=isce_data_dir_for_set / 'reference',
                               height_mesh_arr=hgt_mesh,
                               latitude_mesh_arr=lat_mesh,
                               longitude_mesh_arr=lon_mesh)
    # Total seconds from minimum time
    Y = (X - X.min()) / np.timedelta64(1, 's')
    # Vertical standard deviation
    Y_std = Y.std(axis=0)
    assert_almost_equal(Y_std, 0, decimal=3)
