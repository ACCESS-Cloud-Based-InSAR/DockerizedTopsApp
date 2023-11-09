import json
import math
import netrc
import os
import sys
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, Namespace
from importlib.metadata import entry_points
from pathlib import Path
from typing import Optional

from isce2_topsapp import (BurstParams,
                           aws,
                           download_aux_cal,
                           download_bursts,
                           download_dem_for_isce2,
                           download_orbits,
                           download_slcs,
                           download_water_mask,
                           get_asf_slc_objects,
                           get_region_of_interest,
                           package_gunw_product,
                           prepare_for_delivery,
                           topsappParams,
                           topsapp_processing,
                           )
from isce2_topsapp.iono_proc import iono_processing
from isce2_topsapp.json_encoder import MetadataEncoder
from isce2_topsapp.packaging import update_gunw_internal_version_attribute
from isce2_topsapp.solid_earth_tides import update_gunw_with_solid_earth_tide


def localize_data(
    reference_scenes: list,
    secondary_scenes: list,
    frame_id: int = -1,
    dry_run: bool = False,
    water_mask_flag: bool = True,
    geocode_resolution: int = 90

) -> dict:
    """The dry-run prevents gets necessary metadata from SLCs and orbits.

    Can be used to run workflow without redownloading data (except DEM).

    Fixed frames are found here: s3://s1-gunw-frames/s1_frames.geojson
    And discussed in the readme.
    """
    breakpoint()
    out_slc = download_slcs(
        reference_scenes, secondary_scenes, frame_id=frame_id, dry_run=dry_run
    )

    out_orbits = download_orbits(
        reference_scenes, secondary_scenes, dry_run=dry_run)

    out_dem = {}
    out_aux_cal = {}
    if not dry_run:
        out_dem = download_dem_for_isce2(out_slc['extent'],
                                         geocode_resolution=geocode_resolution)

        out_water_mask = {"water_mask": None}
        # For ionospheric correction computation
        if water_mask_flag:
            out_water_mask = download_water_mask(
                out_slc["extent"],  water_name='SWBD')

        out_aux_cal = download_aux_cal()

    out = {'reference_scenes': reference_scenes,
           'secondary_scenes': secondary_scenes,
           'frame_id': frame_id,
           **out_slc,
           **out_dem,
           **out_water_mask,
           **out_aux_cal,
           **out_orbits}
    return out


def ensure_earthdata_credentials(
    username: Optional[str] = None,
    password: Optional[str] = None,
    host: str = "urs.earthdata.nasa.gov",
):
    """Ensures Earthdata credentials are provided in ~/.netrc

    Earthdata username and password may be provided by, in order of preference, one of:
       * `netrc_file`
       * `username` and `password`
       * `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` environment variables
    and will be written to the ~/.netrc file if it doesn't already exist.
    """
    if username is None:
        username = os.getenv("EARTHDATA_USERNAME")

    if password is None:
        password = os.getenv("EARTHDATA_PASSWORD")

    netrc_file = Path.home() / ".netrc"
    if not netrc_file.exists() and username and password:
        netrc_file.write_text(
            f"machine {host} login {username} password {password}")
        netrc_file.chmod(0o000600)

    try:
        dot_netrc = netrc.netrc(netrc_file)
        username, _, password = dot_netrc.authenticators(host)
    except (FileNotFoundError, netrc.NetrcParseError, TypeError):
        raise ValueError(
            f"Please provide valid Earthdata login credentials via {netrc_file}, "
            f"username and password options, or "
            f"the EARTHDATA_USERNAME and EARTHDATA_PASSWORD environment variables."
        )


def true_false_string_argument(s: str) -> bool:
    s = s.lower()
    if s not in ("true", "false"):
        raise ValueError(
            "Only the strings `true` or `false` (any capitalization) may be provided."
        )
    return s == "true"


def esd_threshold_argument(threshold: str) -> float:
    threshold_float = float(threshold)

    if math.isclose(threshold_float, -1.0):
        return threshold_float

    if (0.0 > threshold_float) or (threshold_float > 1.0):
        raise ValueError(
            "ESD coherence threshold should be a value between 0 and 1,"
            " or -1 for no ESD correction"
        )
    return threshold_float


def get_slc_parser():
    parser = ArgumentParser()
    parser.add_argument('--username')
    parser.add_argument('--password')
    parser.add_argument('--bucket')
    parser.add_argument('--bucket-prefix', default='')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--reference-scenes', type=str.split, nargs='+', required=True)
    parser.add_argument('--secondary-scenes', type=str.split, nargs='+', required=True)
    parser.add_argument('--estimate-ionosphere-delay', type=true_false_string_argument, default=True)
    parser.add_argument('--frame-id', type=int, default=-1, required=True)
    parser.add_argument('--compute-solid-earth-tide', type=true_false_string_argument, default=True)
    parser.add_argument('--esd-coherence-threshold', type=float, default=-1.)
    parser.add_argument('--output-resolution', type=int, default=90, required=False)
    parser.add_argument('--unfiltered-coherence', type=true_false_string_argument, default=True)
    parser.add_argument('--dense-offsets', type=true_false_string_argument, default=False)
    parser.add_argument('--wrapped-phase-layer', type=true_false_string_argument, default=False)
    parser.add_argument('--goldstein-filter-power', type=float, default=.4)
    return parser


