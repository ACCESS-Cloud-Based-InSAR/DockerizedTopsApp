# Author: David Bekaert - Jet Propulsion Laboratory

from builtins import map
from builtins import str
from builtins import range
from builtins import object
import argparse
import json
import logging
import traceback
from collections import OrderedDict
import os
from netCDF4 import Dataset
import numpy as np
from osgeo import gdal
from osgeo import osr
import collections.abc

log_format = "[%(asctime)s: %(levelname)s/%(funcName)s] %(message)s"
logging.basicConfig(format=log_format, level=logging.INFO)
logger = logging.getLogger('standard_product_packaging')

BASE_PATH = os.path.dirname(__file__)


class content_properties(object):
    names = ('type','src_file','nodata','chunks','band','description',
             'dims','python_action','python_action_args','attribute',
             'description','name','crs_name','crs_attribute','data_type','global_attribute')

    def __init__(self,dataset):
        for property_name in self.names:
            setattr(self,property_name,extract_key(dataset,property_name))


def netdf4_dtype_check(dtype):
    """
        only allow the dtypes that netcdf4 supports
	make it all upcase and then pass through a dict

    NC_BYTE 8-bit signed integer
    NC_UBYTE 8-bit unsigned integer
    NC_CHAR 8-bit character byte
    NC_SHORT 16-bit signed integer
    NC_USHORT 16-bit unsigned integer *
    NC_INT (or NC_LONG) 32-bit signed integer
    NC_UINT 32-bit unsigned integer *
    NC_INT64 64-bit signed integer *
    NC_UINT64 64-bit unsigned integer *
    NC_FLOAT 32-bit floating point
    NC_DOUBLE 64-bit floating point
    NC_STRING variable length character string +

    NUMPY2NETCDF4_DATATYPE = {
       1 : 'BYTE',
       2 : 'uint16',
       3 : 'SHORT',
       4 : 'uint32',
       5 : 'INT',
       6 : 'FLOAT',
       7 : 'DOUBLE',
       10: 'CFLOAT',
       11: 'complex128',
    """

    logger.info("testing")


def create_group(fid,group,fid_parent=None):
    '''
       Create a group within the fid
    '''

    name = group["name"]
    contents = group["content"]

    # create a group with the provided name
    grp_id = fid.createGroup(name)

    # track the parent fid
    if fid_parent is None:
        fid_parent = fid

    for content in contents:
        dataset_flag = extract_key(content,"dataset")
        group_flag = extract_key(content,"group")
        if dataset_flag is not None:
            for dataset in content["dataset"]:
                create_dataset(grp_id,dataset,fid_parent)
        if group_flag is not None:
            for subgroup in content["group"]:
                create_group(grp_id,subgroup,fid_parent)


def python_execution(python_string,python_args=None):
    '''
        Executing a python function using a module.function string and provided arguments
    '''
    import importlib

    # split the the python string in a python module and python function
    python_string_list = python_string.split('.')
    n = len(python_string_list)
    python_module_nested = python_string_list[: (n-1)]
    python_module = '.'.join(python_module_nested)
    python_function = python_string_list[-1]

    # loading the python module
    module = importlib.import_module(python_module)
    # loading the function
    function = module.__getattribute__(python_function)
    # execute function with arguments
    if python_args is not None:
        output = function(python_args)
    else:
        output = function()

    return output


