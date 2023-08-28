import datetime
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pysolid
import pytest
import rasterio
import xarray as xr
from affine import Affine
from numpy.testing import assert_almost_equal
from rasterio.crs import CRS

from isce2_topsapp.solid_earth_tides import (get_azimuth_time_array,
                                             get_start_time_from_slc_id,
                                             update_gunw_with_solid_earth_tide)


def test_set_workflow(orbit_files_for_set,
                      gunw_paths_for_set,
                      tmp_path):
    for gunw_path_for_set, orbit_dict in zip(gunw_paths_for_set, orbit_files_for_set):
        tmp_gunw = tmp_path / 'temp.nc'
        shutil.copy(gunw_path_for_set, tmp_gunw)

        update_gunw_with_solid_earth_tide(tmp_gunw, 'reference', [orbit_dict['reference']])
        update_gunw_with_solid_earth_tide(tmp_gunw, 'secondary', [orbit_dict['secondary']])

        for acq_type in ['reference', 'secondary']:
            group = f'/science/grids/corrections/external/tides/solidEarth/{acq_type}'
            variable = 'solidEarthTide'
            with rasterio.open(f'netcdf:{tmp_gunw}:{group}/{variable}') as ds:
                # Check nodata and CRS
                assert ds.nodata == 0
                assert ds.crs == CRS.from_epsg(4326)

                # Transform should not be the identity
                t = ds.transform
                assert t != Affine(1, 0, 0, 0, 1, 0)


@pytest.mark.parametrize('acq_type', ['reference', 'secondary'])
def test_azimuth_time(orbit_files_for_set: list, gunw_paths_for_set: list, acq_type: str):
    """Ensures deviation of retrieved azimuth time array is within 1e-3 seconds"""
    for gunw_path_for_set, orbit_dict in zip(gunw_paths_for_set, orbit_files_for_set):
        group = 'science/grids/imagingGeometry'
        with xr.open_dataset(gunw_path_for_set, group=group) as ds:
            # lon_res is pos (+) and lat_res is neg (-)
            lon_res, lat_res = ds.rio.resolution()

            # Need upper left corner rather than pixel center
            hgt = ds.heightsMeta.data
            # This moves the lats northword due to sign of lat_res (see above)
            lat = ds.latitudeMeta.data - lat_res / 2.
            lon = ds.longitudeMeta.data - lon_res / 2.

        # Uses secondary image
        group = 'science/radarMetaData/inputSLC'
        with xr.open_dataset(gunw_path_for_set, group=f'{group}/{acq_type}') as ds:
            slc_ids = ds['L1InputGranules'].data
            # Ensure non-empty and sorted by acq_time
            slc_ids = sorted(list(filter(lambda x: x, slc_ids)))
            slc_start_time = get_start_time_from_slc_id(slc_ids[0])

        hgt_mesh, lat_mesh, lon_mesh = np.meshgrid(hgt, lat, lon, indexing='ij')
        # Azimuth time array
        X = get_azimuth_time_array(orbit_xmls=[orbit_dict[acq_type]],
                                   slc_start_time=slc_start_time,
                                   height_mesh_arr=hgt_mesh,
                                   latitude_mesh_arr=lat_mesh,
                                   longitude_mesh_arr=lon_mesh)
        # Total seconds from minimum time
        Y = (X - X.min()) / np.timedelta64(1, 's')
        # Vertical standard deviation
        Y_std = Y.std(axis=0)
        assert_almost_equal(Y_std, 0, decimal=3)

        # Ensure that azimuth times are all within specified padding used in computation
        # Padding used is 600 seconds - we check for 70 - note we are using the SLC id start time
        # From secondary and there are TWO slcs so this makes sense with an SLC requiring being acquired
        # over about 20-30 seconds; also the meshgrid for this layer is slightly larger than the GUNW as well
        # indicating why the 10 second buffer is used.
        x = pd.to_datetime(X.ravel())
        differences_in_sec = (x - slc_start_time).total_seconds()
        result = np.all(differences_in_sec < 70)
        assert result


def get_gunw_attrs_for_pysolid(gunw_path: str) -> dict:
    """ Access necessary GUNW attributes to compute SET """
    group = 'science/grids/imagingGeometry'
    with xr.open_dataset(gunw_path, group=group, engine='rasterio') as ds:
        # z_meta = ds.heightsMeta.data
        gt = ds.rio.transform()
        x_step = gt.a
        y_step = gt.e
        x_first = gt.c
        y_first = gt.f

        # convert angles to rad
        _, length, width = ds.incidenceAngle.shape
        solidtide_atr = {
            'LENGTH': length,
            'WIDTH': width,
            'X_FIRST': x_first,
            'Y_FIRST': y_first,
            'X_STEP':  x_step,
            'Y_STEP': y_step,
        }

    return solidtide_atr


