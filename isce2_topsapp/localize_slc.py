import netrc
from concurrent.futures import ThreadPoolExecutor

import asf_search as asf
from shapely.geometry import GeometryCollection, box, shape
from shapely.ops import unary_union
from tqdm import tqdm


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
                   region_of_interest: list) -> GeometryCollection:
    reference_geos = [shape(r.geojson()['geometry']) for r in reference_obs]
    secondary_geos = [shape(r.geojson()['geometry']) for r in secondary_obs]

    reference_geo = unary_union(reference_geos)
    secondary_geo = unary_union(secondary_geos)

    # Two geometries must intersect for their to be an interferogram
    intersection_geo = secondary_geo.intersection(reference_geo)
    if intersection_geo.is_empty:
        raise RuntimeError('The overlap between reference and secondary scenes '
                           'is empty')

    # Update the area of interest based on user specification
    if region_of_interest is not None:
        region_of_interest_geo = box(*region_of_interest)
        if not region_of_interest_geo.intersects(intersection_geo):
            raise RuntimeError('Region of interest does not overlap with IFG '
                               'area (ref and sec overlap)')
        intersection_geo = region_of_interest_geo

    # if they are not Polygons they are multipolygons and not valid
    connected_ref = (reference_geo.geom_type == 'Polygon')
    connected_sec = (secondary_geo.geom_type == 'Polygon')
    if (not connected_sec) or (not connected_ref):
        raise RuntimeError('Reference and/or secondary dates were not connected'
                           ' in their coverage (multipolygons)')
    return intersection_geo


def download_slcs(reference_ids: list,
                  secondary_ids: list,
                  region_of_interest: list = None,
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
                                      region_of_interest=region_of_interest)

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
