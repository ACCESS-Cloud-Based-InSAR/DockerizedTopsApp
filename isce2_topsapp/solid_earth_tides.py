# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Authors: Simran Sangha, Charles Marshak, Brett Buzzanga, David Bekaert,
#         Marin Govorcin, Zhang Yunjun
# Copyright 2023, by the California Institute of Technology. ALL RIGHTS
# RESERVED. United States Government Sponsorship acknowledged.
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
import datetime
import xml.etree.ElementTree as ET
from itertools import starmap
from pathlib import Path
from typing import Union

import h5py
import numpy as np
import pandas as pd
import xarray as xr
from isce.components.isceobj.Constants import SPEED_OF_LIGHT
from isce.components.isceobj.Orbit.Orbit import Orbit, StateVector
from pysolid.solid import solid_grid
from tqdm import tqdm


def read_ESA_Orbit_file(orbit_xml: Union[str, Path]) -> list[np.ndarray]:
    """
    Source: https://github.com/dbekaert/RAiDER/blob/dev/tools/RAiDER/losreader.py#L465
    Note: Raider cannot be imported because ISCE2 and ISCE3 require very different
    environments.

    Parameters
    ----------
    orbit_xml : str | Path
        Orbit xml file

    Returns
    -------
    list[np.ndarray]
      [t, pos_x, pos_y, pos_z, vel_x, vel_y, vel_z] each entry is a vector
      denoting the state vector of the satellite at a given time, i.e. at time
      t[k], the state vector is pos_x[k], ..., vel_z[k].
    """
    tree = ET.parse(orbit_xml)
    root = tree.getroot()
    data_block = root[1]
    numOSV = len(data_block[0])

    t = []
    x = np.ones(numOSV)
    y = np.ones(numOSV)
    z = np.ones(numOSV)
    vx = np.ones(numOSV)
    vy = np.ones(numOSV)
    vz = np.ones(numOSV)

    for i, st in enumerate(data_block[0]):
        t.append(
            datetime.datetime.strptime(
                st[1].text,
                'UTC=%Y-%m-%dT%H:%M:%S.%f'
            )
        )

        x[i] = float(st[4].text)
        y[i] = float(st[5].text)
        z[i] = float(st[6].text)
        vx[i] = float(st[7].text)
        vy[i] = float(st[8].text)
        vz[i] = float(st[9].text)
    t = np.array(t)
    return [t, x, y, z, vx, vy, vz]


def get_state_vector_arrays(orbit_xml: Union[str, Path]) -> list[StateVector]:
    """Source: https://github.com/dbekaert/RAiDER/blob/dev/tools/RAiDER/losreader.py
    """
    state_vector_list = []
    t, x, y, z, vx, vy, vz = read_ESA_Orbit_file(orbit_xml)
    for idx in range(len(t)):
        position = x[idx], y[idx], z[idx]
        velocity = vx[idx], vy[idx], vz[idx]
        state_vector = StateVector(time=t[idx],
                                   position=position,
                                   velocity=velocity)
        state_vector_list.append(state_vector)

    return state_vector_list


def get_orbit_obj_from_orbit_xmls(orbit_xmls: list[Path],
                                  slc_start_time: datetime.datetime,
                                  pad_in_seconds: int = 600) -> Orbit:
    """
    Source: https://github.com/dbekaert/RAiDER/blob/dev/tools/RAiDER/losreader.py

    **Warning**: geo2rdr numerically finds azimuth and range time by Newton's method. The clipping is
    essential and larger than 100,000 seconds yielded errors.

    The reason for the above errors were observed are due to how geo2rdr initializes the root finding method.
    Specifically, using the midpoint of the orbi min/max times. If the clipping
    is too large then the initial point likely is not centered near the frame and a different
    point is coverged to. Using a smaller window ensures a correct time is converged to.

    See: https://github.com/isce-framework/isce2/blob/main/components/isceobj/Orbit/Orbit.py#L1000

    Note that `slc_start_time` is used here to initialize the center of window for the orb.geo2rdr because it's easy to
    get from the name.
    """
    state_vectors = []
    for orbit_xml in orbit_xmls:
        state_vectors.extend(get_state_vector_arrays(orbit_xml))
    orb = Orbit()
    orb.configure()
    window_min = slc_start_time - datetime.timedelta(seconds=pad_in_seconds)
    window_max = slc_start_time + datetime.timedelta(seconds=pad_in_seconds)
    for sv in state_vectors:
        if (sv.time < window_max) and (sv.time > window_min):
            orb.addStateVector(sv)
    return orb


