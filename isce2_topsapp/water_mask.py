import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio import features
from rasterio.transform import array_bounds
from typing import Union


def rasterize_shapes_to_array(shapes: list,
                              attributes: list,
                              profile: dict,
                              all_touched: bool = False,
                              dtype: str = 'float32',
                              fill_value: Union[float, int] = 0) -> np.ndarray:
    """
    Takes a list of geometries and attributes to create an array. For example,
    `shapes = df.geometry` and `attributes = df.label`, where df is a geopandas
    GeoDataFrame. We note the array is initialized as array of zeros.

    Parameters
    ----------
    shapes : list
        List of Shapely geometries.
    attributes : list
        List of attributes corresponding to shapes.
    profile : dict
        Rasterio profile in which shapes will be projected into, importantly
        the transform and dimensions specified.
    all_touched : bool
        Whether factionally covered pixels are written with specific value or
        ignored. See `rasterio.features.rasterize`.
    dtype : str
        The initial array is np.zeros and dtype can be specified as a numpy
        dtype or appropriate string.
    Returns
    -------
    np.ndarray:
        The output array determined with profile.
    """
    out_arr = np.full((profile['height'], profile['width']),
                      fill_value=fill_value,
                      dtype=dtype)

    # this is where we create a generator of geom, value pairs to use in
    # rasterizing
    shapes = [(geom, value) for geom, value in zip(shapes, attributes)]
    burned = features.rasterize(shapes=shapes,
                                out=out_arr,
                                transform=profile['transform'],
                                all_touched=all_touched)

    return burned


def get_water_mask_dataframe(bounds: list) -> gpd.GeoDataFrame:
    mask_location = ('/vsicurl/https://asf-dem-west.s3.amazonaws.com/'
                     'WATER_MASK/GSHHG/GSHHS_f_L1.shp')

    if (bounds[0] < -200) or (bounds[1] > 200):
        raise ValueError('The bounds need to be within -200 and 200')

    # If crosses over the dateline
    if (bounds[0] < -180) or (bounds[2] > 180):
        bounds_e = list(bounds)
        bounds_w = list(bounds)

        # Grab both sides of dateline and then translate back
        if (bounds[0] < -180):
            bounds_e[0] += 360
            bounds_e[2] += 360
            df_e = gpd.read_file(mask_location, bbox=bounds_e)
            df_w = gpd.read_file(mask_location, bbox=bounds_w)
            df_e.geometry = df_e.geometry.translate(xoff=-360)

        else:  # bounds[2] > 180
            bounds_w[0] -= 360
            bounds_w[2] -= 360
            df_e = gpd.read_file(mask_location, bbox=bounds_e)
            df_w = gpd.read_file(mask_location, bbox=bounds_w)
            df_w.geometry = df_w.geometry.translate(xoff=360)

        df = pd.concat([df_e, df_w], axis=0)

    else:
        df = gpd.read_file(mask_location, bbox=bounds)

    return df


def get_water_mask_raster(profile: dict) -> np.ndarray:
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
    bounds = array_bounds(profile['height'],
                          profile['width'],
                          profile['transform'])
    crs = profile['crs']
    df = get_water_mask_dataframe(bounds).to_crs(crs)

    geometries = df.geometry
    land_values = [0] * df.shape[0]
    X = rasterize_shapes_to_array(geometries,
                                  land_values,
                                  profile,
                                  fill_value=1,
                                  dtype='uint8',
                                  all_touched=False)
    return X.astype(bool)
