import site
import subprocess
from pathlib import Path

import numpy as np
import rasterio
from dem_stitcher.rio_tools import (reproject_arr_to_match_profile,
                                    update_profile_resolution)
from dem_stitcher.stitcher import stitch_dem
from lxml import etree
from shapely.geometry import box


def tag_dem_xml_as_ellipsoidal(dem_path: Path) -> str:
    xml_path = str(dem_path) + '.xml'
    assert Path(xml_path).exists()
    tree = etree.parse(xml_path)
    root = tree.getroot()

    y = etree.Element("property", name='reference')
    etree.SubElement(y, "value").text = "WGS84"
    etree.SubElement(y, "doc").text = "Geodetic datum"

    root.insert(0, y)
    with open(xml_path, 'wb') as file:
        file.write(etree.tostring(root, pretty_print=True))
    return xml_path


def fix_image_xml(isce_raster_path: str) -> str:
    fix_cmd = [f'fixImageXml.py',
               '-i',
               str(isce_raster_path),
               '--full']
    fix_cmd_line = ' '.join(fix_cmd)
    subprocess.check_call(fix_cmd_line, shell=True)
    return isce_raster_path


def download_dem_for_isce2(extent: list,
                           dem_name: str = 'glo_30',
                           geocode_resolution: int = 90,
                           full_res_dem_dir: Path = None,
                           low_res_dem_dir: Path = None,
                           buffer: float = .4) -> dict:
    """
    Parameters
    ----------
    extent : list
        [xmin, ymin, xmax, ymax] for epsg:4326 (i.e. (x, y) = (lon, lat))
    dem_name : str, optional
        See names in `dem_stitcher`
    full_res_dem_dir : Path, optional
    low_res_dem_dir : Path, optional
    buffer : float, optional
        In degrees, by default .4, which is about 44 km at equator (or about 2.5 bursts at the equator)
    Returns
    -------
    dict
    """
    if geocode_resolution not in [30, 90]:
        raise ValueError('Geocode resolution must be "30" or "90"')

    full_res_dem_dir = full_res_dem_dir or Path('.')
    low_res_dem_dir = low_res_dem_dir or Path('.')

    full_res_dem_dir.mkdir(exist_ok=True, parents=True)
    low_res_dem_dir.mkdir(exist_ok=True, parents=True)

    extent_geo = box(*extent)
    extent_buffered = list(extent_geo.buffer(buffer).bounds)
    extent_buffered = [np.floor(extent_buffered[0]), np.floor(extent_buffered[1]),
                       np.ceil(extent_buffered[2]), np.ceil(extent_buffered[3])]

    dem_res = 0.0002777777777777777775
    dem_array, dem_profile = stitch_dem(extent_buffered,
                                        dem_name,
                                        dst_ellipsoidal_height=True,
                                        dst_area_or_point='Point',
                                        n_threads_downloading=5,
                                        # ensures square resolution
                                        dst_resolution=dem_res
                                        )

    full_res_dem_path = full_res_dem_dir / 'full_res.dem.wgs84'
    dem_array[np.isnan(dem_array)] = 0.

    dem_profile_isce = dem_profile.copy()
    dem_profile_isce['nodata'] = None
    dem_profile_isce['driver'] = 'ISCE'
    # remove keys that do not work with ISCE gdal format
    [dem_profile_isce.pop(key) for key in ['blockxsize', 'blockysize', 'compress', 'interleave', 'tiled']]

    with rasterio.open(full_res_dem_path, 'w', **dem_profile_isce) as ds:
        ds.write(dem_array, 1)

    # Standard GUNW
    if geocode_resolution == 90:
        geocode_res = dem_res * 3

        dst_profile = update_profile_resolution(dem_profile_isce, geocode_res)
        dem_geocode_arr, dem_geocode_profile = reproject_arr_to_match_profile(dem_array,
                                                                              dem_profile_isce,
                                                                              dst_profile,
                                                                              num_threads=5,
                                                                              resampling='bilinear')
        dem_geocode_arr = dem_geocode_arr[0, ...]

    else:
        # if 30 meters the array and geometadata should be the same
        dem_geocode_arr = dem_array
        dem_geocode_profile = dem_profile.copy()

    low_res_dem_path = low_res_dem_dir / 'low_res.dem.wgs84'

    dem_geocode_profile['driver'] = 'ISCE'
    with rasterio.open(low_res_dem_path, 'w', **dem_geocode_profile) as ds:
        ds.write(dem_geocode_arr, 1)

    low_res_dem_xml = tag_dem_xml_as_ellipsoidal(low_res_dem_path)
    full_res_dem_xml = tag_dem_xml_as_ellipsoidal(full_res_dem_path)

    fix_image_xml(low_res_dem_xml)
    fix_image_xml(full_res_dem_xml)

    return {'extent_buffered': extent_buffered,
            'full_res_dem_path': full_res_dem_path,
            'low_res_dem_path': low_res_dem_path}
