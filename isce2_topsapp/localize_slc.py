import netrc
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from warnings import warn

import asf_search as asf
import geopandas as gpd
from dateparser import parse
from shapely.geometry import GeometryCollection, Polygon, shape
from shapely.ops import unary_union
from tqdm import tqdm


def get_gunw_extent_from_frame_id(frame_id) -> Polygon:
    data_dir = Path(__file__).parent / 'data'
    path_to_frames_zip = data_dir / 's1_gunw_frame_footprints.geojson.zip'
    df_gunw_extent = gpd.read_file(path_to_frames_zip)
    ind = df_gunw_extent.frame_id == frame_id
    df_gunw = df_gunw_extent[ind].reset_index(drop=True)
    gunw_geo = df_gunw.geometry[0]
    return gunw_geo


def get_processing_geo_from_frame_id(frame_id: int) -> Polygon:
    data_dir = Path(__file__).parent / 'data'
    path_to_frames_zip = data_dir / 's1_frames_latitude_aligned.geojson.zip'
    df_frames = gpd.read_file(path_to_frames_zip)
    ind = df_frames.frame_id == frame_id
    df_frame = df_frames[ind].reset_index(drop=True)
    processing_geo = df_frame.geometry[0]
    return processing_geo


def get_asf_slc_objects(slc_ids: list) -> list:

    response = asf.granule_search(slc_ids)

    def filter_by_type(response):
        props = response.properties
        return props['processingLevel'] == 'SLC'
    response = list(filter(filter_by_type, response))

    return response


def get_session():
    netrc_ob = netrc.netrc()

    earthdata_url = 'urs.earthdata.nasa.gov'
    username, _, password = netrc_ob.authenticators(earthdata_url)

    session = asf.ASFSession()
    session.auth_with_creds(username, password)
    return session


def get_interferogram_geo(reference_obs: list,
                          secondary_obs: list,
                          frame_id: int = -1) -> GeometryCollection:
    reference_geos = [shape(r.geojson()['geometry']) for r in reference_obs]
    secondary_geos = [shape(r.geojson()['geometry']) for r in secondary_obs]

    reference_geo = unary_union(reference_geos)
    secondary_geo = unary_union(secondary_geos)

    # if they are not Polygons they are multipolygons and not valid
    connected_ref = (reference_geo.geom_type == 'Polygon')
    connected_sec = (secondary_geo.geom_type == 'Polygon')

    if (not connected_sec) or (not connected_ref):
        raise ValueError('Reference and/or secondary dates were not connected'
                         ' in their coverage (multipolygons)')

    # Two geometries must intersect for their to be an interferogram
    ifg_geo = secondary_geo.intersection(reference_geo)
    if ifg_geo.is_empty:
        raise ValueError('The overlap between reference and secondary scenes '
                         'is empty')

    # Update the area of interest based on frame_id
    if frame_id != -1:
        gunw_geo = get_gunw_extent_from_frame_id(frame_id)
        if not gunw_geo.intersects(ifg_geo):
            raise ValueError('Frame area does not overlap with IFG '
                             'area (i.e. ref and sec overlap)')
        ifg_geo = gunw_geo
    return ifg_geo


def ensure_repeat_pass_time_small(slc_properties: list,
                                  maximum_minutes_between_acq=2):
    """Make sure all the dictionaries of startTime are within 5 minutes"""
    dates = [parse(prop['startTime']) for prop in slc_properties]
    dates = sorted(dates)
    minutes_apart_from_first_acq = [(date - dates[0]).seconds for date in dates]
    return all([minutes_apart <= maximum_minutes_between_acq * 60
                for minutes_apart in minutes_apart_from_first_acq])


def check_flight_direction(slc_properties: list) -> bool:
    unique_look_direction = set([prop['flightDirection']
                                 for prop in slc_properties])
    return len(unique_look_direction) == 1


def check_date_order(ref_properties: list, sec_properties: list) -> bool:
    ref_date = parse(ref_properties[0]['startTime'])
    sec_date = parse(sec_properties[0]['startTime'])
    return sec_date < ref_date


