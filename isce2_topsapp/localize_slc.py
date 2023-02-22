import netrc
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import asf_search as asf
import geopandas as gpd
from dateparser import parse
from shapely.geometry import GeometryCollection, shape
from shapely.ops import unary_union
from tqdm import tqdm


def get_global_gunw_frames():
    data_dir = Path(__file__).parent / 'data'
    path_to_frames_zip = data_dir / 'gunw_frame_footprints.geojson.zip'
    return gpd.read_file(path_to_frames_zip)


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


def get_intersection_geo(reference_obs: list,
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
    intersection_geo = secondary_geo.intersection(reference_geo)
    if intersection_geo.is_empty:
        raise ValueError('The overlap between reference and secondary scenes '
                         'is empty')

    # Update the area of interest based on frame_id
    if frame_id != -1:
        df_frames = get_global_gunw_frames()
        ind = df_frames.frame_id == frame_id
        df_frame = df_frames[ind].reset_index(drop=True)
        frame_geo = df_frame.geometry[0]
        if not frame_geo.intersects(intersection_geo):
            raise ValueError('Frame area does not overlap with IFG '
                             'area (i.e. ref and sec overlap)')
        intersection_geo = frame_geo
    return intersection_geo


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

    intersection_geo = get_intersection_geo(reference_obs,
                                            secondary_obs,
                                            frame_id=frame_id)

    def download_one(resp):
        session = get_session()
        file_name = resp.properties['fileName']
        if not dry_run:
            resp.download(path='.', session=session)
        return file_name

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
            'extent': list(intersection_geo.bounds),
            'intersection_geo': intersection_geo,
            'reference_properties': reference_props,
            'secondary_properties': secondary_props
            }
