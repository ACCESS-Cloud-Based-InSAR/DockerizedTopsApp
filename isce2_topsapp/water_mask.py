import numpy as np
from dem_stitcher.rio_tools import reproject_arr_to_match_profile
from rasterio.transform import array_bounds
from tile_mate import get_raster_from_tiles


def get_water_mask_raster_for_browse_image(profile: dict) -> np.ndarray:
    """
    Water mask where True indicates water. Uses GSHHS_f_L1 with 3km hosted
    by ASF.

    Parameters
    ----------
    profile : dict
        Rasterio profile

    Returns
    -------
    np.ndarray
        Water mask (boolean) with True indicated water
    """
    extent = array_bounds(profile["height"], profile["width"], profile["transform"])

    X_esa, p_esa = get_raster_from_tiles(extent, tile_shortname="esa_world_cover_2021")
    X_esa_r, _ = reproject_arr_to_match_profile(X_esa, p_esa, profile, resampling='nearest')
    mask = (X_esa_r == 80).astype(bool)
    mask = mask[0, ...]
    return mask
