#!/usr/bin/env python3
# David Bekaert - Jet Propulsion Laboratory
# set of functions that are leveraged in the packaging of the ARIA standard product

from __future__ import division
from builtins import str
from builtins import range
import numbers
from osgeo import gdal, ogr, osr


def data_loading(filename,out_data_type=None,data_band=None):
    """
        GDAL READER of the data
        filename: the gdal readable file that needs to be loaded
        out_data_type: the datatype of the output data, default is original
        out_data_res: the resolution of the output data, default is original
        data_band: the band that needs to be loaded, default is all
    """

    import numpy
    import os

    # converting to the absolute path
    filename = os.path.abspath(filename)
    if not os.path.isfile(filename):
        print(filename + " does not exist")
        out_data = None
        return out_data

    # open the GDAL file and get typical data information
    try:
        data =  gdal.Open(filename, gdal.GA_ReadOnly)
    except:
        print(filename + " is not a gdal supported file")
        out_data = None
        return out_data

    # loading the requested band or by default all
    if data_band is not None:
        raster = data.GetRasterBand(data_band)
        out_data = raster.ReadAsArray()

    # getting the gdal transform and projection
    geoTrans = str(data.GetGeoTransform())
    projectionRef = str(data.GetProjection())

    # getting the no-data value
    try:
        NoData = data.GetNoDataValue()
        print(NoData)
    except:
        NoData = None

    # change the dataype if provided
    if out_data_type is not None:
        # changing the format if needed
        out_data = out_data.astype(dtype=out_data_type)

    return out_data, geoTrans,projectionRef, NoData



def get_conncomp(args):
    """
       return a new connected component file that is masked with a new no-data.
       original connected componet has 0 for no-data and also connected component 0
       uses first band of another dataset with 0 as no-data to apply the new no-data masking
    """

    import numpy as np
    import pdb

    vrt_file_conn = args[0]
    no_data_conn = args[1]
    vrt_file_aux = args[2]

    # load connected comp
    conn_comp_data, geoTrans,projectionRef, NoData =  data_loading(vrt_file_conn,out_data_type="float32",data_band=1)

    # load the aux file
    aux_data, geoTrans,projectionRef, no_data_aux =  data_loading(vrt_file_aux,out_data_type=None,data_band=1)
    if no_data_aux is None:
        try:
            no_data_aux = args[3]
        except:
            no_data_aux = 0.0

    # update the connected comp no-data value
    conn_comp_data[aux_data==no_data_aux]=no_data_conn

    # return a dictionary
    output_dict = {}
    output_dict['data'] = conn_comp_data
    output_dict['data_transf'] = geoTrans
    output_dict['data_proj'] = projectionRef
    output_dict['data_nodata'] = no_data_conn
    return output_dict




def get_geocoded_coords_ISCE2(args):
    """Return geo-coordinates center pixel of a GDAL readable file. Note this function is specific for ISCE 2.0 where there is an inconsistency for the pixel definition in the vrt's. Isce assumes center pixel while the coordinate and transf reconstruction required the input to be edge defined."""

    import numpy as np
    import pdb
    vrt_file = args[0]
    geovariables = args[1:]

    # extract geo-coded corner coordinates
    ds = gdal.Open(vrt_file)
    gt = ds.GetGeoTransform()
    cols = ds.RasterXSize
    rows = ds.RasterYSize

    # getting the gdal transform and projection
    geoTrans = str(ds.GetGeoTransform())
    projectionRef = str(ds.GetProjection())

    count=0
    for geovariable in geovariables:
        variable = geovariable[0]
        if variable == 'longitude' or variable == 'Longitude' or variable == 'lon' or variable == 'Lon':
            lon_arr = list(range(0, cols))
            lons = np.empty((cols,),dtype='float64')
            for px in lon_arr:
                lons[px] = gt[0] + (px * gt[1])
            count+=1
            lons_map = geovariable[1]
        elif variable == 'latitude' or variable == 'Latitude' or variable == 'lat' or variable == 'Lat':
            lat_arr = list(range(0, rows))
            lats = np.empty((rows,),dtype='float64')
            for py in lat_arr:
                lats[py] = gt[3] + (py * gt[5])
            count+=1
            lats_map = geovariable[1]
        else:
            raise Exception("arguments are either longitude or lattitude")

    # making sure both lon and lat were querried
    if count !=2:
        raise Exception("Did not provide a longitude and latitude argument")

    coordinate_dict = {}
    coordinate_dict['lons'] = lons
    coordinate_dict['lats'] = lats
    coordinate_dict['lons_map'] = lons_map
    coordinate_dict['lats_map'] = lats_map
    coordinate_dict['data_proj'] = projectionRef
    coordinate_dict['data_transf'] = geoTrans
    return coordinate_dict




