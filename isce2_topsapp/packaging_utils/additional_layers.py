import json
from pathlib import Path

import rioxarray as rxr
import xarray as xr

LAYER_JSON = Path(__file__).parents[0] / 'additional_layers.json'
ADDITIONAL_LAYERS = json.load(open(LAYER_JSON))


def add_2d_layer(layer_name: str, netcdf_path: Path) -> Path:

    layer_data = ADDITIONAL_LAYERS[layer_name]
    data_array = rxr.open_rasterio(layer_data['input_relative_path'])
    data_array = data_array.rename({'x': 'longitude',
                                    'y': 'latitude'})

    data_array = data_array.squeeze(dim=['band'],
                                    drop=True)

    data_array.attrs.update(layer_data['attr'])
    group = xr.Dataset({layer_name: data_array})

    group.rio.write_crs(4326, inplace=True)

    group.to_netcdf(netcdf_path,
                    group=layer_data['dst_group'],
                    mode='a')

    return netcdf_path
