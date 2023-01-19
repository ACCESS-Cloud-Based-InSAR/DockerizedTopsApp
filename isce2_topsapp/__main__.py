import json
import netrc
import os
import sys
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from importlib.metadata import entry_points
from pathlib import Path
from typing import Optional


from isce2_topsapp import (BurstParams, aws, download_aux_cal, download_bursts,
                           download_dem_for_isce2, download_orbits,
                           download_slcs, get_asf_slc_objects, get_region_of_interest,
                           package_gunw_product, prepare_for_delivery,
                           topsapp_processing)
from isce2_topsapp.json_encoder import MetadataEncoder


def localize_data(reference_scenes: list,
                  secondary_scenes: list,
                  region_of_interest: list,
                  dry_run: bool = False) -> dict:
    """The dry-run prevents gets necessary metadata from SLCs and orbits.

    Can be used to run workflow without redownloading data (except DEM).

    region_of_interest is in xmin, ymin, xmax, ymax format (epsg: 4326)
    """
    out_slc = download_slcs(reference_scenes,
                            secondary_scenes,
                            region_of_interest=region_of_interest,
                            dry_run=dry_run)

    out_orbits = download_orbits(reference_scenes,
                                 secondary_scenes,
                                 dry_run=dry_run)

    out_dem = {}
    out_aux_cal = {}
    if not dry_run:
        out_dem = download_dem_for_isce2(out_slc['extent'])
        out_aux_cal = download_aux_cal()

    out = {'reference_scenes': reference_scenes,
           'secondary_scenes': secondary_scenes,
           **out_slc,
           **out_dem,
           **out_aux_cal,
           **out_orbits}
    return out


def ensure_earthdata_credentials(username: Optional[str] = None, password: Optional[str] = None,
                                 host: str = 'urs.earthdata.nasa.gov'):
    """Ensures Earthdata credentials are provided in ~/.netrc

     Earthdata username and password may be provided by, in order of preference, one of:
        * `netrc_file`
        * `username` and `password`
        * `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` environment variables
     and will be written to the ~/.netrc file if it doesn't already exist.
     """
    if username is None:
        username = os.getenv('EARTHDATA_USERNAME')

    if password is None:
        password = os.getenv('EARTHDATA_PASSWORD')

    netrc_file = Path.home() / '.netrc'
    if not netrc_file.exists() and username and password:
        netrc_file.write_text(f'machine {host} login {username} password {password}')
        netrc_file.chmod(0o000600)

    try:
        dot_netrc = netrc.netrc(netrc_file)
        username, _, password = dot_netrc.authenticators(host)
    except (FileNotFoundError, netrc.NetrcParseError, TypeError):
        raise ValueError(
            f'Please provide valid Earthdata login credentials via {netrc_file}, '
            f'username and password options, or '
            f'the EARTHDATA_USERNAME and EARTHDATA_PASSWORD environment variables.'
        )


def gunw_slc():
    parser = ArgumentParser()
    parser.add_argument('--username')
    parser.add_argument('--password')
    parser.add_argument('--bucket')
    parser.add_argument('--bucket-prefix', default='')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--reference-scenes', type=str.split, nargs='+', required=True)
    parser.add_argument('--secondary-scenes', type=str.split, nargs='+', required=True)
    parser.add_argument('--region-of-interest', type=float, nargs=4, default=None,
                        help='xmin ymin xmax ymax in epgs:4326', required=False)
    parser.add_argument('--estimate-ionosphere-delay', type=bool, default=False)
    parser.add_argument('--frame-id', type=int, default=-1)
    parser.add_argument('--do-esd', type=bool, default=False)
    parser.add_argument('--esd-coherence-threshold', type=float, default=-1)
    args = parser.parse_args()

    do_esd_arg = (args.esd_coherence_threshold != -1) == args.do_esd
    if not do_esd_arg:
        raise ValueError('If ESD is turned on, specify esd_coherence_threshold between 0 and 1; '
                         'Otherwise, do not or set the threshold to -1')

    ensure_earthdata_credentials(args.username, args.password)

    args.reference_scenes = [item for sublist in args.reference_scenes for item in sublist]
    args.secondary_scenes = [item for sublist in args.secondary_scenes for item in sublist]

    # Region of interest becomes 'extent' in loc_data
    loc_data = localize_data(args.reference_scenes,
                             args.secondary_scenes,
                             dry_run=args.dry_run,
                             region_of_interest=args.region_of_interest)
    # TODO: either remove this or ensure it is passed to CMR metadata
    loc_data['frame_id'] = args.frame_id
    if args.frame_id >= 0:
        if not args.region_of_interest:
            raise RuntimeError('If you specify frame_id, then must specify region_of_interest')

    # Allows for easier re-inspection of processing, packaging, and delivery
    # after job completes
    json.dump(loc_data,
              open('loc_data.json', 'w'),
              indent=2,
              cls=MetadataEncoder)

    topsapp_processing(reference_slc_zips=loc_data['ref_paths'],
                       secondary_slc_zips=loc_data['sec_paths'],
                       orbit_directory=loc_data['orbit_directory'],
                       # Region of interest is passed to topsapp via 'extent' key in loc_data
                       extent=loc_data['extent'],
                       estimate_ionosphere_delay=args.estimate_ionosphere_delay,
                       do_esd=args.do_esd,
                       esd_coherence_threshold=args.esd_coherence_threshold,
                       dem_for_proc=loc_data['full_res_dem_path'],
                       dem_for_geoc=loc_data['low_res_dem_path'],
                       dry_run=args.dry_run,
                       )

    ref_properties = loc_data['reference_properties']
    sec_properties = loc_data['secondary_properties']
    extent = loc_data['extent']

    additional_2d_layers = []
    if args.estimate_ionosphere_delay:
        additional_2d_layers.append('ionosphere')

    additional_2d_layers = additional_2d_layers or None
    nc_path = package_gunw_product(isce_data_directory=Path.cwd(),
                                   reference_properties=ref_properties,
                                   secondary_properties=sec_properties,
                                   extent=extent,
                                   additional_2d_layers=additional_2d_layers
                                   )

    # Move final product to current working directory
    final_directory = prepare_for_delivery(nc_path, loc_data)

    if args.bucket:
        for file in final_directory.glob('S1-GUNW*'):
            aws.upload_file_to_s3(file, args.bucket, args.bucket_prefix)