def get_geocoded_coords(args):
    """Return geo-coordinates center pixel of a GDAL readable file."""

    import numpy as np
    import pdb

    vrt_file = args[0]
    geovariables = args[1:]

    # extract geo-coded corner coordinates
    ds = gdal.Open(vrt_file)
    gt = ds.GetGeoTransform()
    cols = ds.RasterXSize
    rows = ds.RasterYSize

    # getting the gdal transform and projection
    geoTrans = str(ds.GetGeoTransform())
    projectionRef = str(ds.GetProjection())

    count=0
    for geovariable in geovariables:
        variable = geovariable[0]
        if variable == 'longitude' or variable == 'Longitude' or variable == 'lon' or variable == 'Lon':
            lon_arr = list(range(0, cols))
            lons = np.empty((cols,),dtype='float64')
            for px in lon_arr:
                lons[px] = gt[0] + (gt[1] / 2) + (px * gt[1])
            count+=1
            lons_map = geovariable[1]
        elif variable == 'latitude' or variable == 'Latitude' or variable == 'lat' or variable == 'Lat':
            lat_arr = list(range(0, rows))
            lats = np.empty((rows,),dtype='float64')
            for py in lat_arr:
                lats[py] = gt[3] - (gt[5] / 2) + (py * gt[5])
            count+=1
            lats_map = geovariable[1]
        else:
            raise Exception("arguments are either longitude or lattitude")

    # making sure both lon and lat were querried
    if count !=2:
        raise Exception("Did not provide a longitude and latitude argument")

    coordinate_dict = {}
    coordinate_dict['lons'] = lons
    coordinate_dict['lats'] = lats
    coordinate_dict['lons_map'] = lons_map
    coordinate_dict['lats_map'] = lats_map
    coordinate_dict['data_proj'] = projectionRef
    coordinate_dict['data_transf'] = geoTrans
    return coordinate_dict

def get_topsApp_data(topsapp_xml='topsApp'):
    '''
        loading the topsapp xml file
    '''

    import isce
    from topsApp import TopsInSAR
    import os
    import pdb
    # prvide the full path and strip off any .xml if pressent
    topsapp_xml = os.path.splitext(os.path.abspath(topsapp_xml))[0]
    curdir = os.getcwd()
    filedir = os.path.dirname(topsapp_xml)
    filename = os.path.basename(topsapp_xml)

    os.chdir(filedir)
    #pdb.set_trace()
    insar = TopsInSAR(name = filename)
    insar.configure()
    os.chdir(curdir)
    return insar

def get_isce_version_info(args):
    import isce
    isce_version = isce.release_version
    if isce.release_svn_revision:
        isce_version = "ISCE version = " + isce_version + ", " + "SVN revision = " + isce.release_svn_revision
    return isce_version

