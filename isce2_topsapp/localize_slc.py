import netrc
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import asf_search as asf
import geopandas as gpd
from shapely.geometry import GeometryCollection, shape
from shapely.ops import unary_union
from tqdm import tqdm


def get_global_gunw_frames():
    data_dir = Path(__file__).parent / 'data'
    path_to_frames_zip = data_dir / 's1_frames.geojson.zip'
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


def check_geometry(reference_obs: list,
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
        raise RuntimeError('Reference and/or secondary dates were not connected'
                           ' in their coverage (multipolygons)')

    # Two geometries must intersect for their to be an interferogram
    intersection_geo = secondary_geo.intersection(reference_geo)
    if intersection_geo.is_empty:
        raise RuntimeError('The overlap between reference and secondary scenes '
                           'is empty')

    # Update the area of interest based on frame_id
    if frame_id != -1:
        df_frames = get_global_gunw_frames()
        ind = df_frames.frame_id == frame_id
        df_frame = df_frames[ind].reset_index(drop=True)
        frame_geo = df_frame.geometry[0]
        if not frame_geo.interects(intersection_geo):
            raise RuntimeError('Frame area does not overlap with IFG '
                               'area (i.e. ref and sec overlap)')
        intersection_geo = frame_geo
    return intersection_geo


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

    # Check the number of objects is the same as inputs
    assert len(reference_obs) == len(reference_ids)
    assert len(secondary_obs) == len(secondary_ids)

    intersection_geo = check_geometry(reference_obs,
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