def write_dataset(fid,data,properties_data):
    '''
        Writing out the data in netcdf arrays or strings depending on the type of data or polygons depending on the data_type.
    '''
    # for now only support polygon for vector
    if False:
        print("nothing")
    # this is either string or dataset option
    else:

        if isinstance(data,str):
            dset = fid.createVariable(properties_data.name, str, ('matchup',), zlib=True)
            dset[0]=data
        elif isinstance(data,np.ndarray):
            # make sure the _fillvalue is formatted the same as the data_type
            if properties_data.type is None:
                properties_data.type = data.dtype.name
            if properties_data.nodata is not None:
                nodata = np.array(properties_data.nodata,dtype=properties_data.type)
            else:
                nodata = None


            if len(properties_data.dims)==1:
                dset = fid.createVariable(properties_data.name, properties_data.type, (properties_data.dims[0]), fill_value=nodata, zlib=True)
            elif len(properties_data.dims)==2:
                dset = fid.createVariable(properties_data.name, properties_data.type, (properties_data.dims[0], properties_data.dims[1]), fill_value=nodata, zlib=True)
            elif len(properties_data.dims)==3:
                dset = fid.createVariable(properties_data.name, properties_data.type, (properties_data.dims[0],properties_data.dims[1], properties_data.dims[2]), fill_value=nodata, zlib=True)
            elif properties_data.dims is None:
                dset = fid.createVariable(properties_data.name, properties_data.type)
            dset[:] = data
        elif isinstance(data, collections.abc.Iterable):
            if isinstance(data[0],str):
                dset = fid.createVariable(properties_data.name, str, ('matchup',), zlib=True)
                count = 0
                for data_line in data:
                    dset[count]=data_line
                    logger.info(properties_data.name + " count = " + str(count) + '  ' + data_line)

                    count =+1
            else:
                logger.info('i am a collection, not yet programmed')
        elif data is None:
            logger.info("Action failed...")
            dset = None
        else:
            data = np.array([data])
            if properties_data.type is None:
                properties_data.type='float32'
            #dset = fid.createVariable(properties_data.name,properties_data.type,('matchup',),fill_value=-9999., zlib=True)
            dset = fid.createVariable(properties_data.name,properties_data.type)
            dset[:] = data
        # adding attributes if inputted
        if properties_data.attribute is not None and dset is not None:
            add_attributes(dset,properties_data.attribute)


def expand_attrdict(attr_dict, attr_name, attr_value):
    '''
         expand an attribute dict with more keys and values
         Update the attribute dictionary if original key is used again with a new value
    '''

    #pdb.set_trace()
    if attr_dict is None:
        attr_dict = {}

    for count in range(len(attr_name)):
        attr_temp = {}
        attr_temp["name"]=attr_name[count]
        attr_temp["value"]=attr_value[count]

        # adding it to the original dictionary
        if len(attr_dict)==0:
            attr_dict = [attr_temp]
        else:
            # looping over all the attributes to see if the name already is in use
            count_dict = 0
            name_match = None
            for attr_dict_item in attr_dict:
                if attr_dict_item["name"] == attr_temp["name"]:
                    name_match = count_dict
                count_dict = count_dict +1
            # if a match was found needs to update the attribute information
            if name_match is not None:
                attr_dict[name_match]=attr_temp
            else:
                attr_dict.append(attr_temp)

    return attr_dict

