import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Union

import numpy as np
from dateparser import parse

from isce2_topsapp import __version__
from .templates import read_netcdf_packaging_template

DATASET_VERSION = '2.0.5'


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


def get_center_time(properties: list) -> str:

    ref_start_times = [parse(props['startTime']) for props in properties]
    ref_stop_times = [parse(props['stopTime']) for props in properties]

    all_times = (ref_start_times + ref_stop_times)
    N = len(all_times)
    all_time_deltas = [all_times[k] - all_times[0] for k in range(N)]

    center_time = all_times[0] + np.mean(all_time_deltas)

    return center_time.strftime('%H%M%S')


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

    # dates; remove dashes
    reference_date = reference_properties[0]['startTime'].split('T')[0]
    reference_date = reference_date.replace('-', '')
    secondary_date = secondary_properties[0]['startTime'].split('T')[0]
    secondary_date = secondary_date.replace('-', '')

    # date pair
    date_pair = f'{reference_date}_{secondary_date}'

    # Geo string
    geo_str = get_geo_str(extent)

    # Center Time (with Respect to Reference)
    ref_center_time = get_center_time(reference_properties)

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
           ref_center_time,
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
    nc_template['software_statement'] = f'using the DockerizedTopsApp HyP3 plugin version {__version__}'

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
    assert(metadata_path.exists())

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
    assert(out_nc_file.exists())
    return out_nc_file


def package_gunw_product(*,
                         isce_data_directory: Union[str, Path],
                         reference_properties: list,
                         secondary_properties: list,
                         extent: list) -> Path:
    """Creates a GUNW standard product netcdf from the ISCE outputs and some
    initial metadata.

    Parameters
    ----------
    isce_data_directory
        Where the ISCE outputs are relative to current working directory
    reference_properties
        Each item a dictionary per ASF API including ID, starttime, etc.
    secondary_properties
        Each item a dictionary per ASF API including ID, starttime, etc
    extent
        List of extents ([xmin, ymin, xmax, ymax])

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

    return out_nc_file
