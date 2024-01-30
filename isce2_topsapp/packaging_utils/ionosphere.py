from pathlib import Path

import numpy as np
import rasterio
from dem_stitcher.rio_tools import (reproject_arr_to_match_profile,
                                    update_profile_resolution)


def format_ionosphere_for_gunw(isce_directory: Path,
                               gunw_netcdf_path: Path) -> Path:
    """Resamples the ionosphere to approximately 1 km using origin of product

    Parameters
    ----------
    isce_directory : Path
        The so-called "scratch" directory
    gunw_netcdf_path : Path

    Returns
    -------
    Path
        gunw_path
    """
    with rasterio.open(isce_directory / "merged/topophase.ion.geo") as ds:
        X_ion = ds.read(1)
        p_ion = ds.profile

    X_ion[X_ion == 0] = np.nan
    p_ion['nodata'] = np.nan

    # Get GUNW Mask
    nc_path_str = (f'netcdf:{gunw_netcdf_path}:'
                   '/science/grids/data/connectedComponents')
    with rasterio.open(nc_path_str) as ds:
        cc = ds.read(1)
        p_cc = ds.profile
    mask = (cc == -1).astype(np.int32)

    # Lower resolution by factor of 11 to approximatly 990 m at equator
    p_ion_low_res = update_profile_resolution(p_ion, 0.0091666666)
    X_ion_low_res, _ = reproject_arr_to_match_profile(X_ion,
                                                      p_ion,
                                                      p_ion_low_res,
                                                      resampling='bilinear')
    p_cc['nodata'] = None
    p_cc['dtype'] = np.int32
    mask_low_res, _ = reproject_arr_to_match_profile(mask,
                                                     p_cc,
                                                     p_ion_low_res,
                                                     resampling='nearest')

    X_ion_low_res = X_ion_low_res[0, ...]
    mask_low_res = mask_low_res[0, ...].astype(bool)
    X_ion_low_res[mask_low_res] = np.nan

    out_path = isce_directory / 'merged/ionosphere_for_gunw.geo'
    with rasterio.open(out_path, 'w', **p_ion_low_res) as ds:
        ds.write(X_ion_low_res, 1)

    return out_path


def format_iono_burst_ramps(isce_directory: Path,
                            gunw_netcdf_path: Path) -> Path:
    # open long-wavelength ionosphere layer
    with rasterio.open(isce_directory / "merged/topophase.ion.geo") as ds:
        X_ion = ds.read(1)
        p_ion = ds.profile

    X_ion[X_ion == 0] = np.nan
    p_ion['nodata'] = np.nan

    # open burstRamps layer
    with rasterio.open(isce_directory / "merged/topophase.ion.az_shift.geo") as ds:
        X_ramps = ds.read(1)
    X_ramps[X_ramps == 0] = np.nan

    # Get burst ramps without long-wavength ionospheric delay
    X_ramps -= X_ion

    out_path = isce_directory / 'merged/ionosphereBurstRamps_for_gunw.geo'
    with rasterio.open(out_path, 'w', **p_ion) as ds:
        ds.write(X_ramps, 1)

    return out_path
