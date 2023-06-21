import shutil

import numpy as np
import rasterio
import xarray as xr
from affine import Affine
from numpy.testing import assert_almost_equal
from rasterio.crs import CRS

from isce2_topsapp.solid_earth_tides import (get_azimuth_time_array,
                                             get_start_time_from_slc_id,
                                             update_gunw_with_solid_earth_tide)


def test_set_workflow(orbit_files_for_set,
                      gunw_path_for_set,
                      tmp_path):
    tmp_gunw = tmp_path / 'temp.nc'
    shutil.copy(gunw_path_for_set, tmp_gunw)

    update_gunw_with_solid_earth_tide(tmp_gunw, 'reference', [orbit_files_for_set['reference']])
    update_gunw_with_solid_earth_tide(tmp_gunw, 'secondary', [orbit_files_for_set['secondary']])

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


def test_azimuth_time(orbit_files_for_set, gunw_path_for_set):
    """Ensures deviation of retrieved azimuth time array is within 1e-3 seconds"""
    group = 'science/grids/imagingGeometry'
    with xr.open_dataset(gunw_path_for_set, group=group) as ds:
        lon_res, lat_res = ds.rio.resolution()
        lat_res = -lat_res

        # Need upper left corner rather than pixel center
        hgt = ds.heightsMeta.data
        lat = ds.latitudeMeta.data + lat_res / 2.
        lon = ds.longitudeMeta.data - lon_res / 2.

    # Uses secondary image
    group = 'science/radarMetaData/inputSLC'
    with xr.open_dataset(gunw_path_for_set, group=f'{group}/secondary') as ds:
        slc_ids = ds['L1InputGranules'].data
        # Ensure non-empty and sorted by acq_time
        slc_ids = sorted(list(filter(lambda x: x, slc_ids)))
        slc_start_time = get_start_time_from_slc_id(slc_ids[0])

    hgt_mesh, lat_mesh, lon_mesh = np.meshgrid(hgt, lat, lon, indexing='ij')
    # Azimuth time array
    X = get_azimuth_time_array(orbit_xmls=[orbit_files_for_set['reference']],
                               slc_start_time=slc_start_time,
                               height_mesh_arr=hgt_mesh,
                               latitude_mesh_arr=lat_mesh,
                               longitude_mesh_arr=lon_mesh)
    # Total seconds from minimum time
    Y = (X - X.min()) / np.timedelta64(1, 's')
    # Vertical standard deviation
    Y_std = Y.std(axis=0)
    assert_almost_equal(Y_std, 0, decimal=3)
