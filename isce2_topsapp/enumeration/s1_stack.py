from pathlib import Path
import warnings
from typing import Union, Tuple
from datetime import timedelta

import pandas as pd
import geopandas as gpd

from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry.polygon import orient

S1_COLUMNS = [
    "slc_id",
    "start_time",
    "stop_time",
    "url",
    "track_number",
    "polarization",
    "orbit",
    "beam_mode",
    "size_gb",
    "flight_direction",
    "stack_repeat_pass_id",
    "repeat_pass_timestamp",
    "geometry",
]


def drop_z(geom: Polygon) -> Polygon:
    """
    Remove Z dimension from geometry if present.

    Parameters
    ----------
    geom : shapely.geometry.Polygon
        Geometry with or without Z-values.

    Returns
    -------
    Polygon
        2D polygon with Z-values removed.
    """
    if geom.has_z:
        coords_2d = [(x, y) for x, y, *_ in geom.exterior.coords]
        geom = Polygon(coords_2d)
    return geom


# Correct winding order (counter-clockwise)
def correct_winding(geom: Polygon) -> Polygon:
    """
    Ensure polygon winding is counter-clockwise.

    Parameters
    ----------
    geom : shapely.geometry.Polygon
        Input polygon geometry.

    Returns
    -------
    Polygon
        Oriented polygon.
    """
    return orient(geom, sign=1.0)


def get_processing_df(frame_id: int) -> gpd.GeoDataFrame:
    """
    Load frame geometry from GeoJSON and prepare for ASF query.

    Parameters
    ----------
    frame_id : int
        Sentinel-1 frame ID to extract.

    Returns
    -------
    GeoDataFrame
        Geometry and metadata for given frame.
    """
    data_dir = Path(__file__).parents[1] / "data"
    path_to_frames_zip = data_dir / "s1_frames_latitude_aligned.geojson.zip"
    df_frames = gpd.read_file(path_to_frames_zip, crs=4326)
    ind = df_frames.frame_id == frame_id
    df_frame = df_frames[ind].reset_index(drop=True)
    df_frame["geometry"] = df_frame["geometry"].apply(drop_z).apply(correct_winding)
    return df_frame


