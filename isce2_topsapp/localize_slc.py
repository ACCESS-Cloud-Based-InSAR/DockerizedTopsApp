import datetime
import netrc
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path
from warnings import warn

import asf_search as asf
import geopandas as gpd
from dateparser import parse  # type: ignore
from shapely.geometry import GeometryCollection, Polygon, shape
from shapely.ops import unary_union
from tqdm import tqdm


MIN_FRAME_COVERAGE_DEFAULT = 0.01
S1C_MIN_DATE = datetime.datetime(
    2025, 5, 19, tzinfo=datetime.UTC
)  # https://sentinels.copernicus.eu/-/sentinel-1c-products-are-now-calibrated
S1D_MIN_DATE = datetime.datetime(
    2026, 6, 24, tzinfo=datetime.UTC
)


def get_gunw_extent_from_frame_id(frame_id: int) -> Polygon:
    data_dir = Path(__file__).parent / 'data'
    path_to_frames_zip = data_dir / 's1_gunw_frame_footprints.geojson.zip'
    df_gunw_extent = gpd.read_file(path_to_frames_zip)
    ind = df_gunw_extent.frame_id == frame_id
    df_gunw = df_gunw_extent[ind].reset_index(drop=True)
    gunw_geo = df_gunw.geometry[0]
    return gunw_geo


def get_asf_slc_objects(slc_ids: list) -> list:
    response = asf.granule_search(slc_ids)

    def filter_by_type(response: asf.ASFProduct) -> bool:
        props = response.properties
        return props['processingLevel'] == 'SLC'

    response = list(filter(filter_by_type, response))

    return response


def get_session() -> asf.ASFSession:
    netrc_ob = netrc.netrc()

    earthdata_url = 'urs.earthdata.nasa.gov'
    username, _, password = netrc_ob.authenticators(earthdata_url)

    session = asf.ASFSession()
    session.auth_with_creds(username, password)
    return session


def get_interferogram_geo(
    reference_obs: list,
    secondary_obs: list,
    frame_id: int = -1,
    min_frame_coverage: float = MIN_FRAME_COVERAGE_DEFAULT,
) -> GeometryCollection:
    reference_geos = [shape(r.geojson()['geometry']) for r in reference_obs]
    secondary_geos = [shape(r.geojson()['geometry']) for r in secondary_obs]

    reference_geo = unary_union(reference_geos)
    secondary_geo = unary_union(secondary_geos)

    # if they are not Polygons they are multipolygons and not valid
    connected_ref = reference_geo.geom_type == 'Polygon'
    connected_sec = secondary_geo.geom_type == 'Polygon'

    if (not connected_sec) or (not connected_ref):
        raise ValueError('Reference and/or secondary dates were not connected in their coverage (multipolygons)')

    # Two geometries must intersect for their to be an interferogram
    ifg_geo = secondary_geo.intersection(reference_geo)
    if ifg_geo.is_empty:
        raise ValueError('The overlap between reference and secondary scenes is empty')

    # Update the area of interest based on frame_id
    if frame_id != -1:
        gunw_geo = get_gunw_extent_from_frame_id(frame_id)
        frame_coverage = gunw_geo.intersection(ifg_geo).area / gunw_geo.area
        if frame_coverage < min_frame_coverage:
            raise ValueError(
                f'IFG area (i.e. ref and sec overlap) covers only {frame_coverage * 100:.2f}% of Frame area; '
                f'the requested minimum coverage was {min_frame_coverage * 100:.2f}%.'
            )
        ifg_geo = gunw_geo
    return ifg_geo


def ensure_repeat_pass_time_small(slc_properties: list, maximum_minutes_between_acq: int = 2) -> bool:
    """Make sure all the dictionaries of startTime are within 5 minutes."""
    dates = [parse(prop['startTime']) for prop in slc_properties]
    dates = sorted(dates)
    minutes_apart_from_first_acq = [(date - dates[0]).seconds for date in dates]
    return all([minutes_apart <= maximum_minutes_between_acq * 60 for minutes_apart in minutes_apart_from_first_acq])


def check_flight_direction(slc_properties: list) -> bool:
    unique_look_direction = set([prop['flightDirection'] for prop in slc_properties])
    return len(unique_look_direction) == 1


