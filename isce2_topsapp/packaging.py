import datetime
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Union

import h5py
import numpy as np
import rasterio
from dateparser import parse
from lxml import etree

import isce2_topsapp
from isce2_topsapp.packaging_utils.additional_layers import add_2d_layer
from isce2_topsapp.packaging_utils.ionosphere import (
    format_iono_burst_ramps,
    format_ionosphere_for_gunw,
)
from isce2_topsapp.templates import read_netcdf_packaging_template
from isce2_topsapp.water_mask import get_water_mask_raster_for_browse_image

DATASET_VERSION = "3.0.1"
STANDARD_PROD_PREFIX = "S1-GUNW"
CUSTOM_PROD_PREFIX = "S1-GUNW_CUSTOM"


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

# The filename in the ISCE2 merged folder
LAYER2PATH = {
    "incidence_angle": {"file_name": "los.rdr.geo", "band": 1},
    "azimuth_angle": {"file_name": "los.rdr.geo", "band": 2},
    "filtered_coherence": {"file_name": "phsig.cor.geo", "band": 1},
    "unfiltered_coherence": {"file_name": "topophase.cor.geo", "band": 2}
}


def read_baselines(tops_proc_xml: str) -> dict:
    with open(tops_proc_xml) as f:
        xml_str = f.read()
    # :_ are not properly formatted tags
    xml_str = xml_str.replace(":_", "")
    root = etree.fromstring(xml_str)

    element_path = ".//baseline/"
    elements = root.findall(element_path)

    tags = [e.tag for e in elements]
    vals = [float(e.text) for e in elements]
    parallel_baselines = [vals[k] for (k, val) in enumerate(vals) if "Bpar" in tags[k]]
    perpendicular_baselines = [
        vals[k] for (k, val) in enumerate(vals) if "Bperp" in tags[k]
    ]

    return {
        "parallel_baselines": parallel_baselines,
        "perpendicular_baselines": perpendicular_baselines,
    }


def get_mean_baseline_data(tops_proc_xml: str) -> dict:
    baseline_data = read_baselines(tops_proc_xml)
    mean_baseline_data = {f'mean_{key[:-1]}': np.mean(val) for (key, val) in baseline_data.items()}
    return mean_baseline_data


def update_gunw_internal_version_attribute(nc_path: Path, new_version="1c"):
    with h5py.File(nc_path, mode="a") as file:
        # Deleting attribute removes the type information so there is no
        # truncation and a simple string can be written.
        if "version" in file.attrs:
            del file.attrs["version"]
        file.attrs["version"] = new_version


def get_gunw_hash_id(reference_ids: list, secondary_ids: list) -> str:
    all_ids = json.dumps(
        [" ".join(sorted(reference_ids)), " ".join(sorted(secondary_ids))]
    ).encode("utf8")
    hash_id = hashlib.md5(all_ids).hexdigest()
    return hash_id


def get_geo_str(extent: list) -> str:
    lon, lat = extent[:2]

    lon_dir = "W" if lon <= 0 else "E"
    lat_dir = "N" if lat >= 0 else "S"

    lon_north, lat_north = abs(round(lon)), abs(round(lat))
    lon_str = f"{lon_north:05d}{lon_dir}"
    lat_str = f"{lat_north:05d}{lat_dir}"
    return f"{lon_str}_{lat_str}"


def get_center_time(properties: list) -> datetime.datetime:
    start_times = sorted([parse(props["startTime"]) for props in properties])
    stop_times = sorted([parse(props["stopTime"]) for props in properties])

    start_time = start_times[0]
    stop_time = stop_times[-1]

    center_datetime = start_time + (stop_time - start_time) / 2
    return center_datetime


