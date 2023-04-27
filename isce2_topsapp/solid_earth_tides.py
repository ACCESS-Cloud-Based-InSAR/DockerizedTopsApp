# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Authors: Simran Sangha, Charles Marshak, Brett Buzzanga, David Bekaert,
#         Marin Govorcin, Zhang Yunjun
# Copyright 2023, by the California Institute of Technology. ALL RIGHTS
# RESERVED. United States Government Sponsorship acknowledged.
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
import datetime
from itertools import starmap
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import xarray as xr
from isce.components.isceobj.Constants import SPEED_OF_LIGHT
from pysolid.solid import solid_grid
from tqdm import tqdm

from isce2_topsapp.packaging_utils.makeGeocube import (getMergedOrbit,
                                                       loadProduct)


def compute_solid_earth_tide_from_gunw(*,
                                       gunw_path: str,
                                       reference_or_secondary: str,
                                       isce_data_dir: Path) -> xr.Dataset:
    """
    Read GUNW and compute/export differential SET

    Parameters
    ----------
    gunw_path : str
        Netcdf of the GUNW
    reference_or_secondary : str
        Needs to be either "reference" or "secondary" - refers to category of
        pass for which SET will be calculated
    isce_data_dir : Path
        The data directory of ISCE outputs to extract orbit information

    Returns
    -------
    xr.Dataset
        SET data

    Raises
    ------
    ValueError
        When reference_or_secondary is not specified correctly
    """
    if reference_or_secondary not in ['reference', 'secondary']:
        raise ValueError('acq_type must be in "reference" or "secondary"')

    # get GUNW attributes
    group = 'science/radarMetaData'
    with xr.open_dataset(gunw_path, group=group) as ds:
        wavelength = ds['wavelength'].item()

    group = 'science/grids/imagingGeometry'
    with xr.open_dataset(gunw_path, group=group, mode='r') as ds:
        lon_res, lat_res = ds.rio.resolution()
        lat_res = -lat_res

        height_coord_arr = ds.heightsMeta.data
        # half pixel shift to ensure AREA (i.e. upper left corner) convention assumed by pysolid
        # the xarray coordinates are pixel centered
        latitude_coord_arr = ds.latitudeMeta.data + lat_res / 2.
        longitude_coord_arr = ds.longitudeMeta.data - lon_res / 2.
        # compute differential SET ENU
        # the output shapes will match the variables of the xarray dataset (or mesh of the coords) i.e.
        # height_dim x latitude_dim x longitude_dim
        tide_e, tide_n, tide_u = compute_enu_solid_earth_tide(isce_data_dir=isce_data_dir,
                                                              reference_or_secondary=reference_or_secondary,
                                                              height_coord_arr=height_coord_arr,
                                                              latitude_coord_arr=latitude_coord_arr,
                                                              longitude_coord_arr=longitude_coord_arr,
                                                              res_y=lat_res,
                                                              res_x=lon_res)

        # For LOS computation
        inc_angle = np.deg2rad(ds.incidenceAngle.data)
        azi_angle = np.deg2rad(ds.azimuthAngle.data - 90)

    tide_los = compute_los_solid_earth_tide(tide_e,
                                            tide_n,
                                            tide_u,
                                            inc_angle,
                                            azi_angle,
                                            wavelength)

    solidtide_corr_ds = export_se_tides_to_dataset(gunw_path, tide_los)
    return solidtide_corr_ds


def get_orbit_from_isce_xml(product_dir: Path):
    swath_xmls = list(product_dir.glob('IW*.xml'))
    if len(swath_xmls) == 0:
        raise ValueError('No IW files found in product directory')
    products = list(map(loadProduct, swath_xmls))
    orb = getMergedOrbit(products)
    return orb


def get_azimuth_time_array(product_dir: Path,
                           height_mesh_arr: np.ndarray,
                           latitude_mesh_arr: np.ndarray,
                           longitude_mesh_arr: np.ndarray) -> np.ndarray:

    orb = get_orbit_from_isce_xml(product_dir)

    m, n, p = height_mesh_arr.shape

    heights_flat = height_mesh_arr.ravel()
    latitude_flat = latitude_mesh_arr.ravel()
    longitude_flat = longitude_mesh_arr.ravel()

    azimuth_time_list = []
    for (lon, lat, hgt) in zip(tqdm(longitude_flat), latitude_flat, heights_flat):
        datetime_isce, rng = orb.geo2rdr([lat, lon, hgt])
        rng_seconds = rng / SPEED_OF_LIGHT
        total_time_isce2 = datetime_isce + datetime.timedelta(seconds=rng_seconds)
        dt_np = pd.to_datetime(str(total_time_isce2))
        azimuth_time_list.append(dt_np)
    azimuth_time_flat_np = np.array(azimuth_time_list, dtype='datetime64')
    azimuth_time = azimuth_time_flat_np.reshape((m, n, p))
    return azimuth_time


def solid_grid_pixel_rounded_to_nearest_sec(timestamp: pd.Timestamp,
                                            lon: float,
                                            lat: float,
                                            res_x: float,
                                            res_y: float) -> np.ndarray:
    tide_e, tide_n, tide_u = solid_grid(timestamp.year,
                                        timestamp.month,
                                        timestamp.day,
                                        timestamp.hour,
                                        timestamp.minute,
                                        timestamp.second,
                                        lat, res_y, 1,
                                        lon, res_x, 1)
    # The output is a 1 x 1 matrix and we want the floats within them
    tide_e, tide_n, tide_u = tide_e[0, 0], tide_n[0, 0], tide_u[0, 0]
    return np.array([tide_e, tide_n, tide_u])