def check_track_numbers(slc_properties: list):
    path_numbers = [prop['pathNumber'] for prop in slc_properties]
    path_numbers = sorted(list(set(path_numbers)))
    if len(path_numbers) == 1:
        return True
    if len(path_numbers) == 2:
        if ((path_numbers[1] - path_numbers[0]) == 1):
            return True
    return False


def get_percent_water_from_ne_land(ifg_geo: Polygon):
    """Gets percent_water using Natural Earth Low Res Mask"""
    df_world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
    world_geo = df_world.geometry.unary_union
    land_overlap = world_geo.intersection(ifg_geo)
    return (1 - land_overlap.area / ifg_geo.area) * 100


def download_slcs(reference_ids: list,
                  secondary_ids: list,
                  frame_id: int = -1,
                  max_workers_for_download: int = 5,
                  dry_run: bool = False) -> dict:
    reference_obs = get_asf_slc_objects(reference_ids)
    secondary_obs = get_asf_slc_objects(secondary_ids)

    # store properties so we don't have to retreive them again
    reference_props = [ob.properties for ob in reference_obs]
    secondary_props = [ob.properties for ob in secondary_obs]

    minutes_apart = 2
    if not ensure_repeat_pass_time_small(reference_props,
                                         maximum_minutes_between_acq=minutes_apart):
        raise ValueError('The reference SLCs are more than {minutes_apart} min'
                         'apart from the initial acq. in this pass')
    if not ensure_repeat_pass_time_small(secondary_props,
                                         maximum_minutes_between_acq=minutes_apart):
        raise ValueError('The secondary SLCs are more than {minutes_apart} min'
                         'apart from the initial acq. in this pass')

    if not check_flight_direction(reference_props + secondary_props):
        raise ValueError('The SLCs are not all Descending or Ascending')

    if not check_track_numbers(reference_props + secondary_props):
        raise ValueError('The SLCs do not belong to the same track (or sequential tracks)')

    if not check_date_order(reference_props, secondary_props):
        raise ValueError('Reference date must occur after secondary date')

    # Check the number of objects is the same as inputs
    assert len(reference_obs) == len(reference_ids)
    assert len(secondary_obs) == len(secondary_ids)

    ifg_geo = get_interferogram_geo(reference_obs,
                                    secondary_obs,
                                    frame_id=frame_id)

    percent_water_low_res = get_percent_water_from_ne_land(intersection_geo)
    if percent_water_low_res >= 80:
        warn(f'The IFG is {percent_water_low_res:1.2f}% water; '
             'If there are not enough bursts over land - ISCE2 will fail.',
             category=RuntimeWarning)

    def download_one(resp):
        session = get_session()
        file_name = resp.properties['fileName']
        if not dry_run:
            resp.download(path='.', session=session)
        return file_name

    processing_geo = ifg_geo
    if frame_id != -1:
        processing_geo = get_processing_geo_from_frame_id(frame_id)

    all_obs = reference_obs + secondary_obs
    n = len(all_obs)
    with ThreadPoolExecutor(max_workers=max_workers_for_download) as executor:
        results = list(tqdm(executor.map(download_one,
                                         all_obs),
                            total=n,
                            desc='Downloading SLCs'))

    n0 = len(reference_obs)
    return {'ref_paths': results[:n0],
            'sec_paths': results[n0:],
            'extent': list(ifg_geo.bounds),
            # For frames:
            # This is the expected extent with the submitted ROI bounds below,
            # i.e. all the bursts that overlap with the bbox - this will be used
            # to request the DEM extent which will be larger than the frame
            'gunw_geo': ifg_geo,
            # For frames:
            # Want to follow latitude aligned frames for ROI bbox field in ISCE2
            # This will be smaller than the actual ifg_geo/gunw_geo which
            # includes all the bursts that overlap this processing geometry.
            'processing_extent': list(processing_geo.bounds),
            'reference_properties': reference_props,
            'secondary_properties': secondary_props
            }