def create_dataset(fid,dataset,fid_parent=None):
    """
        Creating a dataset, either a gdal readable file, or a string, or an action
    """

    import copy

    name = dataset["name"]
    logger.info("dataset name = " + name)

    # extracting the data properties
    properties_data = content_properties(dataset)

    # Considering the different data parsing methods
    # running a python function
    if properties_data.python_action is not None:
       data = python_execution(properties_data.python_action,properties_data.python_action_args)

    # loading data from a src file
    elif properties_data.src_file is not None:

       # loading the data
       data, data_transf, data_proj, data_nodata = data_loading(properties_data.src_file,properties_data.type,properties_data.band)

       # setting the no-data value in case the user is not overwriting it
       if data_nodata is not None and properties_data.nodata is None:
           properties_data.nodata = data_nodata
       # check if the user is not over-writing the no-data value with something different.
       elif data_nodata is not None and properties_data.nodata is not None:
           data[data==data_nodata]=properties_data.nodata

    # data is a string
    elif properties_data.type == "str":
       if properties_data.description is not None:
           data = properties_data.description


    # special case to parse the connected component data
    if properties_data.name.lower()=="connected_components" or properties_data.name.lower() =="connectedcomponents" or properties_data.name.lower() =="coherence":
        # setting the no-data value in case the user is not overwriting it
        if data["data_nodata"] is not None and properties_data.nodata is None:
            properties_data.nodata = data["data_nodata"]
        # check if the user is not over-writing the no-data value with something different.
        elif data["data_nodata"] is not None and properties_data.nodata is not None:
            temp = data["data"]
            temp[temp==data["data_nodata"]]=properties_data.nodata
            data["data"] = temp

        # extract again the actual data to be written to file
        data = data["data"]

        # check if there is an additional mapping that needs to be done as for the python function this is not done directly
        # change the dataype if provided
        if properties_data.type is not None:
            # changing the format if needed
            data = data.astype(dtype=properties_data.type)

    # tracking if its a regular dataset, 2D geocoordinates, or 3D geocoordinates and make the CF compliance for these datasets
    if properties_data.name=="GEOCOOR2" or properties_data.name=="GEOCOOR3":
        # setting the coordinate system
        crs_name = properties_data.crs_name
        crs_attribute = properties_data.crs_attribute

        # ensuring the crs is CF compliant
        crs_attribute = CF_attribute_compliance(crs_attribute,crs_name)

        # try to see if the geo transformation and projection is passed as well
        try:
            if data["data_proj"] is not None:
                attr_name = ['crs_wkt']
                attr_value = [data["data_proj"]]
                crs_attribute = expand_attrdict(crs_attribute, attr_name, attr_value)
        except:
            pass

        # modify to make the CRS information locally at the group level of the datasets
        dset = fid.createVariable(crs_name, 'i4')
        add_attributes(dset,crs_attribute)

        ## START with 2D: LON LAT
        # defining the scales of the data at the parent level of the file for 2D coordinates
        lons = data['lons']
        lats = data['lats']
        lons_dim = data['lons_map']
        lats_dim = data['lats_map']
        rows_ds = len(lats)
        cols_ds = len(lons)
        fid.createDimension(lats_dim, rows_ds)
        fid.createDimension(lons_dim, cols_ds)


        # defining the lon lat datasets
        # Longitude
        properties_londata = copy.deepcopy(properties_data)
        #properties_londata.name = 'longitude'
        properties_londata.name = lons_dim
        attr_name = ['_CoordinateAxisType','units','long_name','standard_name']
        attr_value = ['Lon','degrees_east','longitude','longitude']
        properties_londata.attribute = expand_attrdict(properties_londata.attribute, attr_name, attr_value)
        properties_londata.dims = [lons_dim]
        data_lon = np.array(lons)
        write_dataset(fid,data_lon,properties_londata)

        # latitude
        properties_latdata = copy.deepcopy(properties_data)
        #properties_latdata.name = 'latitude'
        properties_latdata.name =lats_dim
        attr_name = ['_CoordinateAxisType','units','long_name','standard_name']
        attr_value = ['Lat','degrees_north','latitude','latitude']
        #attr_name = ['_CoordinateAxisType','units','long_name','standard_name','bounds']
        #attr_value = ['Lat','degrees_north','latitude','latitude',lats_dim+'_bnds']
        properties_latdata.attribute = expand_attrdict(properties_latdata.attribute, attr_name, attr_value)
        data_lat =  np.array(lats)
        properties_latdata.dims = [lats_dim]
        write_dataset(fid,data_lat,properties_latdata)

        ## ADD 3D if needed: HGT
        if properties_data.name=="GEOCOOR3":
            # defining the scales of the data at the parent level of the file for 3D coordinate
            hgts = data['hgts']
            hgts_dim = data['hgts_map']
            vert_ds = len(hgts)
            fid.createDimension(hgts_dim, vert_ds)

            # heights
            properties_hgtdata = copy.deepcopy(properties_data)
            #properties_hgtdata.name = 'heights'
            properties_hgtdata.name = hgts_dim
            attr_name = ['_CoordinateAxisType','units','long_name','standard_name','positive']
            attr_value = ['Lev','meter','height','height','up']
            properties_hgtdata.attribute = expand_attrdict(properties_hgtdata.attribute, attr_name, attr_value)
            data_hgt = np.array(hgts)
            properties_hgtdata.dims = [hgts_dim]
            write_dataset(fid,data_hgt,properties_hgtdata)

    ## POLYGON NEEDS special manipulation compared to raster datasets
    elif properties_data.data_type is not None and properties_data.data_type.lower()=="polygon":

        # number of polygons corresponds to the length of the list
        n_poly = len(data)
        # for now lets code the char to be lenth of the first poly
        n_char = len(list(data[0]))

        # creating the dimensions for the netcdf
        fid_parent.createDimension('wkt_length',n_char)
        fid_parent.createDimension('wkt_count',n_poly)
        dset = fid_parent.createVariable(name,'S1',('wkt_count','wkt_length'))

        # formatting the string as an array of single char
        # fill data with a charakter at each postion of the polyfgon string
        for poly_i in range(n_poly):
            polygon_i = list(data[poly_i])
            data_temp = []
            data_temp = np.empty((len(polygon_i),),'S1')
            for n in range(len(polygon_i)):
                data_temp[n] = polygon_i[n]
            dset[poly_i] = data_temp

        # setting the attribute
        if properties_data.attribute is not None and dset is not None:
            # for CF compliance make sure few attributes are provided
            properties_data = CF_attribute_compliance(properties_data,name)
            add_attributes(dset,properties_data.attribute)

        # adding the crs information for the polygon
        crs_name = properties_data.crs_name
        dset2 = fid_parent.createVariable(crs_name, 'i4')
        crs_attributes = properties_data.crs_attribute
        if crs_attributes is not None:
            # getting the EPSG code and update corresponding field if needed
            projectionRef = None
            for crs_attribute in crs_attributes:
                crs_attribute_name = extract_key(crs_attribute,"name")
                crs_attribute_value = extract_key(crs_attribute,"value")
                if crs_attribute_name.lower() == "spatial_ref":
                    if isinstance(crs_attribute_value,int):
                        ref = osr.SpatialReference()
                        ref.ImportFromEPSG(crs_attribute_value)
                        projectionRef = ref.ExportToWkt()
            if projectionRef is not None:
                # update the the attribute information
                attr_name = ['spatial_ref']
                attr_value = [projectionRef]
                crs_attributes = expand_attrdict(crs_attributes, attr_name, attr_value)

            # ensuring the crs is CF compliant
            crs_attributes = CF_attribute_compliance(crs_attributes,crs_name)

            # setting the variable
            add_attributes(dset2,crs_attributes)

        # setting the global attributes
        global_attribute = properties_data.global_attribute
        add_attributes(fid_parent,global_attribute)

    else:
        # for CF compliance make sure few attributes are provided
        properties_data = CF_attribute_compliance(properties_data,name)

        # write the dataset
        write_dataset(fid,data,properties_data)