def solid_grid_pixel_interpolated_across_second_est(np_datetime: np.datetime64,
                                                    lon: float,
                                                    lat: float,
                                                    res_x: float,
                                                    res_y: float) -> np.ndarray:
    dt = pd.to_datetime(np_datetime)
    dt_sec_floor = dt.floor('S')
    dt_sec_ceil = dt.ceil('S')

    # The sum of these differences is 1 so can serve as weights
    seconds_diff_low = (dt - dt_sec_floor).total_seconds()
    seconds_diff_high = (dt_sec_ceil - dt).total_seconds()

    se_tides_low = solid_grid_pixel_rounded_to_nearest_sec(dt_sec_floor,
                                                           lon,
                                                           lat,
                                                           res_x,
                                                           res_y)

    se_tides_high = solid_grid_pixel_rounded_to_nearest_sec(dt_sec_ceil,
                                                            lon,
                                                            lat,
                                                            res_x,
                                                            res_y)

    interpolated_se_tides = se_tides_low * seconds_diff_low + se_tides_high * seconds_diff_high
    return interpolated_se_tides


def compute_enu_solid_earth_tide(*,
                                 isce_data_dir: Path,
                                 reference_or_secondary: str,
                                 height_coord_arr: np.ndarray,
                                 latitude_coord_arr: np.ndarray,
                                 longitude_coord_arr: np.ndarray,
                                 res_x: float,
                                 res_y: float
                                 ) -> np.ndarray:
    """Compute SET in ENU """

    if (res_x <= 0) or (res_y <= 0):
        raise ValueError('Resolutions must be positive')

    product_dir = Path(isce_data_dir / reference_or_secondary)
    if not product_dir.exists():
        raise ValueError(f'The isce data directory specified doesn\'t have a "{reference_or_secondary}" directory')

    height_mesh_arr, latitude_mesh_arr, longitude_mesh_arr = np.meshgrid(height_coord_arr,
                                                                         latitude_coord_arr,
                                                                         longitude_coord_arr,
                                                                         # indexing keyword argument
                                                                         # Ensures output dimensions
                                                                         # align with order the inputs
                                                                         # height x latitude x longitude
                                                                         indexing='ij')

    azimuth_time_arr = get_azimuth_time_array(product_dir,
                                              height_mesh_arr,
                                              latitude_mesh_arr,
                                              longitude_mesh_arr)

    latitude_flat = latitude_mesh_arr.ravel()
    longitude_flat = latitude_mesh_arr.ravel()

    input_data = zip(azimuth_time_arr.ravel(),
                     longitude_flat,
                     latitude_flat)

    def solid_grid_pixel_partial(azi_time: float,
                                 lon: float,
                                 lat: float) -> np.ndarray:
        return solid_grid_pixel_interpolated_across_second_est(azi_time,
                                                               lon,
                                                               lat,
                                                               res_x,
                                                               res_y)

    results = list(starmap(solid_grid_pixel_partial,
                           input_data))
    tide_e_flat, tide_n_flat, tide_u_flat = zip(*results)
    tide_e_flat, tide_n_flat, tide_u_flat = (np.array(tide_e_flat),
                                             np.array(tide_n_flat),
                                             np.array(tide_u_flat))

    m, n, p = height_mesh_arr.shape
    tide_e = tide_e_flat.reshape((m, n, p))
    tide_n = tide_n_flat.reshape((m, n, p))
    tide_u = tide_u_flat.reshape((m, n, p))
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
    with xr.open_dataset(gunw_path, group=group) as ds:
        solidtide_corr_ds = ds.copy(deep=True)

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
    solidtide_corr_ds = solidtide_corr_ds.astype(np.float32)
    solidtide_corr_ds.rio.write_crs('epsg:4326', inplace=True)
    solidtide_corr_ds['solidEarthTide'].rio.write_nodata(0, inplace=True)
    return solidtide_corr_ds


def update_gunw_with_solid_earth_tide(gunw_path: Path,
                                      reference_or_secondary: str,
                                      isce_data_dir: Path = None) -> Path:
    if reference_or_secondary not in ['reference', 'secondary']:
        raise ValueError('acq_type must be in "reference" or "secondary"')
    tide_group = '/science/grids/corrections/external/tides'
    # If GUNW has dummy placeholder - delete it
    se_tide_group_dummy = f'{tide_group}/solidEarthTide'

    se_tide_group_acq = f'{tide_group}/solidEarth/{reference_or_secondary}'
    with h5py.File(gunw_path, 'a') as file:
        if se_tide_group_dummy in file:
            del file[se_tide_group_dummy]
    solid_earth_tide_ds = compute_solid_earth_tide_from_gunw(gunw_path=gunw_path,
                                                             isce_data_dir=isce_data_dir,
                                                             reference_or_secondary=reference_or_secondary)
    solid_earth_tide_ds.to_netcdf(gunw_path,
                                  mode='a',
                                  group=se_tide_group_acq)
    return gunw_path