def check_date_order(ref_properties: list, sec_properties: list) -> bool:
    ref_date = parse(ref_properties[0]['startTime'])
    sec_date = parse(sec_properties[0]['startTime'])
    return sec_date < ref_date


def check_if_s1c_has_valid_date(slc_ids: list, slc_properties: list) -> bool:
    assert len(slc_ids) == len(slc_properties)
    s1c_filter_bool = [id.startswith('S1C') for id in slc_ids]
    s1c_properties_filter = [prop for (k, prop) in enumerate(slc_properties) if s1c_filter_bool[k]]
    # No s1c data
    if not sum(s1c_filter_bool):
        return True
    s1c_ids = [id for (k, id) in enumerate(slc_ids) if s1c_filter_bool[k]]
    s1c_dates = [parse(prop['startTime']) for prop in s1c_properties_filter]
    s1c_valid_data_filter = [date >= S1C_MIN_DATE for date in s1c_dates]
    s1c_has_valid_date = all(s1c_valid_data_filter)
    if not s1c_has_valid_date:
        invalid_s1c_ids = [id for (k, id) in enumerate(s1c_ids) if not s1c_valid_data_filter[k]]
        print(f'The following S1C acquisitions were before {S1C_MIN_DATE}: {invalid_s1c_ids}')
    return s1c_has_valid_date


def check_if_s1d_has_valid_date(slc_ids: list, slc_properties: list) -> bool:
    assert len(slc_ids) == len(slc_properties)
    s1d_filter_bool = [id.startswith('S1D') for id in slc_ids]
    s1d_properties_filter = [
        prop for (k, prop) in enumerate(slc_properties) if s1d_filter_bool[k]
    ]
    # No s1d data
    if not sum(s1d_filter_bool):
        return True
    s1d_ids = [id for (k, id) in enumerate(slc_ids) if s1d_filter_bool[k]]
    s1d_dates = [parse(prop['startTime']) for prop in s1d_properties_filter]
    s1d_valid_data_filter = [date >= S1D_MIN_DATE for date in s1d_dates]
    s1d_has_valid_date = all(s1d_valid_data_filter)
    if not s1d_has_valid_date:
        invalid_s1d_ids = [
            id for (k, id) in enumerate(s1d_ids) if not s1d_valid_data_filter[k]
        ]
        print(
            f'The following S1D acquisitions were before {S1D_MIN_DATE}: {invalid_s1d_ids}'
        )
    return s1d_has_valid_date


def check_track_numbers(slc_properties: list) -> False:
    path_numbers = [prop['pathNumber'] for prop in slc_properties]
    path_numbers = sorted(list(set(path_numbers)))
    if len(path_numbers) == 1:
        return True
    if len(path_numbers) == 2:
        if (path_numbers[1] - path_numbers[0]) == 1:
            return True
    return False


@cache
def get_world_df() -> gpd.GeoDataFrame:
    data_dir = Path(__file__).parent / 'data'
    df_world = gpd.read_file(data_dir / 'ne_10m_land.zip')
    return df_world


def get_percent_water_from_ne_land(ifg_geo: Polygon) -> float:
    """Get percent_water using Natural Earth Low Res Mask."""
    df_world = get_world_df()
    world_geo = df_world.geometry.unary_union
    land_overlap = world_geo.intersection(ifg_geo)
    return (1 - land_overlap.area / ifg_geo.area) * 100


