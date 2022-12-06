import netrc
from concurrent.futures import ThreadPoolExecutor

import asf_search as asf
from shapely.geometry import GeometryCollection, Polygon, shape
from shapely.ops import unary_union
from tqdm import tqdm

from .dateline import unwrap_geometry


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


def _unwrap_one(geometry: Polygon):
    xmin, _, xmax, _ = geometry.bounds
    if (xmin < -150) and (xmax > 150):
        return unwrap_geometry(geometry)
    else:
        return geometry


def check_geometry(reference_obs: list,
                   secondary_obs: list) -> GeometryCollection:
    reference_geos = [shape(r.geojson()['geometry']) for r in reference_obs]
    secondary_geos = [shape(r.geojson()['geometry']) for r in secondary_obs]

    # Only unwrapes if (xmin < -150) and (xmax > 150)
    reference_geos = list(map(_unwrap_one, reference_geos))
    secondary_geos = list(map(_unwrap_one, secondary_geos))

    reference_geo = unary_union(reference_geos)
    secondary_geo = unary_union(secondary_geos)

    # Two geometries must intersect for their to be an interferogram
    intersection_geo = secondary_geo.intersection(reference_geo)
    assert not intersection_geo.is_empty

    # if they are not Polygons they are multipolygons and not valid
    assert isinstance(secondary_geo, Polygon)
    assert isinstance(reference_geo, Polygon)
    return intersection_geo


def download_slcs(reference_ids: list,
                  secondary_ids: list,
                  max_workers: int = 5,
                  dry_run: bool = False) -> dict:
    reference_obs = get_asf_slc_objects(reference_ids)
    secondary_obs = get_asf_slc_objects(secondary_ids)

    # store properties so we don't have to retreive them again
    reference_props = [ob.properties for ob in reference_obs]
    secondary_props = [ob.properties for ob in secondary_obs]

    # Check the number of objects is the same as inputs
    assert len(reference_obs) == len(reference_ids)
    assert len(secondary_obs) == len(secondary_ids)

    intersection_geo = check_geometry(reference_obs, secondary_obs)

    def download_one(resp):
        session = get_session()
        file_name = resp.properties['fileName']
        if not dry_run:
            resp.download(path='.', session=session)
        return file_name

    all_obs = reference_obs + secondary_obs
    n = len(all_obs)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
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
