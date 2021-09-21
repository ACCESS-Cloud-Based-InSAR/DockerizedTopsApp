import asf_search as asf
from shapely.geometry import shape, Polygon, GeometryCollection
from shapely.ops import unary_union
import dotenv
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor


def get_asf_slc_objects(slc_ids: list) -> list:

    response = asf.granule_search(slc_ids)

    def filter_by_type(response):
        props = response.properties
        return props['processingLevel'] == 'SLC'
    response = list(filter(filter_by_type, response))

    return response


def get_session():
    # usecwd ensures that env is searched for from current working directory
    # rather than the one where this script is installed.
    env_path = dotenv.find_dotenv(usecwd=True,
                                  raise_error_if_not_found=True)
    env_dict = dotenv.dotenv_values(env_path)
    earthdata_username = env_dict['earthdata_username']
    earthdata_password = env_dict['earthdata_password']

    session = asf.ASFSession()
    session.auth_with_creds(earthdata_username, earthdata_password)
    return session


def check_geometry(reference_obs: list,
                   secondary_obs: list) -> GeometryCollection:
    reference_geos = [shape(r.geojson()['geometry']) for r in reference_obs]
    secondary_geos = [shape(r.geojson()['geometry']) for r in secondary_obs]

    reference_geo = unary_union(reference_geos)
    secondary_geo = unary_union(secondary_geos)

    # Two geometries must intersect for their to be an interferogram
    intersection_geo = secondary_geo.intersection(reference_geo)
    assert(not intersection_geo.is_empty)
    # if they are not Polygons they are multipolygons and not valid
    assert(isinstance(secondary_geo, Polygon))
    assert(isinstance(reference_geo, Polygon))
    return intersection_geo


def download_slcs(reference_ids: list,
                  secondary_ids: list,
                  max_workers: int = 5,
                  dry_run: bool = False) -> dict:
    reference_obs = get_asf_slc_objects(reference_ids)
    secondary_obs = get_asf_slc_objects(secondary_ids)

    # Check the number of objects is the same as inputs
    assert(len(reference_obs) == len(reference_ids))
    assert(len(secondary_obs) == len(secondary_ids))

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
            'extent': list(intersection_geo.bounds)}
