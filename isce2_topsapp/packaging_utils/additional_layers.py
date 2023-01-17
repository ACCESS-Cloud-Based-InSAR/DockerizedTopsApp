import json
from pathlib import Path

import h5py
import xarray as xr

LAYER_JSON = Path(__file__).parents[0] / 'additional_layers.json'
ADDITIONAL_LAYERS = json.load(open(LAYER_JSON))


def add_2d_layer(layer_name: str, netcdf_path: Path) -> Path:
    """
    Combines a lot of standard formatting of the netcdf via rioxarray and
    deletes the previous placeholder (we assume it exists via the placeholder).

    We also assume any additional processing specific to GUNW is done outside of
    this function.
    """

    layer_data = ADDITIONAL_LAYERS[layer_name]
    dst_group = layer_data['dst_group']
    dst_variable = layer_data['dst_variable']

    # The layers generally already exist within the file
    with h5py.File(netcdf_path, mode='a') as file:
        del file[dst_group][dst_variable]

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

    ds.to_netcdf(netcdf_path,
                 group=layer_data['dst_group'],
                 mode='a')

    return netcdf_path
