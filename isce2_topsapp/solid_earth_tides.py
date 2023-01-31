# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Authors: Simran Sangha, Charles Marshak, Brett Buzzanga, David Bekaert,
#         Marin Govorcin, Zhang Yunjun
# Copyright 2023, by the California Institute of Technology. ALL RIGHTS
# RESERVED. United States Government Sponsorship acknowledged.
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
import datetime as dt
from pathlib import Path
from typing import Tuple

import h5py
import numpy as np
import pysolid
import xarray as xr


def compute_solid_earth_tide_from_gunw(gunw_path: str) -> xr.Dataset:
    """ Read GUNW and compute/export differential SET """

    gunw_basename = Path(gunw_path).name
    dates = gunw_basename.split('-')[6].split('_')
    ref_time = gunw_basename.split('-')[7]

    # get GUNW attributes
    (wavelength,
     z_meta,
     inc_angle,
     az_angle,
     set_attrs) = get_gunw_attrs(gunw_path)

    # compute differential SET ENU
    # Use reference time twice (assuming exact same pass time)
    tide_e_ref, tide_n_ref, tide_u_ref = compute_enu_se_tide(dates[0],
                                                             ref_time,
                                                             set_attrs)
    tide_e_sec, tide_n_sec, tide_u_sec = compute_enu_se_tide(dates[1],
                                                             ref_time,
                                                             set_attrs)
    tide_e = tide_e_sec - tide_e_ref
    tide_n = tide_n_sec - tide_n_ref
    tide_u = tide_u_sec - tide_u_ref

    # compute SET LOS estimate for each height level
    tide_los = np.zeros(inc_angle.shape)
    for i in range(len(z_meta)):
        tide_los[i] = compute_los_solid_earth_tide(tide_e,
                                                   tide_n,
                                                   tide_u,
                                                   inc_angle[i],
                                                   az_angle[i],
                                                   wavelength)

    solidtide_corr_ds = export_se_tides_to_dataset(gunw_path, tide_los)

    return solidtide_corr_ds


def get_gunw_attrs(gunw_path: str) -> Tuple[float, np.array, np.array,
                                            np.array, xr.Dataset, dict]:
    """ Access necessary GUNW attributes to compute SET """

    group = 'science/radarMetaData'
    with xr.open_dataset(gunw_path, group=group) as ds:
        wavelength = ds['wavelength'].item()

    group = 'science/grids/imagingGeometry'
    with xr.open_dataset(gunw_path, group=group, engine='rasterio') as ds:
        z_meta = ds.heightsMeta.data
        lat_meta = ds.y.data
        lon_meta = ds.x.data
        # convert angles to rad
        inc_angle = np.deg2rad(ds.incidenceAngle.data)
        az_angle = np.deg2rad(ds.azimuthAngle.data-90)
        solidtide_atr = {
            'LENGTH': len(lat_meta),
            'WIDTH': len(lon_meta),
            'X_FIRST': lon_meta[0],
            'Y_FIRST': lat_meta[0],
            'X_STEP':  lon_meta[1] - lon_meta[0],
            'Y_STEP': lat_meta[1] - lat_meta[0],
        }

    return wavelength, z_meta, inc_angle, az_angle, solidtide_atr


def compute_enu_se_tide(acq_date: str,
                        acq_time: str,
                        solidtide_atr: dict) -> np.array:
    """ Compute SET in ENU """
    # source:
    # https://github.com/insarlab/ and
    # PySolid/blob/main/docs/plot_grid_SET.ipynb
    dt_obj = dt.datetime.strptime(acq_date + '-' + acq_time,
                                  "%Y%m%d-%H%M%S")
    tide_e, tide_n, tide_u = pysolid.calc_solid_earth_tides_grid(dt_obj,
                                                                 solidtide_atr,
                                                                 display=False,
                                                                 verbose=False)

    return tide_e, tide_n, tide_u


def compute_los_solid_earth_tide(tide_e: np.array,
                                 tide_n: np.array,
                                 tide_u: np.array,
                                 inc_angle: np.array,
                                 az_angle: np.array,
                                 wavelength: float) -> np.array:
    """ Compute SET in LOS """
    # source:
    # https://github.com/insarlab/
    # PySolid/blob/main/docs/plot_grid_SET.ipynb

    # project ENU to radar line-of-sight (LOS)
    # with positive for motion towards satellite
    tide_e_slant = tide_e * np.sin(inc_angle) * np.sin(az_angle) * -1
    tide_n_slant = tide_n * np.sin(inc_angle) * np.cos(az_angle)
    tide_u_slant = tide_u * np.cos(inc_angle)
    tide_los = tide_e_slant + tide_n_slant + tide_u_slant

    # Convert m to rad
    tide_los = tide_los / (wavelength / (4*np.pi))

    return tide_los


def export_se_tides_to_dataset(gunw_path: str,
                               tide_los: np.array,
                               lyr_name='solidEarthTide') -> xr.Dataset:
    """ Create SET array and populate with metadata leveraging
    the same geodata from the imaging geometry in the gunw"""

    # obtain affine transformation and coordinate metadata
    group = 'science/grids/imagingGeometry'
    solidtide_corr_ds = xr.open_dataset(gunw_path,
                                        group=group)

    solidtide_corr_ds = solidtide_corr_ds.rename({'longitudeMeta': 'x',
                                                  'latitudeMeta': 'y'})
    attrs = {'description': 'Solid Earth tide',
             'units': 'radians',
             'long_name': lyr_name,
             'standard_name': lyr_name}

    dim_order = ['heightsMeta', 'y', 'x']
    solidtide_corr_ds[lyr_name] = (dim_order, tide_los)
    solidtide_corr_ds[lyr_name].attrs.update(attrs)
    return solidtide_corr_ds[[lyr_name]]


def update_gunw_with_solid_earth_tide(gunw_path: Path) -> Path:
    se_tide_group = '/science/grids/corrections/external/tides'
    with h5py.File(gunw_path, 'a') as file:
        if se_tide_group in file:
            del file[se_tide_group]
    solid_earth_tide_ds = compute_solid_earth_tide_from_gunw(gunw_path)
    solid_earth_tide_ds.to_netcdf(gunw_path,
                                  mode='a',
                                  group=se_tide_group)
    return gunw_path