def update_slc_namespace(args: Namespace) -> Namespace:

    args.reference_scenes = [
        item for sublist in args.reference_scenes for item in sublist
    ]
    args.secondary_scenes = [
        item for sublist in args.secondary_scenes for item in sublist
    ]
    return args


def gunw_slc():
    cmd_line_str = 'isce2_topsapp ++' + ' '.join(sys.argv)

    parser = get_slc_parser()
    args = parser.parse_args()
    args = update_slc_namespace(args)

    # Validation
    ensure_earthdata_credentials(args.username, args.password)

    cli_params = vars(args)
    [cli_params.pop(key) for key in ['username', 'password', 'bucket', 'bucket_prefix', 'dry_run']]
    topsapp_params_obj = topsappParams(**cli_params)

    # serialize input
    json.dump(topsapp_params_obj.model_dump(),
              open('topsapp_input_params.json', 'w'),
              indent=2)

    # Region of interest becomes 'extent' in loc_data
    loc_data = localize_data(
        args.reference_scenes,
        args.secondary_scenes,
        dry_run=args.dry_run,
        geocode_resolution=args.output_resolution,
        frame_id=args.frame_id,
        water_mask_flag=args.estimate_ionosphere_delay,
    )
    loc_data["frame_id"] = args.frame_id

    # Allows for easier re-inspection of processing, packaging, and delivery
    # after job completes
    json.dump(loc_data, open("loc_data.json", "w"),
              indent=2, cls=MetadataEncoder)

    # Turn-off ESD when using ionospheric computation
    # NOTE: note sure if this needs to be off
    #       esd is calculated with iono only when
    #       considerBurstProperties is on which off
    #       by default
    if args.estimate_ionosphere_delay:
        args.esd_coherence_threshold = -1

    topsapp_processing(
        reference_slc_zips=loc_data["ref_paths"],
        secondary_slc_zips=loc_data["sec_paths"],
        orbit_directory=loc_data["orbit_directory"],
        # Region of interest is passed to topsapp via 'extent' key in loc_data
        extent=loc_data["processing_extent"],
        estimate_ionosphere_delay=False,
        do_esd=args.esd_coherence_threshold >= 0.0,
        esd_coherence_threshold=args.esd_coherence_threshold,
        dem_for_proc=loc_data["full_res_dem_path"],
        dem_for_geoc=loc_data["low_res_dem_path"],
        dry_run=args.dry_run,
        do_dense_offsets=args.dense_offsets,
        wrapped_phase_layer=args.wrapped_phase_layer,
        goldstein_filter_power=args.goldstein_filter_power,
        output_resolution=args.output_resolution
    )

    # Run ionospheric correction
    if args.estimate_ionosphere_delay:
        iono_attr = iono_processing(
            mask_filename=loc_data["water_mask"],
            correct_burst_ramps=True,
        )

    ref_properties = loc_data["reference_properties"]
    sec_properties = loc_data["secondary_properties"]
    extent = loc_data["extent"]

    additional_2d_layers_for_packaging = []
    additional_attributes_for_packaging = []
    if args.estimate_ionosphere_delay:
        additional_2d_layers_for_packaging.append("ionosphere")
        additional_attributes_for_packaging.append(iono_attr['ionosphere'])
        additional_2d_layers_for_packaging.append("ionosphereBurstRamps")
        additional_attributes_for_packaging.append(iono_attr['ionosphereBurstRamps'])
    if args.dense_offsets:
        additional_2d_layers_for_packaging.append('rangePixelOffsets')
        additional_2d_layers_for_packaging.append('azimuthPixelOffsets')
    if args.unfiltered_coherence:
        additional_2d_layers_for_packaging.append('unfilteredCoherence')

    additional_2d_layers_for_packaging = additional_2d_layers_for_packaging or None

    nc_path = package_gunw_product(
        isce_data_directory=Path.cwd(),
        reference_properties=ref_properties,
        secondary_properties=sec_properties,
        extent=extent,
        additional_2d_layers=additional_2d_layers_for_packaging,
        additional_attributes=additional_attributes_for_packaging,
        standard_product=params.is_standard_gunw_product(),
        cmd_line_str=cmd_line_str,
        topaspp_params=topsapp_params_obj.model_dump()
    )

    if args.compute_solid_earth_tide:
        nc_path = update_gunw_with_solid_earth_tide(nc_path, "reference", loc_data['reference_orbits'])
        nc_path = update_gunw_with_solid_earth_tide(nc_path, "secondary", loc_data['secondary_orbits'])

    if args.compute_solid_earth_tide or args.estimate_ionosphere_delay:
        update_gunw_internal_version_attribute(nc_path, new_version="1c")

    # Move final product to current working directory
    final_directory = prepare_for_delivery(nc_path, loc_data)

    if args.bucket:
        for file in final_directory.glob("S1-GUNW*"):
            aws.upload_file_to_s3(file, args.bucket, args.bucket_prefix)