def get_gunw_id(
    reference_properties: list,
    secondary_properties: list,
    extent: list,
    standard_product: bool = True,
) -> str:
    # asc_or_desc: will be "A" or "D"
    flight_direction = reference_properties[0]["flightDirection"]
    asc_or_desc = flight_direction[0]

    # path or track number; needs to be padded so it is 3 digits
    # e.g. 064 or 128
    track_num = int(reference_properties[0]["pathNumber"])
    track = f"{track_num:03}"

    # Center Datetimes
    ref_center_datetime = get_center_time(reference_properties)
    sec_center_datetime = get_center_time(secondary_properties)

    # Center Time string
    ref_center_time_str = ref_center_datetime.strftime("%H%M%S")

    reference_date_str = ref_center_datetime.strftime("%Y%m%d")
    secondary_date_str = sec_center_datetime.strftime("%Y%m%d")

    # date pair
    date_pair = f"{reference_date_str}_{secondary_date_str}"

    # Geo string
    geo_str = get_geo_str(extent)

    # hash_id
    reference_ids = [p["sceneName"] for p in reference_properties]
    secondary_ids = [p["sceneName"] for p in secondary_properties]
    ifg_hash = get_gunw_hash_id(reference_ids, secondary_ids)
    ifg_hash_trunc = ifg_hash[:4]

    # version
    version = DATASET_VERSION.replace(".", "_")
    version = f"v{version}"

    gunw_prefix = STANDARD_PROD_PREFIX if standard_product else CUSTOM_PROD_PREFIX
    ids = [
        gunw_prefix,
        asc_or_desc,
        # right looking
        "R",
        track,
        # legacy constant
        "tops",
        date_pair,
        ref_center_time_str,
        geo_str,
        # legacy constant
        "PP",
        ifg_hash_trunc,
        version,
    ]

    gunw_id = "-".join(ids)

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
    merged_dir = Path(isce_data_directory) / "merged"
    os.chdir(merged_dir)

    cmd = "makeGeocube --r ../reference --s ../secondary -o metadata.h5"
    subprocess.check_call(cmd, shell=True)
    os.chdir(cwd)

    metadata_path = merged_dir / "metadata.h5"
    return metadata_path


def _write_json_config(*, gunw_id: str, directory: Path) -> Path:
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

    nc_template["filename"] = f"{gunw_id}.nc"
    # This will be appended to the global source attribute
    nc_template[
        "software_statement"
    ] = f"using the DockerizedTopsApp HyP3 plugin version {isce2_topsapp.__version__}"

    out_path = directory / "tops_groups.json"
    with open(out_path, "w") as f:
        json.dump(nc_template, f, indent=2, sort_keys=True)
    return out_path


def perform_netcdf_packaging(*, gunw_id: str, isce_data_dir: Union[str, Path]) -> Path:
    # Check that the metadata.h5 exists
    isce_data_dir = Path(isce_data_dir)
    merged_dir = isce_data_dir / "merged"
    metadata_path = merged_dir / "metadata.h5"
    assert metadata_path.exists()

    # Write config file
    _write_json_config(gunw_id=gunw_id, directory=merged_dir)

    cwd = Path.cwd()
    os.chdir(merged_dir)

    cmd = "nc_packaging"
    subprocess.check_call(cmd, shell=True)
    os.chdir(cwd)

    out_nc_file = merged_dir / f"{gunw_id}.nc"

    # Check if the netcdf file was created
    assert out_nc_file.exists()
    return out_nc_file


def package_additional_layers_into_gunw(
    gunw_path: Path,
    isce_data_directory: Path,
    additional_2d_layers: list,
    additional_attributes: dict,
):
    # Current workflow of additional layers
    # 1. Do any additional processing/formatting outside of GUNW
    # 2. Add layer into GUNW
    # 3. Update Version

    # in case additional attributes is None
    additional_attributes = additional_attributes or {}
    if not set(additional_attributes.keys()).issubset(additional_2d_layers):
        raise ValueError(
            "Additional attributes dict must be within additional_2d_layers"
        )

    if "ionosphere" in additional_2d_layers:
        # current working directory is ISCE directory
        _ = format_ionosphere_for_gunw(isce_data_directory, gunw_path)
    if "ionosphereBurstRamps" in additional_2d_layers:
        # current working directory is ISCE directory
        _ = format_iono_burst_ramps(isce_data_directory, gunw_path)

    # Assumes ionosphere raster is written to specific path
    additional_attributes_lst = [
        additional_attributes.get(layer_name, None)
        for layer_name in additional_2d_layers
    ]
    zipped_data = zip(additional_2d_layers, additional_attributes_lst)
    [
        add_2d_layer(layer, gunw_path, additional_attrs=add_attrs)
        for (layer, add_attrs) in zipped_data
    ]

    # Update
    with h5py.File(gunw_path, mode="a") as file:
        file.attrs.modify("version", "1c")
    return gunw_path


def get_layer_mean(
    merged_dir: Union[Path, str], layer_name: str, apply_water_mask: bool = False, default_isce_nodata: float = 0.,
) -> float:
    log = f"Extracting mean value from {layer_name}"
    if apply_water_mask:
        log += " with water mask"
    print(log)
    merged_dir = Path(merged_dir)
    layer_path = merged_dir / LAYER2PATH[layer_name]["file_name"]
    band_num = LAYER2PATH[layer_name]["band"]

    with rasterio.open(layer_path) as ds:
        X = ds.read(band_num)
        X_nodata = (X == default_isce_nodata)
        if apply_water_mask:
            p = ds.profile
            water_mask = get_water_mask_raster_for_browse_image(p)
            X_nodata = water_mask | X_nodata

    mean_val = np.mean(X[~X_nodata])
    return mean_val