def get_pysolid_set(gunw_path: Path, acq_type='reference') -> np.ndarray:
    """Source: https://github.com/insarlab/PySolid/blob/main/docs/plot_grid_SET.ipynb

    returns the SET cube as displacement in millimeters (mm)
    """
    assert acq_type in ['reference', 'secondary']

    group = f'science/radarMetaData/inputSLC/{acq_type}'
    with xr.open_dataset(gunw_path, group=group) as ds:
        slc_id = ds['L1InputGranules'].values[0]
    dt_obj = get_start_time_from_slc_id(slc_id).to_pydatetime()

    atr = get_gunw_attrs_for_pysolid(gunw_path)

    tide_e, tide_n, tide_u = pysolid.calc_solid_earth_tides_grid(dt_obj,
                                                                 atr,
                                                                 display=False,
                                                                 verbose=True
                                                                 )

    group = 'science/grids/imagingGeometry'
    with xr.open_dataset(gunw_path, group=group, engine='rasterio') as ds:
        inc_angle = np.deg2rad(ds.incidenceAngle.data)
        az_angle = np.deg2rad(ds.azimuthAngle.data-90)

    # broadcasting will ensure 2d arrays are copied in height dimension
    tide_los = (tide_e * np.sin(inc_angle) * np.sin(az_angle) * -1
                + tide_n * np.sin(inc_angle) * np.cos(az_angle)
                + tide_u * np.cos(inc_angle))

    # Convert to mm (pysolid is in meters)
    tide_los *= 1_000
    return tide_los


@pytest.mark.parametrize('acq_type', ['reference', 'secondary'])
def test_magnitude_of_set_with_variable_timing(acq_type: str, orbit_files_for_set: list,
                                               gunw_paths_for_set: list, tmp_path):
    """This test verifies (with the functions above) the SET correction doesn't deviate more than 1 mm than
    a fixed time calculation.

    Note to get an orbit file from a gunw use:
    ```
    group = f'science/radarMetaData/inputSLC/{acq_type}'
    with xr.open_dataset(gunw_path_for_set_2, group=group) as ds:
        slc_id = ds['L1InputGranules'].values[0]

    orb_file, _ = get_orb.downloadSentinelOrbitFile(slc_id)
    ```
    """
    for gunw_path_for_set, orbit_dict in zip(gunw_paths_for_set, orbit_files_for_set):

        tmp_gunw = tmp_path / 'temp.nc'
        shutil.copy(gunw_path_for_set, tmp_gunw)

        orb_file = orbit_dict[acq_type]
        update_gunw_with_solid_earth_tide(tmp_gunw, acq_type, [orb_file])

        path_to_set = (f'netcdf:{tmp_gunw}:/science/grids/corrections/external/'
                       f'tides/solidEarth/{acq_type}/solidEarthTide')
        with rasterio.open(path_to_set) as ds:
            X = ds.read()

        X_set_plugin_mm = X * 0.055465761572122574 / np.pi / 4 * 1_000
        X_set_pysolid_mm = get_pysolid_set(tmp_gunw, acq_type=acq_type)

        set_abs_diff = np.abs(X_set_pysolid_mm - X_set_plugin_mm)
        assert np.max(set_abs_diff) < 1


def test_overlapping_orbits(get_overlapping_orbits_for_set_test):
    """See https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/issues/148

    relevant granules are:

    ```
    granules = ['S1A_IW_SLC__1SDV_20230615T225929_20230615T225956_049003_05E492_C8D9',
                'S1A_IW_SLC__1SDV_20230615T225954_20230615T230021_049003_05E492_3D08']
    ```
    """
    slc_start_time = datetime.datetime(2023, 6, 15, 22, 59, 29)
    orb_paths = get_overlapping_orbits_for_set_test()
    bounds = [-77.742622,  39.382721, -74.029358,  42.887646]

    # Build cube
    lons = np.linspace(bounds[0], bounds[2], 20)
    lats = np.linspace(bounds[3], bounds[1], 20)
    hgts = [-500, 0, 500, 1500]

    height_mesh_arr, latitude_mesh_arr, longitude_mesh_arr = np.meshgrid(hgts, lats, lons, indexing='ij')

    # Should not crash
    X = get_azimuth_time_array(orb_paths,
                               slc_start_time,
                               height_mesh_arr,
                               latitude_mesh_arr,
                               longitude_mesh_arr,
                               orbit_padding_in_seconds=600)
    assert X.shape == height_mesh_arr.shape