def get_topsApp_variable(args):
    '''
        return the value of the requested variable
    '''

    import os
    import pdb
    topsapp_xml = args[0]
    variable = args[1]

    #pdb.set_trace()
    insar = get_topsApp_data(topsapp_xml)
    # ESD specific
    if variable == 'ESD':
        import numpy as np
        if insar.__getattribute__('doESD'):
            insar_temp = insar.__getattribute__('esdCoherenceThreshold')
        else:
            insar_temp = -1.0
        data = np.float(insar_temp)
    # other variables
    elif variable == 'DEM':
        import numpy as np
        print("isce_function: variable = DEM")
        if insar.__getattribute__('demFilename'):
            insar_temp = insar.__getattribute__('demFilename')
            print("isce_function: demFilename Found. insar_temp : %s" %insar_temp)
            if insar_temp.startswith("NED"):
                data = "NED"
            else:
                data = "SRTM"

        else:
            print("isce_function : demFilename NOT Found. Defaulting to SRTM")
            data = "SRTM"
    else:
        # tops has issues with calling a nested variable, will need to loop over it
        variables = variable.split('.')
        insar_temp = insar
        for variable in variables:
            insar_temp = insar_temp.__getattribute__(variable)
        data = insar_temp

    # further processing if needed
    # removing any paths and only re-ruturning a list of files
    if variable == 'safe':
        data  = [os.path.basename(SAFE) for SAFE in data]

    return data



def get_tops_subswath_xml(masterdir):
    '''
        Find all available IW[1-3].xml files
    '''

    import os
    import glob

    masterdir = os.path.abspath(masterdir)
    IWs = glob.glob(os.path.join(masterdir,'IW*.xml'))
    if len(IWs)<1:
        raise Exception("Could not find a IW*.xml file in " + masterdir)
    return IWs


def get_h5_dataset_coords(args):
    '''
       Getting the coordinates from the meta hdf5 file which is longitude, latitude and height
    '''
    import pdb
    h5_file = args[0]
    geovariables = args[1:]

    # loop over the variables and track the variable names
    count=0
    for geovariable in geovariables:
        variable = geovariable[0]
        varname = variable.split('/')[-1]
        if varname == 'longitude' or varname == 'Longitude' or varname == 'lon' or varname == 'Lon' or  varname == 'lons' or varname == 'Lons':
            lons = get_h5_dataset([h5_file,variable])
            count+=1
            lons_map = geovariable[1]
        elif varname == 'latitude' or varname == 'Latitude' or varname == 'lat' or varname == 'Lat' or  varname == 'lats' or varname == 'Lats':
            lats = get_h5_dataset([h5_file,variable])
            count+=1
            lats_map = geovariable[1]
        elif varname == 'height' or varname == 'Height' or varname == 'h' or varname == 'H' or  varname == 'heights' or varname == 'Heights':
            hgts = get_h5_dataset([h5_file,variable])
            count+=1
            hgts_map = geovariable[1]
        else:
            raise Exception("arguments are either longitude, lattitude, or height")

    # making sure both lon and lat were querried
    if count !=3:
        raise Exception("Did not provide a longitude and latitude argument")


    #pdb.set_trace()
    # getting the projection string
    try:
        proj4 = get_h5_dataset([h5_file,"/inputs/projection"])
    except:
        try:
            proj4 = get_h5_dataset([h5_file,"/projection"])
        except:
            raise Exception

    proj4 = proj4.astype(dtype='str')[0]
    proj4 = int(proj4.split(":")[1])
    from osgeo import osr
    ref = osr.SpatialReference()
    ref.ImportFromEPSG(proj4)
    projectionRef = ref.ExportToWkt()

    coordinate_dict = {}
    coordinate_dict['lons'] = lons.astype(dtype='float64')
    coordinate_dict['lats'] = lats.astype(dtype='float64')
    coordinate_dict['hgts'] = hgts.astype(dtype='float64')
    coordinate_dict['lons_map'] = lons_map
    coordinate_dict['lats_map'] = lats_map
    coordinate_dict['hgts_map'] = hgts_map
    coordinate_dict['data_proj'] = projectionRef
    return coordinate_dict



