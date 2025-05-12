import logging
import datetime
import geopandas as gpd
from typing import List, Optional
from dateparser import parse  # type: ignore
from datetime import timedelta
from shapely.geometry import Polygon

import asf_search as asf
from asf_search import ASFSearchResults


def query_slc_over_frame(
    frame_df: gpd.GeoDataFrame,
    max_results_per_frame: int = 100_000,
    allowable_polarizations: List[str] = ["VV", "VV+VH"],
    start_time: Optional[datetime.datetime] = None,
    stop_time: Optional[datetime.datetime] = None,
) -> ASFSearchResults:
    """
    Query Sentinel-1 SLC scenes over a frame using ASF's geo_search API.

    Parameters
    ----------
    frame_df : GeoDataFrame
        Frame geometry and metadata (must include 'geometry' and orbit number).
    max_results_per_frame : int
        Max number of scenes to return (default 100,000).
    allowable_polarizations : list of str
        Accepted polarizations (default ["VV", "VV+VH"]).
    start_time : datetime, optional
        Start of time window (UTC).
    stop_time : datetime, optional
        End of time window (UTC).

    Returns
    -------
    GeoDataFrame
        ASF SLC scenes with metadata and geometry.

    Raises
    ------
    ValueError
        If no scenes are found.
    """

    original_log_level = logging.getLogger().getEffectiveLevel()

    # Temporarily suppress warnings by setting a higher log level
    logging.getLogger().setLevel(logging.ERROR)
    try:
        results = asf.geo_search(
            platform=[asf.PLATFORM.SENTINEL1],
            intersectsWith=frame_df.geometry[0].wkt,
            maxResults=max_results_per_frame,
            relativeOrbit=frame_df.relative_orbit_number_min[0],
            polarization=allowable_polarizations,
            beamMode=[asf.BEAMMODE.IW],
            processingLevel=[asf.PRODUCT_TYPE.SLC],
            start=start_time,
            end=stop_time,
        )
        results = [r.geojson() for r in results]

        # Check if there search results
        if len(results) > 0:
            data = [r["properties"] for r in results]
            geom = [Polygon(r["geometry"]["coordinates"][0]) for r in results]
            return gpd.GeoDataFrame(data, geometry=geom, crs=4326)
        else:
            raise ValueError(
                "No S1-SLCs within specified period:"
                f" {start_time} - {stop_time}\n"
                "Refine search period!"
            )

    finally:
        # Restore the original log level
        logging.getLogger().setLevel(original_log_level)


def get_gunw_hits(record: dict) -> asf.ASFSearchResults:
    """
    Query ARIA GUNW interferograms using frame ID and reference/secondary dates.

    Parameters
    ----------
    record : dict
        Must include 'frame_id', 'reference_date', and 'secondary_date'.

    Returns
    -------
    list
        Matching GUNW ASF results.
    """

    frame_id = int(record["frame_id"])
    ref_date = parse(record["reference_date"])
    sec_date = parse(record["secondary_date"])

    start = ref_date - timedelta(days=1)
    end = ref_date + timedelta(days=1)
    tb_days = (ref_date - sec_date).days

    opts = asf.ASFSearchOptions(
        shortName="ARIA_S1_GUNW",
        asfFrame=frame_id,
        start=start,
        end=end,
        temporalBaselineDays=[tb_days],
        maxResults=3,
    )

    results = asf.search(opts=opts)

    return results
