from lxml import etree
import rasterio
from shapely.geometry import box
from dem_stitcher.stitcher import stitch_dem
from dem_stitcher.rio_tools import resample_by_multiple
from pathlib import Path
import subprocess
import site
import numpy as np


def tag_dem_xml_as_ellipsoidal(dem_path: Path) -> str:
    xml_path = str(dem_path) + '.xml'
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
    import os
    import glob
    import shutil
    from osgeo import gdal
    
    full_res_dem_dir = full_res_dem_dir or Path('.')
    low_res_dem_dir = low_res_dem_dir or Path('.')

    full_res_dem_dir.mkdir(exist_ok=True, parents=True)
    low_res_dem_dir.mkdir(exist_ok=True, parents=True)

    extent_geo = box(*extent)
    extent_buffered = list(extent_geo.buffer(buffer).bounds)
    extent_buffered = list(map(lambda e: round(e, 3), extent_buffered))
    
    full_res_dem_path = full_res_dem_dir/'full_res.dem.wgs84'
    full_res_dem_path = str(full_res_dem_path.resolve())
    stitch_dem(extent_buffered,
                       dem_name,
                       full_res_dem_path,
                       dst_ellipsoidal_height=True,
                       dst_area_or_point='Point',
                       max_workers=5)
                       
    # downsample to 3-arc sec
    downsamp_res = gdal.Open(full_res_dem_path).GetGeoTransform()[1]
    downsamp_res *= 3
    low_res_dem_path = (low_res_dem_dir/'low_res.dem.wgs84')
    low_res_dem_path = str(low_res_dem_path.resolve())
    gdal.Warp(low_res_dem_path, full_res_dem_path, \
                     options=gdal.WarpOptions(format = 'ISCE', \
                     xRes = downsamp_res, \
                     yRes = downsamp_res, \
                     targetAlignedPixels = True, \
                     multithread = True))
    # Update VRT
    gdal.BuildVRT(low_res_dem_path+'.vrt', low_res_dem_path, \
                            options=gdal.BuildVRTOptions(options=['-overwrite']))

    low_res_dem_xml = tag_dem_xml_as_ellipsoidal(low_res_dem_path)
    full_res_dem_xml = tag_dem_xml_as_ellipsoidal(full_res_dem_path)

    shutil.copyfile(full_res_dem_path+'.vrt', full_res_dem_path+'.vrt_OG')
    shutil.copyfile(low_res_dem_path+'.vrt', low_res_dem_path+'.vrt_OG')
    fix_image_xml(low_res_dem_xml)
    fix_image_xml(full_res_dem_xml)
    # circumvent VRT bug
    os.rename(full_res_dem_path+'.vrt_OG', full_res_dem_path+'.vrt')
    os.rename(low_res_dem_path+'.vrt_OG', low_res_dem_path+'.vrt')

    return {'extent_buffered': extent_buffered,
            'full_res_dem_path': full_res_dem_path,
            'low_res_dem_path': low_res_dem_path}