def get_h5_dataset(args):
    '''
        Extracts a hdf5 variable and return the content of it
        INPUTS:
        filename    str of the hdf5 file
        variable    str describing the path within the hdf5 file: e.g. cube/dataset1
    '''

    import h5py
    import numpy as np

    file_name=  args[0]
    path_variable = args[1]
    datafile = h5py.File(file_name,'r')
    data = datafile[path_variable][:][::-1]

    return data


def get_tops_metadata_variable(args):
    '''
        return the value of the requested variable
    '''
    masterdir = args[0]
    variable = args[1]
    tops_metadata = get_tops_metadata(masterdir)
    data = tops_metadata[variable]

    return data

def get_tops_metadata(masterdir):
    import pdb
    from scipy.constants import c

    # get a list of avialble xml files for IW*.xml
    IWs = get_tops_subswath_xml(masterdir)

    # append all swaths togheter
    frames=[]
    for IW  in IWs:
        obj = read_isce_product(IW)
        frames.append(obj)

    output={}
    dt = min(frame.sensingStart for frame in frames)
    output['sensingStart'] =  dt.isoformat('T') + 'Z'
    dt = max(frame.sensingStop for frame in frames)
    output['sensingStop'] = dt.isoformat('T') + 'Z'
    output['farRange'] = max(frame.farRange for frame in frames)
    output['startingRange'] = min(frame.startingRange for frame in frames)
    output['spacecraftName'] = obj.spacecraftName
    burst = obj.bursts[0]
    output['rangePixelSize'] = burst.rangePixelSize
    output['azimuthTimeInterval'] = burst.azimuthTimeInterval
    output['wavelength'] = burst.radarWavelength
    output['frequency']  = (c / output['wavelength'])
    if "POEORB" in obj.orbit.getOrbitSource():
        output['orbittype'] = "precise"
    elif "RESORB" in obj.orbit.getOrbitSource():
        output['orbittype'] = "restituted"
    else:
        output['orbittype'] = ""
    #output['bbox'] = get_bbox(masterdir)
    # geo transform grt for x y
    # bandwith changes per swath - placeholder c*b/2 or delete
    # tops xml file
    # refer to safe files frame doppler centroid burst[middle].doppler
    # extract from topsapp.xml

    return output



def check_file_exist(infile):
    import os
    if not os.path.isfile(infile):
        raise Exception(infile + " does not exist")

def read_isce_product(xmlfile):
    import os
    import isce
    from iscesys.Component.ProductManager import ProductManager as PM

    # check if the file does exist
    check_file_exist(xmlfile)

    # loading the xml file with isce
    pm = PM()
    pm.configure()
    obj = pm.loadProduct(xmlfile)

    return obj

def get_orbit():
    from isceobj.Orbit.Orbit import Orbit

    """Return orbit object."""

    orb = Orbit()
    orb.configure()
    return orb

def get_aligned_bbox(prod, orb):
    """Return estimate of 4 corner coordinates of the
       track-aligned bbox of the product."""
    import numpy as np
    import os

    # create merged orbit
    burst = prod.bursts[0]

    #Add first burst orbit to begin with
    for sv in burst.orbit:
         orb.addStateVector(sv)

    ##Add all state vectors
    for bb in prod.bursts:
        for sv in bb.orbit:
            if (sv.time< orb.minTime) or (sv.time > orb.maxTime):
                orb.addStateVector(sv)
        bb.orbit = orb

    # extract bbox
    ts = [prod.sensingStart, prod.sensingStop]
    rngs = [prod.startingRange, prod.farRange]
    pos = []
    for tim in ts:
        for rng in rngs:
            llh = prod.orbit.rdr2geo(tim, rng, height=0.)
            pos.append(llh)
    pos = np.array(pos)
    bbox = pos[[0, 1, 3, 2], 0:2]
    return bbox.tolist()

