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


def compute_solid_earth_tide_from_gunw(gunw_path: str, acq_type: str) -> xr.Dataset:
    """ Read GUNW and compute/export differential SET """
    if acq_type not in ['reference', 'secondary']:
        raise ValueError('acq_type must be in "reference" or "secondary"')

    gunw_basename = Path(gunw_path).name
    dates = gunw_basename.split('-')[6].split('_')
    ref_time = gunw_basename.split('-')[7]

    acq_date = dates[0] if acq_type == 'reference' else dates[1]

    # get GUNW attributes
    (wavelength,
     z_meta,
     inc_angle,
     az_angle,
     set_attrs) = get_gunw_attrs(gunw_path)

    # compute differential SET ENU
    # Use reference time twice (assuming exact same pass time)
    tide_e, tide_n, tide_u = compute_enu_se_tide(acq_date,
                                                 ref_time,
                                                 set_attrs)

    # compute SET LOS estimate for each height level
    tide_los = np.zeros(inc_angle.shape, dtype=float)
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
        gt = ds.rio.transform()
        # convert angles to rad
        inc_angle = np.deg2rad(ds.incidenceAngle.data)
        az_angle = np.deg2rad(ds.azimuthAngle.data-90)
        solidtide_atr = {
            'LENGTH': az_angle.shape[1],
            'WIDTH': az_angle.shape[2],
            'X_FIRST': gt.c,
            'Y_FIRST': gt.f,
            'X_STEP':  gt.a,
            'Y_STEP': gt.e,
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
    tide_e_slant = tide_e * (np.sin(inc_angle) * np.sin(az_angle) * -1)
    tide_n_slant = tide_n * (np.sin(inc_angle) * np.cos(az_angle))
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

    solidtide_corr_ds = solidtide_corr_ds.rename({'longitudeMeta': 'longitude',
                                                  'latitudeMeta': 'latitude',
                                                  'heightsMeta': 'height'})
    attrs = {'description': 'Solid Earth tide',
             'units': 'radians',
             'long_name': lyr_name,
             'standard_name': lyr_name}

    dim_order = ['height', 'latitude', 'longitude']
    solidtide_corr_ds[lyr_name] = (dim_order, tide_los)
    solidtide_corr_ds[lyr_name].attrs.update(attrs)
    solidtide_corr_ds = solidtide_corr_ds[[lyr_name]]
    solidtide_corr_ds = solidtide_corr_ds.astype(float)
    solidtide_corr_ds.rio.write_crs('epsg:4326', inplace=True)
    solidtide_corr_ds['solidEarthTide'].rio.write_nodata(0, inplace=True)
    return solidtide_corr_ds


def update_gunw_with_solid_earth_tide(gunw_path: Path, acq_type: str) -> Path:
    if acq_type not in ['reference', 'secondary']:
        raise ValueError('acq_type must be in "reference" or "secondary"')
    tide_group = '/science/grids/corrections/external/tides'
    # If GUNW has dummy placeholder - delete it
    se_tide_group_dummy = f'{tide_group}/solidEarthTide'

    se_tide_group_acq = f'{tide_group}/solidEarth/{acq_type}'
    with h5py.File(gunw_path, 'a') as file:
        if se_tide_group_dummy in file:
            del file[se_tide_group_dummy]
    solid_earth_tide_ds = compute_solid_earth_tide_from_gunw(gunw_path,
                                                             acq_type)
    solid_earth_tide_ds.to_netcdf(gunw_path,
                                  mode='a',
                                  group=se_tide_group_acq)
    return gunw_path