def gunw_burst():
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('--username')
    parser.add_argument('--password')
    parser.add_argument('--bucket')
    parser.add_argument('--bucket-prefix', default='')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--reference-scene', type=str, required=True)
    parser.add_argument('--secondary-scene', type=str, required=True)
    parser.add_argument('--image-number', type=int, required=True)
    parser.add_argument('--burst-number', type=int, required=True)
    parser.add_argument('--azimuth-looks', type=int, default=2)
    parser.add_argument('--range-looks', type=int, default=10)
    parser.add_argument('--estimate-ionosphere-delay', type=bool, default=False)
    args = parser.parse_args()

    ensure_earthdata_credentials(args.username, args.password)

    ref_obj, sec_obj = get_asf_slc_objects([args.reference_scene, args.secondary_scene])

    ref_params = BurstParams(
        safe_url=ref_obj.properties['url'],
        image_number=args.image_number,
        burst_number=args.burst_number,
    )
    sec_params = BurstParams(
        safe_url=sec_obj.properties['url'],
        image_number=args.image_number,
        burst_number=args.burst_number,
    )

    ref_burst, sec_burst = download_bursts([ref_params, sec_params])

    intersection = ref_burst.footprint.intersection(sec_burst.footprint).bounds
    is_ascending = ref_burst.orbit_direction == 'ascending'
    roi = get_region_of_interest(ref_burst.footprint, sec_burst.footprint, is_ascending=is_ascending)

    orbits = download_orbits([ref_burst.safe_name[:-5]], [sec_burst.safe_name[:-5]], dry_run=args.dry_run)

    if not args.dry_run:
        # TODO this is likely not the optimal geometry to pass to this function
        dem = download_dem_for_isce2(intersection)
        _ = download_aux_cal()

    # TODO fails when using the default 19x7 looks
    topsapp_processing(
        reference_slc_zips=ref_burst.safe_name,
        secondary_slc_zips=sec_burst.safe_name,
        orbit_directory=orbits['orbit_directory'],
        extent=roi,
        dem_for_proc=dem['full_res_dem_path'],
        dem_for_geoc=dem['low_res_dem_path'],
        estimate_ionosphere_delay=args.estimate_ionosphere_delay,
        azimuth_looks=args.azimuth_looks,
        range_looks=args.range_looks,
        swaths=[ref_burst.swath],
        dry_run=args.dry_run,
    )

    if args.bucket:
        for file in Path('merged').glob('*geo*'):
            aws.upload_file_to_s3(file, args.bucket, args.bucket_prefix)


def main():
    parser = ArgumentParser(prefix_chars='+', formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '++process', choices=['gunw_slc', 'gunw_burst'], default='gunw_slc',
        help='Select the HyP3 entrypoint to use'
    )
    args, unknowns = parser.parse_known_args()

    sys.argv = [args.process, *unknowns]
    # FIXME: this gets better in python 3.10
    # (process_entry_point,) = entry_points(group='console_scripts', name=args.process)
    process_entry_point = [ep for ep in entry_points()['console_scripts'] if ep.name == args.process][0]
    sys.exit(
        process_entry_point.load()()
    )


if __name__ == '__main__':
    main()