def CF_attribute_compliance(properties_data,name):
    """
        Ensuring that few CF attributes are added
    """

    # try to see if the attribute list is given directly or if it is part of a class
    class_flag = False
    try:
        data_attribute = properties_data.attribute
        class_flag = True
    except:
        data_attribute = properties_data


    # load all current attributes
    CF_current_dict = {}
    if data_attribute is not None:
        for attribute in data_attribute:
            CF_current_dict[extract_key(attribute,"name")] = extract_key(attribute,"value")


    # ensure the required CF attributes are present
    CF_missing_attr_name = []
    CF_missing_attr_value = []
    for CF_key in ["long_name","standard_name"]:
        try:
            CF_current_dict[CF_key]
        except:
            try:
                CF_missing_attr_name.append(CF_key)
                CF_missing_attr_value.append(name)
            except:
                pass

    if len(CF_missing_attr_name)>0:
        if class_flag:
            properties_data.attribute = expand_attrdict(properties_data.attribute, CF_missing_attr_name, CF_missing_attr_value)
        else:
            properties_data =  expand_attrdict(properties_data,CF_missing_attr_name, CF_missing_attr_value)

    return properties_data

def add_attributes(fid,attributes):
    """
        Adding attributes to a group/dataset
    """

    # looping over the attributes
    if attributes is not None:
        for attribute in attributes:
            attribute_name = extract_key(attribute,"name")
            attribute_value = extract_key(attribute,"value")
            # make sure the strings are correctly encoded
            if isinstance(attribute_value, str):
                attribute_value = attribute_value.encode('ascii')
            setattr(fid, attribute_name, attribute_value)