def get_loc(box):
    """Return GeoJSON bbox."""
    import numpy as np
    import os

    bbox = np.array(box).astype(np.float)
    coords = [
        [ bbox[0,1], bbox[0,0] ],
        [ bbox[1,1], bbox[1,0] ],
        [ bbox[2,1], bbox[2,0] ],
        [ bbox[3,1], bbox[3,0] ],
        [ bbox[0,1], bbox[0,0] ],
    ]
    return {
        "type": "Polygon",
        "coordinates":  [coords]
    }

def get_env_box(env):

    #print("get_env_box env " %env)
    bbox = [
        [ env[3], env[0] ],
        [ env[3], env[1] ],
        [ env[2], env[1] ],
        [ env[2], env[0] ],
    ]
    print("get_env_box box : %s" %bbox)
    return bbox


def get_union_geom(bbox_list):
    import json

    geom_union = None
    for bbox in bbox_list:
        loc = get_loc(bbox)
        geom = ogr.CreateGeometryFromJson(json.dumps(loc))
        print("get_union_geom : geom : %s" %get_union_geom)
        if geom_union is None:
            geom_union = geom
        else:
            geom_union = geom_union.Union(geom)
    print("geom_union_type : %s" %type(geom_union))
    return geom_union

def get_area(coords):
    '''get area of enclosed coordinates- determines clockwise or counterclockwise order'''
    n = len(coords) # of corners
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += coords[i][1] * coords[j][0]
        area -= coords[j][1] * coords[i][0]
    #area = abs(area) / 2.0
    return (area / 2)

def change_direction(coords):
    cord_area= get_area(coords)
    if not get_area(coords) > 0: #reverse order if not clockwise
        print("update_met_json, reversing the coords")
        coords = coords[::-1]
    return coords

def get_raster_corner_coords(vrt_file):
    """Return raster corner coordinates."""
    import os

    # go to directory where vrt exists to extract from image
    cwd =os.getcwd()
    data_dir = os.path.dirname(os.path.abspath(vrt_file))
    os.chdir(data_dir)

    # extract geo-coded corner coordinates
    ds = gdal.Open(os.path.basename(vrt_file))
    gt = ds.GetGeoTransform()
    cols = ds.RasterXSize
    rows = ds.RasterYSize
    ext = []
    lon_arr = [0, cols]
    lat_arr = [0, rows]
    for px in lon_arr:
        for py in lat_arr:
            lon = gt[0] + (px * gt[1]) + (py * gt[2])
            lat = gt[3] + (px * gt[4]) + (py * gt[5])
            ext.append([lat, lon])
        lat_arr.reverse()
    os.chdir(cwd)
    return ext


def get_bbox(args):
    import json
    import os
    import pdb

    cur_dir = os.path.dirname(os.path.abspath(__file__))
    cur_wd = os.getcwd()
    master_dir= args[0]

    print("isce_functions : get_bbox: %s : %s : %s" %(cur_dir, cur_wd, master_dir))
    bboxes = []
    master_dir = args[0]

    IWs = get_tops_subswath_xml(master_dir)
    print("isce_functions : get_bbox : after get_tops_subswath_xml : %s" %len(IWs))
    for IW in IWs:
        try:
            prod = read_isce_product(IW)
            print("isce_functions: after prod")
            orb = get_orbit()
            print("isce_functions : orb")
            bbox_swath = get_aligned_bbox(prod, orb)
            print("isce_functions : bbox_swath : %s" %bbox_swath)
            bboxes.append(bbox_swath)
        except Exception as e:
            print("isce_functions : Failed to get aligned bbox: %s" %str(e))
            #print("Getting raster corner coords instead.")
            #bbox_swath = get_raster_corner_coords(vrt_file)

    geom_union = get_union_geom(bboxes)
    print("isce_functions : geom_union : %s" %geom_union)
    # return the polygon as a list of strings, which each poly a list argument
    geom_union_str = ["%s"%geom_union]
    return geom_union_str



