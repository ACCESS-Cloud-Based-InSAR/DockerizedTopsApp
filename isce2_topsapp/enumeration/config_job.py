import pandas as pd
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser


from .s1_stack import (
    get_processing_df,
    format_results,
    filter_min_coverage,
    find_date,
)
from .asf_query import query_slc_over_frame, get_gunw_hits


def _ensure_utc(dt):
    dt = pd.to_datetime(dt)
    return dt if dt.tzinfo else dt.tz_localize("UTC")


def get_job_config(frame_id: int, reference_date: str, secondary_date: str) -> dict:
    # Get frame geometry
    frame_df = get_processing_df(frame_id)

    # Query SLC archive over the frame
    asf_results = query_slc_over_frame(frame_df)

    # Format results
    df_formatted = format_results(asf_results)

    # Filter out dates with insufficient frame coverage
    df_formatted, dropped_dates = filter_min_coverage(
        df_formatted, frame_df, min_coverage=0.95
    )

    print(
        f"Frame {frame_df.frame_id[0]}: "
        f"Number of dropped dates {len(dropped_dates)}: {dropped_dates}"
    )

    if df_formatted.empty:
        raise ValueError(
            "All dates were dropped due to insufficient coverage. No valid SLCs remain."
        )

    # Convert and order reference/secondary dates
    ref_dt = _ensure_utc(reference_date)
    sec_dt = _ensure_utc(secondary_date)

    # Force reference date to be later date
    if ref_dt < sec_dt:
        ref_dt, sec_dt = sec_dt, ref_dt

    # Find matching repeat-pass groups
    try:
        ref_df = find_date(df_formatted, ref_dt)
    except ValueError as e:
        raise ValueError(f"Reference date error: {e}")

    try:
        sec_df = find_date(df_formatted, sec_dt)
    except ValueError as e:
        raise ValueError(f"Secondary date error: {e}")

    output = {
        "reference": ref_df.slc_id.to_list(),
        "secondary": sec_df.slc_id.to_list(),
        "reference_date": ref_dt.strftime("%Y-%m-%d"),
        "secondary_date": sec_dt.strftime("%Y-%m-%d"),
        "frame_id": frame_df.frame_id[0],
        "geometry": frame_df.geometry[0].wkt,
    }

    # Check if ARIA GUNW already exists
    aria_s1_hits = get_gunw_hits(output)
    if len(aria_s1_hits) > 0:
        filename = aria_s1_hits.data[0].properties["fileName"]
        raise ValueError(
            f"GUNW exists: {filename}!\nSkip generation of topsApp job config."
        )
    return output


def main():
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("--frame-id", type=int, required=True)
    parser.add_argument("--reference-date", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument("--secondary-date", type=str, required=True, help="YYYY-MM-DD")

    args = parser.parse_args()

    try:
        config = get_job_config(args.frame_id, args.reference_date, args.secondary_date)
        print(config)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
