import datetime
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Union

import h5py
from dateparser import parse

import isce2_topsapp
from isce2_topsapp.packaging_utils.additional_layers import add_2d_layer
from isce2_topsapp.packaging_utils.ionosphere import format_ionosphere_for_gunw
from isce2_topsapp.templates import read_netcdf_packaging_template

DATASET_VERSION = '3.0.0'


PERMISSIBLE_2D_LAYERS = ['ionosphere']


"""Warning: the packaging scripts were written as command line scripts and
are highly dependent on the current working directory and its structure.

Frequently, scripts (if they fail) may change the current working directory so
cannot be re-run with the same inputs unless the initial current working
directory are correctly configured in the workspace as initially intended.

For example, let `cwd` be the current working directory and `F` be some
routine that takes `cwd`. If `F(cwd)` fails, then `F(cwd)` may fail
simply because the actual current working directory is different because this
was changed during runtime of `F`.
"""


def update_gunw_internal_version_attribute(nc_path: Path, new_version='1c'):
    with h5py.File(nc_path, mode='a') as file:
        # Deleting attribute removes the type information so there is no
        # truncation and a simple string can be written.
        if 'version' in file.attrs:
            del file.attrs['version']
        file.attrs['version'] = new_version


def get_gunw_hash_id(reference_ids: list, secondary_ids: list) -> str:
    all_ids = json.dumps([' '.join(sorted(reference_ids)),
                          ' '.join(sorted(secondary_ids))
                          ]).encode('utf8')
    hash_id = hashlib.md5(all_ids).hexdigest()
    return hash_id


def get_geo_str(extent: list) -> str:

    lon, lat = extent[:2]

    lon_dir = 'W' if lon <= 0 else 'E'
    lat_dir = 'N' if lat >= 0 else 'S'

    lon_north, lat_north = abs(round(lon)), abs(round(lat))
    lon_str = f'{lon_north:05d}{lon_dir}'
    lat_str = f'{lat_north:05d}{lat_dir}'
    return f'{lon_str}_{lat_str}'


def get_center_time(properties: list) -> datetime.datetime:

    start_times = sorted([parse(props['startTime']) for props in properties])
    stop_times = sorted([parse(props['stopTime']) for props in properties])

    start_time = start_times[0]
    stop_time = stop_times[-1]

    center_datetime = start_time + (stop_time - start_time) / 2
    return center_datetime


def get_gunw_id(reference_properties: list,
                secondary_properties: list,
                extent: list,
                ) -> str:

    # asc_or_desc: will be "A" or "D"
    flight_direction = reference_properties[0]['flightDirection']
    asc_or_desc = flight_direction[0]

    # path or track number; needs to be padded so it is 3 digits
    # e.g. 064 or 128
    track_num = int(reference_properties[0]['pathNumber'])
    track = f'{track_num:03}'

    # Center Datetimes
    ref_center_datetime = get_center_time(reference_properties)
    sec_center_datetime = get_center_time(secondary_properties)

    # Center Time string
    ref_center_time_str = ref_center_datetime.strftime('%H%M%S')

    reference_date_str = ref_center_datetime.strftime('%Y%m%d')
    secondary_date_str = sec_center_datetime.strftime('%Y%m%d')

    # date pair
    date_pair = f'{reference_date_str}_{secondary_date_str}'

    # Geo string
    geo_str = get_geo_str(extent)

    # hash_id
    reference_ids = [p['sceneName'] for p in reference_properties]
    secondary_ids = [p['sceneName'] for p in secondary_properties]
    ifg_hash = get_gunw_hash_id(reference_ids, secondary_ids)
    ifg_hash_trunc = ifg_hash[:4]

    # version
    version = DATASET_VERSION.replace('.', '_')
    version = f'v{version}'

    ids = ['S1-GUNW',
           asc_or_desc,
           # right looking
           'R',
           track,
           # legacy constant
           'tops',
           date_pair,
           ref_center_time_str,
           geo_str,
           # legacy constant
           'PP',
           ifg_hash_trunc,
           version]

    gunw_id = '-'.join(ids)

    return gunw_id


def make_geocube(isce_data_directory: Union[str, Path]) -> Path:
    """This generates the `metadata.h5` from a command-line script.

    The metadata.h5 will be written in the `merged/` directory of the ISCE2
    outputs.

    Parameters
    ----------
    isce_data_directory
        The relative location of the ISCE2 files.

    Returns
    -------
    Path
        Relative path of the metadata.h5 file.
    """
    cwd = Path.cwd()
    merged_dir = Path(isce_data_directory)/'merged'
    os.chdir(merged_dir)

    cmd = 'makeGeocube --r ../reference --s ../secondary -o metadata.h5'
    subprocess.check_call(cmd, shell=True)
    os.chdir(cwd)

    metadata_path = merged_dir/'metadata.h5'
    return metadata_path