def data_loading(filename,out_data_type=None,data_band=None):
    """
        GDAL READER of the data
        filename: the gdal readable file that needs to be loaded
        out_data_type: the datatype of the output data, default is original
        out_data_res: the resolution of the output data, default is original
        data_band: the band that needs to be loaded, default is all
    """

    # converting to the absolute path
    filename = os.path.abspath(filename)
    if not os.path.isfile(filename):
        logger.info(filename + " does not exist")
        out_data = None
        return out_data

    # open the GDAL file and get typical data information
    try:
        data =  gdal.Open(filename, gdal.GA_ReadOnly)
    except:
        logger.info(filename + " is not a gdal supported file")
        out_data = None
        return out_data

    # loading the requested band or by default all
    if data_band is not None:
        raster = data.GetRasterBand(data_band)
        out_data = raster.ReadAsArray()
    else:
        # load the data
        out_data = data.ReadAsArray()

    # getting the gdal transform and projection
    geoTrans = str(data.GetGeoTransform())
    projectionRef = str(data.GetProjection())

    # getting the no-data value
    try:
        NoData = data.GetNoDataValue()
        logger.info(NoData)
    except:
        NoData = None

    # change the dataype if provided
    if out_data_type is not None:
        # changing the format if needed
        out_data = out_data.astype(dtype=out_data_type)

    return out_data, geoTrans,projectionRef, NoData

def extract_key(data_dict,key):
    #logger.info(data_dict)
    #logger.info(key)
    if key in data_dict:
        dict_value = data_dict[key]

        # convert the chunks string to a tuple
        if key=="chunks":
           dict_value = tuple(map(int,dict_value.split(",")))

        return dict_value
    else:
        return None


def createParser():
    '''
        Create command line parser.
    '''

    parser = argparse.ArgumentParser(description='Unwrap interferogram using snaphu')
    parser.add_argument('-i', '--input', dest='filename', type=str, required=True, help='Input json file to be used for packing')
    return parser

def cmdLineParse(iargs=None):
    '''
        Command line parser.
    '''
    parser = createParser()
    return parser.parse_args(args = iargs)

def main():
    # get config json file
    cwd = os.getcwd()
    filename = os.path.join(cwd, 'tops_groups.json')

    with open(filename) as f:
        # read the json file with planned netcdf4 structure and put the content in a dictionary
        structure = json.load(f, object_pairs_hook=OrderedDict)

    # set netcdf file
    netcdf_outfile = structure["filename"]

    # Check for existing netcdf file
    if os.path.exists(netcdf_outfile):
        logger.info('{0} file already exists'.format(netcdf_outfile))
        os.remove(netcdf_outfile)
    fid = Dataset(netcdf_outfile, 'w')

    # create a variable scale for strings in case these are being generated
    fid.createDimension('matchup', None)


    # adding the global attributes to the file
    try:
        global_attribute = structure["global_attribute"]
        add_attributes(fid, global_attribute)
    except Exception as e:
        logger.error(e)
        logger.error(traceback.format_exc())
        pass

    # iterate over the different datasets
    try:
        for dataset in structure.get("dataset", []):
            create_dataset(fid, dataset, fid_parent=fid)
    except Exception as e:
        logger.error(e)
        logger.error(traceback.format_exc())
        pass

    # iterate over the different groups
    try:
        for group in structure.get("group", []):
            create_group(fid, group, fid_parent=fid)
    except Exception as e:
        logger.error(e)
        logger.error(traceback.format_exc())
        pass

    source_statement = fid.getncattr('source')
    software_statement = structure['software_statement']
    fid.setncattr('source', f'{source_statement} {software_statement}')

    # close the file
    fid.close()

    logger.info('Done with packaging')


if __name__ == '__main__':
    '''
        Main driver.
    '''
    main()