def get_geocoded_layer_means(*, merged_dir: Union[Path, str] = None) -> Path:
    if merged_dir is None:
        cwd = Path.cwd()
        merged_dir = f"{cwd}/merged"

    def get_layer_mean_p(layer_name: str, apply_water_mask: bool = False) -> float:
        return get_layer_mean(merged_dir, layer_name, apply_water_mask=apply_water_mask)

    mean_vals = {
        "mean_filtered_coherence_without_water_mask": get_layer_mean_p(
            "filtered_coherence", apply_water_mask=False
        ),
        "mean_filtered_coherence_with_water_mask": get_layer_mean_p(
            "filtered_coherence", apply_water_mask=True
        ),
        "mean_unfiltered_coherence_without_water_mask": get_layer_mean_p(
            "unfiltered_coherence", apply_water_mask=False
        ),
        "mean_unfiltered_coherence_with_water_mask": get_layer_mean_p(
            "unfiltered_coherence", apply_water_mask=True
        ),
        "mean_incidence_angle": get_layer_mean_p("incidence_angle"),
        "mean_azimuth_angle": get_layer_mean_p("azimuth_angle") + 90,
    }
    return mean_vals


def record_params_as_global_attrs(
    *, netcdf_path: Path, cmd_line_str: str, topsapp_params: dict
) -> Path:
    with h5py.File(netcdf_path, mode="a") as file:
        file.attrs.update(aria_frame_id=topsapp_params["frame_id"])
        file.attrs.update(topsapp_command_line_string=cmd_line_str)
        file.attrs.update(isce2_topsapp_version=f"{isce2_topsapp.__version__}")
        file["science/grids"].attrs.update(**topsapp_params)
    return netcdf_path


def record_wkt_geometry_as_global_attrs(*, netcdf_path: Path, product_geometry_wkt: str) -> Path:
    with h5py.File(netcdf_path, mode="a") as file:
        file.attrs.update(product_geometry_wkt=product_geometry_wkt)
    return netcdf_path


def record_stats_as_global_attrs(*, netcdf_path: Union[Path, str], isce_data_dir: Union[Path, str]) -> Path:
    """Records the mean coherence (with and without water mask), mean incidence angle, mean azimuth angle, and
    mean baselines (parallel and perp)"""
    merged_dir = Path(isce_data_dir) / 'merged'
    layer_means_from_geocoded_isce_files = get_geocoded_layer_means(merged_dir=merged_dir)

    tops_proc_xml = Path(isce_data_dir) / 'topsProc.xml'
    mean_baseline_data = get_mean_baseline_data(tops_proc_xml)
    with h5py.File(netcdf_path, mode='a') as file:
        file.attrs.update(**layer_means_from_geocoded_isce_files)
        file.attrs.update(**mean_baseline_data)
    return netcdf_path


def package_gunw_product(
    *,
    isce_data_directory: Union[str, Path],
    reference_properties: list,
    secondary_properties: list,
    extent: list,
    topaspp_params: dict,
    cmd_line_str: str,
    product_geometry_wkt: str,
    additional_2d_layers: list = None,
    standard_product: bool = True,
    additional_attributes: dict = None,
) -> Path:
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
    additional_attributes: dict
        List of attributs dicts for additional layers o add.
        Currently, supported only for ionosphere.
    standard_product: bool
        Whether the package is a GUNW standard product or not. Will use the
        the prefix `S1-GUNW` for standard products and `S1-GUNW_CUSTOM`
        otherwise

    Returns
    -------
    Path
        Location of final netcdf product
    """
    make_geocube(isce_data_directory)

    gunw_id = get_gunw_id(
        reference_properties=reference_properties,
        secondary_properties=secondary_properties,
        extent=extent,
        standard_product=standard_product,
    )

    out_nc_file = perform_netcdf_packaging(
        isce_data_dir=isce_data_directory, gunw_id=gunw_id
    )

    if additional_2d_layers is not None:
        isce_data_directory = Path(isce_data_directory)
        package_additional_layers_into_gunw(
            out_nc_file,
            isce_data_directory,
            additional_2d_layers,
            additional_attributes,
        )
    out_nc_file = record_params_as_global_attrs(
        netcdf_path=out_nc_file,
        topsapp_params=topaspp_params,
        cmd_line_str=cmd_line_str,
    )
    out_nc_file = record_stats_as_global_attrs(netcdf_path=out_nc_file, isce_data_dir=isce_data_directory)
    out_nc_file = record_wkt_geometry_as_global_attrs(
        netcdf_path=out_nc_file, product_geometry_wkt=product_geometry_wkt
    )
    return out_nc_file