def _write_json_config(*,
                       gunw_id: str,
                       directory: Path) -> Path:
    """Reads the json template and writes a new entry: `file: '<gunw_id>.nc'`.

    Then, the new json file is saved in the directory specified. The filename
    is `tops_groups.json`.

    Parameters
    ----------
    gunw_id : str
        The gunw_id is specified as this will be used to create a netcdf file
        `<gunw_id>.nc`.
    directory : Path
        Directory where `tops_group.json` is saved.

    Returns
    -------
    Path
        Path to `tops_group.json`.
    """
    nc_template = read_netcdf_packaging_template()

    nc_template['filename'] = f'{gunw_id}.nc'
    # This will be appended to the global source attribute
    nc_template['software_statement'] = f'using the DockerizedTopsApp HyP3 plugin version {isce2_topsapp.__version__}'

    out_path = directory/'tops_groups.json'
    with open(out_path, 'w') as f:
        json.dump(nc_template, f, indent=2, sort_keys=True)
    return out_path


def perform_netcdf_packaging(*,
                             gunw_id: str,
                             isce_data_dir: Union[str, Path]) -> Path:

    # Check that the metadata.h5 exists
    isce_data_dir = Path(isce_data_dir)
    merged_dir = isce_data_dir/'merged'
    metadata_path = merged_dir/'metadata.h5'
    assert metadata_path.exists()

    # Write config file
    _write_json_config(gunw_id=gunw_id,
                       directory=merged_dir)

    cwd = Path.cwd()
    os.chdir(merged_dir)

    cmd = 'nc_packaging'
    subprocess.check_call(cmd, shell=True)
    os.chdir(cwd)

    out_nc_file = merged_dir/f'{gunw_id}.nc'

    # Check if the netcdf file was created
    assert out_nc_file.exists()
    return out_nc_file


def package_additional_layers_into_gunw(gunw_path: Path,
                                        isce_data_directory: Path,
                                        additional_2d_layers: list):
    # Current workflow of additional layers
    # 1. Do any additional processing/formatting outside of GUNW
    # 2. Add layer into GUNW
    # 3. Update Version
    if not set(additional_2d_layers).issubset(set(PERMISSIBLE_2D_LAYERS)):
        raise RuntimeError('Additional 2d layers must be subset of '
                           f'{PERMISSIBLE_2D_LAYERS}')

    if 'ionosphere' in additional_2d_layers:
        # current working directory is ISCE directory
        _ = format_ionosphere_for_gunw(isce_data_directory, gunw_path)

    # Assumes ionosphere raster is written to specific path
    [add_2d_layer(layer, gunw_path) for layer in additional_2d_layers]

    # Update
    with h5py.File(gunw_path, mode='a') as file:
        file.attrs.modify('version', '1c')
    return gunw_path


def package_gunw_product(*,
                         isce_data_directory: Union[str, Path],
                         reference_properties: list,
                         secondary_properties: list,
                         extent: list,
                         additional_2d_layers: list = None) -> Path:
    """Creates a GUNW standard product netcdf from the ISCE outputs and some
    initial metadata.

    Parameters
    ----------
    isce_data_directory: str | path
        Where the ISCE outputs are relative to current working directory
    reference_properties: list
        Each item a dictionary per ASF API including ID, starttime, etc.
    secondary_properties: list
        Each item a dictionary per ASF API including ID, starttime, etc
    extent: list
        List of extents ([xmin, ymin, xmax, ymax])
    additional_2d_layers: list
        List of 2d layers to add. Currently, supported is ionosphere.

    Returns
    -------
    Path
        Location of final netcdf product
    """
    make_geocube(isce_data_directory)

    gunw_id = get_gunw_id(reference_properties=reference_properties,
                          secondary_properties=secondary_properties,
                          extent=extent)

    out_nc_file = perform_netcdf_packaging(isce_data_dir=isce_data_directory,
                                           gunw_id=gunw_id)

    if additional_2d_layers is not None:
        package_additional_layers_into_gunw(out_nc_file,
                                            isce_data_directory,
                                            additional_2d_layers)
    return out_nc_file