def gunw_burst():
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--bucket")
    parser.add_argument("--bucket-prefix", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reference-scene", type=str, required=True)
    parser.add_argument("--secondary-scene", type=str, required=True)
    parser.add_argument("--image-number", type=int, required=True)
    parser.add_argument("--burst-number", type=int, required=True)
    parser.add_argument("--azimuth-looks", type=int, default=2)
    parser.add_argument("--range-looks", type=int, default=10)
    parser.add_argument(
        "--estimate-ionosphere-delay", type=true_false_string_argument, default=False
    )
    args = parser.parse_args()

    ensure_earthdata_credentials(args.username, args.password)

    ref_obj, sec_obj = get_asf_slc_objects(
        [args.reference_scene, args.secondary_scene])

    ref_params = BurstParams(
        safe_url=ref_obj.properties["url"],
        image_number=args.image_number,
        burst_number=args.burst_number,
    )
    sec_params = BurstParams(
        safe_url=sec_obj.properties["url"],
        image_number=args.image_number,
        burst_number=args.burst_number,
    )

    ref_burst, sec_burst = download_bursts([ref_params, sec_params])

    intersection = ref_burst.footprint.intersection(sec_burst.footprint).bounds
    is_ascending = ref_burst.orbit_direction == "ascending"
    roi = get_region_of_interest(
        ref_burst.footprint, sec_burst.footprint, is_ascending=is_ascending
    )

    orbits = download_orbits(
        [ref_burst.safe_name[:-5]], [sec_burst.safe_name[:-5]], dry_run=args.dry_run
    )

    if not args.dry_run:
        # TODO this is likely not the optimal geometry to pass to this function
        dem = download_dem_for_isce2(intersection)
        _ = download_aux_cal()

    # TODO fails when using the default 19x7 looks
    topsapp_processing(
        reference_slc_zips=ref_burst.safe_name,
        secondary_slc_zips=sec_burst.safe_name,
        orbit_directory=orbits["orbit_directory"],
        extent=roi,
        dem_for_proc=dem["full_res_dem_path"],
        dem_for_geoc=dem["low_res_dem_path"],
        estimate_ionosphere_delay=False,
        azimuth_looks=args.azimuth_looks,
        range_looks=args.range_looks,
        swaths=[ref_burst.swath],
        dry_run=args.dry_run,
    )

    # Run ionospheric correction
    if args.estimate_ionosphere_delay:
        iono_processing(
            reference_slc_zips=ref_burst.safe_name,
            secondary_slc_zips=sec_burst.safe_name,
            orbit_directory=orbits["orbit_directory"],
            extent=roi,
            dem_for_proc=dem["full_res_dem_path"],
            dem_for_geoc=dem["low_res_dem_path"],
            azimuth_looks=args.azimuth_looks,
            range_looks=args.range_looks,
            swaths=[ref_burst.swath],
            mask_filename=None,
        )

    if args.bucket:
        for file in Path("merged").glob("*geo*"):
            aws.upload_file_to_s3(file, args.bucket, args.bucket_prefix)


def main():
    parser = ArgumentParser(
        prefix_chars="+", formatter_class=ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "++process",
        choices=["gunw_slc", "gunw_burst"],
        default="gunw_slc",
        help="Select the HyP3 entrypoint to use",
    )
    parser.add_argument(
        "++omp-num-threads",
        type=int,
        help=("The number of OpenMP threads to use for parallel processing in ISCE2 routines; "
              "when running locally, this topsapp will utilize all resources, which is not recommended; "
              "suggest to set this option to 8 - 16 so other processes on server/workstation can running.")
    )

    args, unknowns = parser.parse_known_args()

    if args.omp_num_threads:
        os.environ["OMP_NUM_THREADS"] = str(args.omp_num_threads)

    sys.argv = [args.process, *unknowns]
    # FIXME: this gets better in python 3.10
    # (process_entry_point,) = entry_points(group='console_scripts', name=args.process)
    process_entry_point = [
        ep for ep in entry_points()["console_scripts"] if ep.name == args.process
    ][0]
    sys.exit(process_entry_point.load()())


if __name__ == "__main__":
    main()
