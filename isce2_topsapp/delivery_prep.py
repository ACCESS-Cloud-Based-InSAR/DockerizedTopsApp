import datetime
import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from dateparser import parse
from matplotlib import cm

from isce2_topsapp.packaging import DATASET_VERSION
from isce2_topsapp.water_mask import get_water_mask_raster

TEMPLATE_DIR = (Path(__file__).parent/'templates').absolute()
SCHEMA_PATH = TEMPLATE_DIR/'daac_ingest_schema.json'


def get_dataset_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    return schema


def scale_img(img: np.ndarray,
              new_min: int = 0,
              new_max: int = 1) -> np.ndarray:
    """
    Scale an image by the absolute max and min in the array to have dynamic
    range new_min to new_max. Useful for visualization.
    Parameters
    ----------
    img : np.ndarray
    new_min : int
    new_max : int
    Returns
    -------
    np.ndarray:
       New image with shape equal to img, scaled to [new_min, new_max]
    """
    i_min = np.nanmin(img)
    i_max = np.nanmax(img)
    if i_min == i_max:
        # then image is constant image and clip between new_min and new_max
        return np.clip(img, new_min, new_max)
    img_scaled = (img - i_min) / (i_max - i_min) * (new_max - new_min)
    img_scaled += new_min
    return img_scaled


def read_baseline_perp(nc_path) -> np.ndarray:
    group_path = '/science/grids/imagingGeometry/perpendicularBaseline'
    with rasterio.open(f'netcdf:{nc_path}:{group_path}') as ds:
        arr = ds.read(1)
    return arr


def open_science_grid(nc_path, variable):
    group_path = f'/science/grids/data/{variable}'
    with rasterio.open(f'netcdf:{nc_path}:{group_path}') as ds:
        X = ds.read(1)
        profile = ds.profile
    return X, profile


def get_connected_component_mask(con_comp: np.ndarray) -> np.ndarray:
    mask = (con_comp == 0) | (con_comp == -1)
    return mask


def save_png(arr: np.ndarray,
             out_png_path: Path,
             scale_dimension: float = .2,
             cmap: str = 'hsv') -> Path:
    shape = arr.shape
    # from normal dynamic range to [0, 1]
    arr_scaled = scale_img(arr)

    s = scale_dimension
    # swap dimensions for Pillow
    shape_new = int(shape[1] * s), int(shape[0] * s)

    # https://stackoverflow.com/a/10967471
    cmap_trans = cm.__dict__[cmap]
    im = Image.fromarray(np.uint8(cmap_trans(arr_scaled) * 255))
    # https://stackoverflow.com/a/13211834
    im = im.resize(shape_new, Image.ANTIALIAS)

    im.save(str(out_png_path))
    return out_png_path


def get_wrapped_ifg(nc_path: Path) -> np.ndarray:
    cc, profile = open_science_grid(nc_path, 'connectedComponents')
    unw, _ = open_science_grid(nc_path, 'unwrappedPhase')

    mask_cc = get_connected_component_mask(cc)
    mask_water = get_water_mask_raster(profile)
    mask = mask_cc | mask_water

    wrapped = np.zeros(mask.shape)
    # If no valid data skip
    if np.sum(~mask) > 0:
        unw_m = unw.copy()
        unw_m[mask] = np.nan
        wrapped = np.angle(np.exp(1j * unw_m))
    return wrapped


def gen_browse_imagery(nc_path: Path,
                       out_path: Path) -> Path:

    wrapped = get_wrapped_ifg(nc_path)
    save_png(wrapped, out_path)
    return out_path


def format_metadata(nc_path: Path,
                    all_metadata: dict) -> dict:

    label = nc_path.name[:-3]  # removes suffix .nc
    geojson = all_metadata['gunw_geo'].__geo_interface__

    ref_props_all = sorted(all_metadata['reference_properties'],
                           key=lambda prop: prop['startTime'])
    ref_props_first = ref_props_all[0]
    sec_props_all = sorted(all_metadata['secondary_properties'],
                           key=lambda prop: prop['startTime'])
    sec_props_first = sec_props_all[0]
    b_perp = read_baseline_perp(nc_path).mean()

    ref_start_times = [parse(props['startTime']) for props in ref_props_all]
    ref_stop_times = [parse(props['stopTime']) for props in ref_props_all]
    sec_start_times = [parse(props['startTime']) for props in sec_props_all]

    ref_start_time = ref_start_times[0]
    ref_stop_time = ref_stop_times[-1]
    sec_start_time = sec_start_times[0]

    # The %f is miliseconds zero-padded with 6 decimals - just as we need!
    ref_start_time_formatted = ref_start_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    ref_stop_time_formatted = ref_stop_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    creation_timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ')

    # We want the nearest day (dt.days takes a floor) so we use total seconds and then round
    temporal_baseline_seconds = (ref_start_time - sec_start_time).total_seconds()
    temporal_baseline_days = round(temporal_baseline_seconds / 60 / 60 / 24)

    metadata = {}
    # get 4 corners of bounding box of the geometry; default is 5 returning
    # to start point
    ogr_bbox = all_metadata['gunw_geo'].envelope.exterior.coords[:4]
    metadata.update({"ogr_bbox": ogr_bbox,
                     "reference_scenes": all_metadata['reference_scenes'],
                     "secondary_scenes": all_metadata['secondary_scenes'],
                     "sensing_start": ref_start_time_formatted,
                     "sensing_stop": ref_stop_time_formatted,
                     "version": DATASET_VERSION,
                     "temporal_baseline_days": temporal_baseline_days,
                     "orbit_number": [int(ref_props_first['orbit']),
                                      int(sec_props_first['orbit'])],
                     "platform": [ref_props_first['platform'], sec_props_first['platform']],
                     "beam_mode": ref_props_first['beamModeType'],
                     "orbit_direction": ref_props_first['flightDirection'].lower(),
                     "dataset_type": 'slc',
                     "product_type": 'interferogram',
                     "polarization": "VV",
                     "look_direction": 'right',
                     "track_number": int(ref_props_first['pathNumber']),
                     "perpendicular_baseline":  round(float(b_perp), 4)
                     })

    data = {"label": label,
            "location": geojson,
            "creation_timestamp": creation_timestamp,
            "version": DATASET_VERSION,
            "metadata": metadata}

    if all_metadata['frame_id'] != -1:
        metadata['frame_number'] = all_metadata['frame_id']

    return data


def prepare_for_delivery(nc_path: Path,
                         all_metadata: dict) -> Path:
    gunw_id = nc_path.stem

    out_dir = Path(gunw_id)
    out_dir.mkdir(exist_ok=True)

    browse_path = out_dir / f'{gunw_id}.png'
    gen_browse_imagery(nc_path, browse_path)

    metadata = format_metadata(nc_path, all_metadata)

    metadata_path = out_dir / f'{gunw_id}.json'
    json.dump(metadata,
              open(metadata_path, 'w'),
              indent=2)

    nc_path.rename(out_dir / f'{gunw_id}.nc')

    return out_dir
