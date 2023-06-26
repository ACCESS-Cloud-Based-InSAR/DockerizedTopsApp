import json
from pathlib import Path

import h5py
import xarray as xr

LAYER_JSON = Path(__file__).parents[0] / 'additional_layers.json'
ADDITIONAL_LAYERS = json.load(open(LAYER_JSON))


def add_2d_layer(layer_name: str, gunw_netcdf_path: Path, additional_attrs: dict = None) -> Path:
    """
    Combines a lot of standard formatting of the netcdf via rioxarray and
    deletes the previous placeholder (we assume it exists via the placeholder).

    We also assume any additional processing specific to GUNW is done outside of
    this function.
    """

    layer_data = ADDITIONAL_LAYERS[layer_name]
    dst_group = layer_data['dst_group']
    dst_variable = layer_data['dst_variable']
    if additional_attrs:
        layer_data['attrs'].update(additional_attrs)

    # The layers generally already exist within the file
    with h5py.File(gunw_netcdf_path, mode='a') as file:
        if dst_group in file:
            # Delete the variable to be written to
            if dst_variable in file[dst_group]:
                del file[dst_group][dst_variable]
            # Delete the group if there are no variables left
            if len(file[dst_group].keys()) == 0:
                del file[dst_group]

    ds = xr.open_dataset(layer_data['input_relative_path'],
                         engine='rasterio')

    # Renaming ensures correct geo-referencing with spatial_ref grid mapping
    ds = ds.rename({'x': 'longitude',
                    'y': 'latitude',
                    'band_data': dst_variable})
    ds['latitude'].attrs.update({'long_name': 'latitude',
                                 'standard_name': 'latitude'})
    ds['longitude'].attrs.update({'long_name': 'longitude',
                                  'standard_name': 'longitude'})

    # removes channel (aka band) dimension
    ds = ds.squeeze(['band'], drop=True)
    ds[layer_name].attrs.update(layer_data['attrs'])

    ds.to_netcdf(gunw_netcdf_path,
                 group=layer_data['dst_group'],
                 mode='a')

    return gunw_netcdf_path