def get_start_time_from_slc_id(slc_id: str) -> pd.Timestamp:
    acq_start_time_token = slc_id.split('_')[5]
    return pd.to_datetime(acq_start_time_token)


def compute_solid_earth_tide_from_gunw(*,
                                       gunw_path: str,
                                       reference_or_secondary: str,
                                       orbit_xmls: list[Path]) -> xr.Dataset:
    """
    Read GUNW and compute/export differential SET

    Parameters
    ----------
    gunw_path : str
        Netcdf of the GUNW
    reference_or_secondary : str
        Needs to be either "reference" or "secondary" - refers to category of
        pass for which SET will be calculated
    orbit_xml : Path
        The ESA burst xml

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

    group = 'science/radarMetaData/inputSLC'
    with xr.open_dataset(gunw_path, group=f'{group}/{reference_or_secondary}') as ds:
        slc_ids = ds['L1InputGranules'].data
        # Ensure non-empty and sorted by acq_time
        slc_ids = sorted(list(filter(lambda x: x, slc_ids)))
        slc_start_time = get_start_time_from_slc_id(slc_ids[0])

    group = 'science/grids/imagingGeometry'
    with xr.open_dataset(gunw_path, group=group, mode='r') as ds:
        # latitude resolution will match the rasterio transformed; i.e. it will be negative
        lon_res, lat_res = ds.rio.resolution()
        # We make the resolution positive
        lat_res = -lat_res

        height_coord_arr = ds.heightsMeta.data
        # half pixel shift to ensure AREA (i.e. upper left corner) convention assumed by pysolid
        # the xarray coordinates are pixel centered; latitude resolution moves up due to sign (see above)
        latitude_coord_arr = ds.latitudeMeta.data + lat_res / 2.
        longitude_coord_arr = ds.longitudeMeta.data - lon_res / 2.
        # compute differential SET ENU
        # the output shapes will match the variables of the xarray dataset (or mesh of the coords) i.e.
        # height_dim x latitude_dim x longitude_dim
        tide_e, tide_n, tide_u = compute_enu_solid_earth_tide(orbit_xmls=orbit_xmls,
                                                              slc_start_time=slc_start_time,
                                                              height_coord_arr=height_coord_arr,
                                                              longitude_coord_arr=longitude_coord_arr,
                                                              latitude_coord_arr=latitude_coord_arr,
                                                              res_x=lon_res,
                                                              res_y=lat_res,)

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


def get_azimuth_time_array(orbit_xmls: list[Path],
                           slc_start_time: datetime.datetime,
                           height_mesh_arr: np.ndarray,
                           latitude_mesh_arr: np.ndarray,
                           longitude_mesh_arr: np.ndarray,
                           orbit_padding_in_seconds: int = 600) -> np.ndarray:
    """Get azimuth time array in which each pixel in mesh array is matched to a azimuth time corresponding to time
    which satellite passes (zero-doppler).

    Parameters
    ----------
    orbit_xmls : list[Path]
    slc_start_time : datetime.datetime
        This is required to truncate state vector times roughly around a window of the SLC. Used for geo2rdr
    height_mesh_arr : np.ndarray
    latitude_mesh_arr : np.ndarray
    longitude_mesh_arr : np.ndarray
    orbit_padding_in_seconds : int, optional
        This is required to truncate state vector times roughly around a window of the SLC. Used for geo2rdr

    Returns
    -------
    np.ndarray
        Array which matches the size of the input mesh arrays and obtains the zero-doppler time with respect to the
        satellite orbit.

    Notes
    -----
    See get_orbit_obj_from_orbit_xmls as to why slc start time and padding is required.
    """

    orb = get_orbit_obj_from_orbit_xmls(orbit_xmls,
                                        slc_start_time,
                                        pad_in_seconds=orbit_padding_in_seconds)

    m, n, p = height_mesh_arr.shape

    heights_flat = height_mesh_arr.ravel()
    latitude_flat = latitude_mesh_arr.ravel()
    longitude_flat = longitude_mesh_arr.ravel()

    azimuth_time_list = []
    for (lon, lat, hgt) in zip(tqdm(longitude_flat), latitude_flat, heights_flat):
        datetime_isce, rng = orb.geo2rdr([lat, lon, hgt])
        rng_seconds = rng / SPEED_OF_LIGHT
        total_time_isce = datetime_isce + datetime.timedelta(seconds=rng_seconds)
        dt_np = pd.to_datetime(str(total_time_isce))
        azimuth_time_list.append(dt_np)
    azimuth_time_flat_np = np.array(azimuth_time_list, dtype='datetime64')
    azimuth_time = azimuth_time_flat_np.reshape((m, n, p))
    return azimuth_time


def solid_grid_pixel_rounded_to_nearest_sec(timestamp: pd.Timestamp,
                                            lon: float,
                                            lat: float,
                                            res_x: float,
                                            res_y: float) -> np.ndarray:
    if any([res <= 0 for res in [res_x, res_y]]):
        raise ValueError('Resolutions must be positive')
    # https://github.com/insarlab/PySolid/blob/main/src/pysolid/grid.py#L69-L79
    # Make sure that our steps are in line with the geo-transform
    lat_step = -res_y
    lon_step = res_x
    tide_e, tide_n, tide_u = solid_grid(timestamp.year,
                                        timestamp.month,
                                        timestamp.day,
                                        timestamp.hour,
                                        timestamp.minute,
                                        timestamp.second,
                                        lat, lat_step, 1,
                                        lon, lon_step, 1)
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

    # The sum of these differences is 1 so can serve as linear weights
    # When we use 1 - diff; the closer the time, the more it should be valued
    seconds_diff_low = (dt - dt_sec_floor).total_seconds()
    seconds_diff_high = (dt_sec_ceil - dt).total_seconds()

    for diff_time in [seconds_diff_low, seconds_diff_high]:
        if (diff_time < 0) or (diff_time >= 1):
            raise ValueError('The truncated times were invalid; should be in [0, 1)')

    # The rare case in which the truncated time occurs exactly on the seconds marker (w.r.t. floating point)
    # This would mean seconds_diff_low and seconds_diff_high are both 0.
    if np.abs(seconds_diff_low) < 1e-9:
        interpolated_se_tides = solid_grid_pixel_rounded_to_nearest_sec(dt_sec_floor,
                                                                        lon,
                                                                        lat,
                                                                        res_x,
                                                                        res_y)
    else:
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

        # The closer a time is to its ceiling or floor, the smaller the difference is; and the higher the linear weight
        # in (0, 1) should be
        interpolated_se_tides = se_tides_low * (1 - seconds_diff_low) + se_tides_high * (1 - seconds_diff_high)
    return interpolated_se_tides


def compute_enu_solid_earth_tide(*,
                                 orbit_xmls: Path,
                                 slc_start_time: pd.Timestamp,
                                 height_coord_arr: np.ndarray,
                                 latitude_coord_arr: np.ndarray,
                                 longitude_coord_arr: np.ndarray,
                                 res_x: float,
                                 res_y: float
                                 ) -> np.ndarray:
    """Compute SET in ENU """

    if (res_x <= 0) or (res_y <= 0):
        raise ValueError('Resolutions must be positive')

    height_mesh_arr, latitude_mesh_arr, longitude_mesh_arr = np.meshgrid(height_coord_arr,
                                                                         latitude_coord_arr,
                                                                         longitude_coord_arr,
                                                                         # indexing keyword argument
                                                                         # Ensures output dimensions
                                                                         # align with order the inputs
                                                                         # height x latitude x longitude
                                                                         indexing='ij')

    azimuth_time_arr = get_azimuth_time_array(orbit_xmls,
                                              slc_start_time,
                                              height_mesh_arr,
                                              latitude_mesh_arr,
                                              longitude_mesh_arr)

    latitude_flat = latitude_mesh_arr.ravel()
    longitude_flat = longitude_mesh_arr.ravel()

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
                                      orbit_xmls: list[Path] = None) -> Path:
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
                                                             orbit_xmls=orbit_xmls,
                                                             reference_or_secondary=reference_or_secondary)
    solid_earth_tide_ds.to_netcdf(gunw_path,
                                  mode='a',
                                  group=se_tide_group_acq)
    return gunw_path
