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
    assert(Path(xml_path).exists())
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
    isce_apps_path = site.getsitepackages()[0] + '/isce/applications'
    fix_cmd = [f'{isce_apps_path}/fixImageXml.py',
               '-i',
               str(isce_raster_path),
               '--full']
    fix_cmd_line = ' '.join(fix_cmd)
    subprocess.check_call(fix_cmd_line, shell=True)
    return isce_raster_path


def download_dem_for_isce2(extent: list,
                           dem_name: str = 'glo_30',
                           full_res_dem_dir: Path = None,
                           low_res_dem_dir: Path = None,
                           buffer: float = .004) -> dict:
    """
    Parameters
    ----------
    extent : list
        [xmin, ymin, xmax, ymin] for epsg:4326 (i.e. (x, y) = (lon, lat))
    dem_name : str, optional
        See names in `dem_stitcher`
    full_res_dem_dir : Path, optional
    low_res_dem_dir : Path, optional
    buffer : float, optional
        In degrees, by default .004, which is .5 km at equator
    Returns
    -------
    dict
    """
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
                                        max_workers=5,
                                        # ensures square resolution
                                        dst_resolution=dem_res
                                        )

    full_res_dem_path = full_res_dem_dir / 'full_res.dem.wgs84'
    dem_array[np.isnan(dem_array)] = 0.
    dem_profile['nodata'] = None
    dem_profile['driver'] = 'ISCE'
    with rasterio.open(full_res_dem_path, 'w', **dem_profile) as ds:
        ds.write(dem_array, 1)

    geocode_res = dem_res * 3
    dst_profile = update_profile_resolution(dem_profile, geocode_res)
    dem_geocode_arr, dem_geocode_profile = reproject_arr_to_match_profile(dem_array,
                                                                          dem_profile,
                                                                          dst_profile,
                                                                          num_threads=5,
                                                                          resampling='bilinear')
    dem_geocode_arr = dem_geocode_arr[0, ...]
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