def download_slcs(
    reference_ids: list,
    secondary_ids: list,
    frame_id: int = -1,
    min_frame_coverage: float = MIN_FRAME_COVERAGE_DEFAULT,
    max_workers_for_download: int = 5,
    dry_run: bool = False,
    download_source: str = 'ASF',
) -> dict:
    reference_obs = get_asf_slc_objects(reference_ids)
    secondary_obs = get_asf_slc_objects(secondary_ids)

    # store properties so we don't have to retreive them again
    reference_props = [ob.properties for ob in reference_obs]
    secondary_props = [ob.properties for ob in secondary_obs]

    minutes_apart = 2
    if not ensure_repeat_pass_time_small(reference_props, maximum_minutes_between_acq=minutes_apart):
        raise ValueError('The reference SLCs are more than {minutes_apart} minapart from the initial acq. in this pass')
    if not ensure_repeat_pass_time_small(secondary_props, maximum_minutes_between_acq=minutes_apart):
        raise ValueError('The secondary SLCs are more than {minutes_apart} minapart from the initial acq. in this pass')

    if not check_flight_direction(reference_props + secondary_props):
        raise ValueError('The SLCs are not all Descending or Ascending')

    if not check_track_numbers(reference_props + secondary_props):
        raise ValueError('The SLCs do not belong to the same track (or sequential tracks)')

    if not check_date_order(reference_props, secondary_props):
        raise ValueError('Reference date must occur after secondary date')

    if not check_if_s1c_has_valid_date(reference_ids + secondary_ids, reference_props + secondary_props):
        raise ValueError(f'The Sentinel-1C acquisitions provided were before {S1C_MIN_DATE}')

    if not check_if_s1d_has_valid_date(
        reference_ids + secondary_ids, reference_props + secondary_props
    ):
        raise ValueError(
            f'The Sentinel-1D acquisitions provided were before {S1D_MIN_DATE}'
        )

    # Check the number of objects is the same as inputs
    assert len(reference_obs) == len(reference_ids)
    assert len(secondary_obs) == len(secondary_ids)

    ifg_geo = get_interferogram_geo(
        reference_obs,
        secondary_obs,
        frame_id=frame_id,
        min_frame_coverage=min_frame_coverage,
    )

    percent_water_low_res = get_percent_water_from_ne_land(ifg_geo)
    if percent_water_low_res >= 80:
        warn(
            f'The IFG is {percent_water_low_res:1.2f}% water; '
            'If there are not enough bursts over land - ISCE2 will fail.',
            category=RuntimeWarning,
        )

    processing_geo = ifg_geo
    if frame_id != -1:
        processing_geo = _get_frame_by_id(frame_id).geometry

    if download_source == 'CDSE':
        from isce2_topsapp.localize_slc_cdse import download_slcs_from_cdse

        all_ids = reference_ids + secondary_ids
        results = download_slcs_from_cdse(
            all_ids,
            output_dir='.',
            max_workers=max_workers_for_download,
            dry_run=dry_run,
        )
    else:

        def download_one(resp: asf.ASFProduct) -> str:
            session = get_session()
            file_name = resp.properties['fileName']
            if not dry_run:
                resp.download(path='.', session=session)
            return file_name

        all_obs = reference_obs + secondary_obs
        n = len(all_obs)
        with ThreadPoolExecutor(max_workers=max_workers_for_download) as executor:
            results = list(
                tqdm(
                    executor.map(download_one, all_obs),
                    total=n,
                    desc='Downloading SLCs',
                )
            )

    n0 = len(reference_obs)
    return {
        'ref_paths': results[:n0],
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
        'secondary_properties': secondary_props,
    }


def _get_frame_by_id(frame_id: int) -> gpd.GeoSeries:
    frames = gpd.read_file(Path(__file__).parent / 'data' / 's1_frames_latitude_aligned.geojson.zip')
    return frames[frames.frame_id == frame_id].reset_index(drop=True).iloc[0]


def _get_dates(product: asf.ASFProduct) -> set[datetime.date]:
    date_strings = [product.properties[field].strip('Z') for field in ['startTime', 'stopTime']]
    return {datetime.datetime.fromisoformat(date_string).date() for date_string in date_strings}


def get_slcs_for_date_and_frame(date: datetime.date, frame_id: int) -> list[str]:
    frame = _get_frame_by_id(frame_id)
    date_as_datetime = datetime.datetime(year=date.year, month=date.month, day=date.day)
    results = asf.search(
        dataset=asf.constants.DATASET.SENTINEL1,
        processingLevel=asf.constants.PRODUCT_TYPE.SLC,
        beamMode=asf.constants.BEAMMODE.IW,
        polarization=[asf.constants.POLARIZATION.VV, asf.constants.POLARIZATION.VV_VH],
        flightDirection=frame.orbit_direction,
        relativeOrbit=list({frame.relative_orbit_number_min, frame.relative_orbit_number_max}),
        intersectsWith=frame.geometry.wkt,
        start=date_as_datetime - datetime.timedelta(minutes=5),
        end=date_as_datetime + datetime.timedelta(days=1, minutes=5),
    )
    if not any(
        product_date == date
        for product in results
        for product_date in _get_dates(product)
    ):
        raise ValueError(
            f'No Sentinel-1A/1B/1C/1D SLCs found for date {date} and frame id {frame_id}.'
        )

    return [result.properties['sceneName'] for result in results]
