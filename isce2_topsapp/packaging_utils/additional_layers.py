import json
from pathlib import Path

import h5py
import xarray as xr

LAYER_JSON = Path(__file__).parents[0] / 'additional_layers.json'
ADDITIONAL_LAYERS_DATA = json.load(open(LAYER_JSON))


def add_2d_layer(layer_name: str,
                 gunw_netcdf_path: Path,
                 additional_attrs: dict = None) -> Path:
    """
    Combines a lot of standard formatting of the netcdf via rioxarray and
    deletes the previous placeholder if there is one.

    We assume any additional processing specific to GUNW is done outside of
    this function.
    """

    layer_data = ADDITIONAL_LAYERS_DATA[layer_name]

    dst_group = layer_data['dst_group']
    dst_variable = layer_data['dst_variable']
    band_number = layer_data['src_band_number']
    nodata_val = layer_data.get('nodata')
    possible_layers = list(ADDITIONAL_LAYERS_DATA.keys())

    if layer_name not in possible_layers:
        ValueError('layer_name must be in {", ".join(possible_layers)}')

    if not isinstance(band_number, int) or (band_number < 1):
        ValueError('Layers must select individual layers from outputs i.e '
                   '1, 2, ...')

    if additional_attrs:
        layer_data['attrs'].update(additional_attrs)

    # If the layers already exist within the file, we need to delete them otherwise the dummy placeholder
    # Causes type errors when attempting to overwrite
    with h5py.File(gunw_netcdf_path, mode='a') as file:
        if dst_group in file:
            # Delete the variable to be written to
            if dst_variable in file[dst_group]:
                del file[dst_group][dst_variable]
            # Delete the group if there are no variables left to ensure correct type of arrays.
            # If there are variables left, this routine appends the new array to the group (assumes same dims
            # as existing arrays)
            if len(file[dst_group].keys()) == 0:
                del file[dst_group]

    ds = xr.open_dataset(layer_data['input_relative_path'],
                         engine='rasterio')

    # Ensures of grid_mapping_name as 'crs'
    # This allows us to append to /science/grids/data to have consistent CRS
    ds = ds.drop_vars('spatial_ref')
    ds.rio.write_crs(4326, inplace=True, grid_mapping_name='crs')

    # Renaming ensures correct geo-referencing with grid mapping
    ds = ds.rename({
                    # x, y are the coordinate names
                    'x': 'longitude',
                    'y': 'latitude',
                    'band_data': dst_variable})
    # removes channel (what rioxarray band) dimension in the coordinates
    ds = ds.sel(band=band_number, drop=True)

    ds['latitude'].attrs.update({'long_name': 'latitude',
                                 'standard_name': 'latitude'})
    ds['longitude'].attrs.update({'long_name': 'longitude',
                                  'standard_name': 'longitude'})

    ds[layer_name].attrs.update(layer_data['attrs'])

    if nodata_val is not None:
        ds[layer_name] = ds[layer_name].rio.write_nodata(nodata_val)

    ds.to_netcdf(gunw_netcdf_path,
                 group=layer_data['dst_group'],
                 mode='a')

    return gunw_netcdf_path
