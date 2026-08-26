import numpy as np
from dem_stitcher.rio_tools import reproject_arr_to_match_profile
from rasterio.transform import array_bounds
from scipy.ndimage import binary_dilation
from tile_mate import get_raster_from_tiles


# JRC/Pekel water occurrence is a percentage in [0, 100] with 255 reserved for no-data.
# Open ocean dithers between ~90 and 100 along Landsat WRS-2 scene edges, so a threshold
# of 95 carves scalloped holes out of the sea; anything <= 90 gives a solid ocean.
PEKEL_OCCURRENCE_THRESHOLD = 90
PEKEL_NODATA = 255
# No-data blocks sit offshore and carry a thin rim of 0-occurrence pixels along their
# edge, which reads as land and draws hairline seams through the sea. Growing the
# no-data region a few pixels swallows the rim without touching the coastline.
PEKEL_NODATA_DILATION = 3


def water_mask_from_occurrence(occurrence: np.ndarray, nodata_dilation: int = PEKEL_NODATA_DILATION) -> np.ndarray:
    nodata = occurrence == PEKEL_NODATA
    mask = ((occurrence >= PEKEL_OCCURRENCE_THRESHOLD) & ~nodata) | nodata
    if nodata_dilation:
        mask |= binary_dilation(nodata, iterations=nodata_dilation)
    return mask


def get_water_mask_raster_for_browse_image(profile: dict) -> np.ndarray:
    """
    Water mask where True indicates water.

    Derived from JRC/Pekel water occurrence 2021.

    Parameters
    ----------
    profile : dict
        Rasterio profile

    Returns
    -------
    np.ndarray
        Water mask (boolean) with True indicated water
    """
    extent = array_bounds(profile['height'], profile['width'], profile['transform'])

    X_occ, p_occ = get_raster_from_tiles(extent, tile_shortname='pekel_water_occ_2021')
    # nearest keeps the 255 no-data code intact; bilinear averages it into valid
    # occurrence values and paints a spurious water halo around every no-data edge
    X_occ_r, _ = reproject_arr_to_match_profile(X_occ, p_occ, profile, resampling='nearest')
    return water_mask_from_occurrence(X_occ_r[0, ...])