def format_results(df_asf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Format ASF search results into a consistent GeoDataFrame.

    Parameters
    ----------
    df_asf : GeoDataFrame
        ASF raw search results.

    Returns
    -------
    GeoDataFrame
        Cleaned and organized results with stack info.
    """
    df_formatted = gpd.GeoDataFrame(columns=S1_COLUMNS, geometry=[], crs=4326)
    if df_asf.empty:
        return df_formatted

    df_formatted["slc_id"] = df_asf["fileID"].map(
        lambda file_id: file_id.replace("-SLC", "")
    )
    df_formatted["start_time"] = pd.to_datetime(df_asf.startTime)
    df_formatted["stop_time"] = pd.to_datetime(df_asf.stopTime)
    df_formatted["url"] = df_asf["url"]
    df_formatted["track_number"] = df_asf["pathNumber"].astype(int)
    df_formatted["orbit"] = df_asf["orbit"].astype(int)
    df_formatted["polarization"] = df_asf["polarization"]
    df_formatted["beam_mode"] = df_asf["beamModeType"]
    df_formatted["size_gb"] = df_asf["bytes"] / 1e9
    df_formatted["geometry"] = df_asf["geometry"]
    df_formatted["flight_direction"] = df_asf["flightDirection"]

    # Drop duplicate rows and sort by acq time
    df_formatted.drop_duplicates(subset=["slc_id"], inplace=True)
    df_formatted = df_formatted.sort_values(
        by=["start_time", "track_number"]
    ).reset_index(drop=True)

    # Want to group S1 imagery by repeat pass date
    # technically this could be at midnight so we do some work.
    # First we get ids based on julian date, then we group by first date in group
    julian_dates = df_formatted.start_time.map(lambda dt: dt.to_julian_date())
    # Note this calculus depends on the repeat pass frequency of Sentinel-1 which is 6
    df_formatted["stack_repeat_pass_id"] = (
        (julian_dates - julian_dates[0]) // 5
    ).astype(int)
    # Ensure sequential (see: https://stackoverflow.com/a/15074395)
    df_formatted["stack_repeat_pass_id"] = df_formatted.groupby(
        ["stack_repeat_pass_id"]
    ).ngroup()

    df_temp = pd.DataFrame(columns=["stack_repeat_pass_id", "repeat_pass_timestamp"])
    df_temp["stack_repeat_pass_id"] = df_formatted.stack_repeat_pass_id
    # We want the UTC date - however timestamps are serializable (dates are currently not)
    df_temp["repeat_pass_timestamp"] = pd.to_datetime(df_formatted.start_time.dt.date)
    # Requires UTC timzone
    df_temp.repeat_pass_timestamp = df_temp.repeat_pass_timestamp.map(
        lambda ts: ts.tz_localize("UTC")
    )
    # Get the min date in group
    df_repeat_pass_timestamp = df_temp.groupby("stack_repeat_pass_id").min()
    # look up min date based on group
    repeat_pass_dict = df_repeat_pass_timestamp.to_dict()["repeat_pass_timestamp"]
    df_formatted["repeat_pass_timestamp"] = df_formatted.stack_repeat_pass_id.map(
        lambda rp_id: repeat_pass_dict[rp_id]
    )

    return df_formatted


def filter_min_coverage(
    stack_df: gpd.GeoDataFrame, frame_df: gpd.GeoDataFrame, min_coverage: float = 0.95
) -> Tuple[gpd.GeoDataFrame, list]:
    """
    Filter repeat-pass dates with coverage above threshold.

    Parameters
    ----------
    stack_df : GeoDataFrame
        Formatted ASF results with repeat-pass timestamps.
    frame_df : GeoDataFrame
        Frame polygon for intersection check.
    min_coverage : float
        Minimum area overlap ratio (default 0.95).

    Returns
    -------
    tuple
        Filtered GeoDataFrame and list of excluded dates.
    """

    gdf_union = (
        stack_df.groupby("repeat_pass_timestamp")["geometry"]
        .apply(lambda g: g.unary_union)
        .reset_index()
    )

    # Convert to GeoDataFrame
    gdf_union = gpd.GeoDataFrame(gdf_union, geometry="geometry", crs=4326)

    # NOTE Check if there is a multiploygon, drop as that indicates a gap
    gdf_union["is_multipolygon"] = gdf_union.geometry.apply(
        lambda geom: isinstance(geom, MultiPolygon)
    )
    gdf_union = gdf_union[~gdf_union.is_multipolygon]

    # Frame area
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Geometry is in a geographic CRS.*")
        frame_area = frame_df.geometry[0].area
        frame_intersection = gdf_union.intersection(frame_df.geometry[0])
        intersection_ratio = frame_intersection.area / frame_area

    stack_ind = gdf_union[intersection_ratio > min_coverage]
    stack_ind = stack_df.repeat_pass_timestamp.isin(stack_ind.repeat_pass_timestamp)
    dates_no_coverage = gdf_union[intersection_ratio < min_coverage]

    dates_no_coverage = dates_no_coverage.repeat_pass_timestamp.dt.strftime("%Y-%m-%d")

    return stack_df[stack_ind].reset_index(drop=True), dates_no_coverage.to_list()


def find_date(
    stack_df: gpd.GeoDataFrame, date: Union[str, pd.Timestamp], time_buffer: int = 1
) -> gpd.GeoDataFrame:
    """
    Find dates near the specified timestamp in the stack.

    Parameters
    ----------
    stack_df : GeoDataFrame
        ASF results with repeat-pass timestamps.
    date : str or Timestamp
        Reference date.
    time_buffer : int
        Days before/after to search (default 1).

    Returns
    -------
    GeoDataFrame
        Matching entries within time buffer.

    Raises
    ------
    ValueError
        If no date within buffer is found.
    """

    date = pd.Timestamp(date).tz_convert("UTC")

    start = date - timedelta(days=time_buffer)
    end = date + timedelta(days=time_buffer)

    selection = stack_df.repeat_pass_timestamp.between(start, end)
    if selection.sum() > 0:
        return stack_df[selection]
    else:
        # Find the nearest date
        before = stack_df[stack_df.repeat_pass_timestamp < date]
        after = stack_df[stack_df.repeat_pass_timestamp > date]

        if not before.empty:
            near_before = before.loc[
                before.repeat_pass_timestamp.sub(date).abs().idxmin()
            ]
            near_before = near_before.repeat_pass_timestamp.strftime("%Y-%m-%d")
        else:
            near_before = None

        if not after.empty:
            near_after = after.loc[after.repeat_pass_timestamp.sub(date).abs().idxmin()]
            near_after = near_after.repeat_pass_timestamp.strftime("%Y-%m-%d")
        else:
            near_after = None

        raise ValueError(
            f'Specified date: {date.strftime("%Y-%m-%d")}'
            " does not exist in the stack!\n"
            f"    Nearest date available: {near_before} or {near_after}"
        )
