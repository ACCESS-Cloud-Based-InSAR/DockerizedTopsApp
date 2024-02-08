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

    X_occ, p_occ = get_raster_from_tiles(extent, tile_shortname="peckel_water_occ_2021")
    X_occ_r, _ = reproject_arr_to_match_profile(X_occ, p_occ, profile, resampling='bilinear')
    mask = (X_occ_r >= 95).astype(bool)
    mask = mask[0, ...]
    return mask
