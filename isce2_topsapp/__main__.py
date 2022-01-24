import json
import netrc
from argparse import ArgumentParser
from pathlib import Path

from isce2_topsapp import (aws, download_aux_cal, download_dem_for_isce2,
                           download_orbits, download_slcs,
                           package_gunw_product, prepare_for_delivery,
                           topsapp_processing)

from .json_encoder import MetadataEncoder


def localize_data(reference_scenes: list,
                  secondary_scenes: list,
                  dry_run: bool = False) -> dict:
    """
    The dry-run prevents gets necessary metadata from SLCs and orbits.

    Can be used to run workflow without redownloading data (except DEM).
    """
    out_slc = download_slcs(reference_scenes,
                            secondary_scenes,
                            dry_run=dry_run)
    out_orbit = download_orbits(reference_scenes,
                                secondary_scenes,
                                dry_run=dry_run)
    out_dem = download_dem_for_isce2(out_slc['extent'])
    out_aux_cal = download_aux_cal()

    out = {'reference_scenes': reference_scenes,
           'secondary_scenes': secondary_scenes,
           **out_slc,
           **out_dem,
           **out_aux_cal,
           **out_orbit}
    return out


def main():
    parser = ArgumentParser()
    parser.add_argument('--username', default='')
    parser.add_argument('--password', default='')
    parser.add_argument('--bucket')
    parser.add_argument('--bucket-prefix', default='')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--reference-scenes', type=str.split, nargs='+', required=True)
    parser.add_argument('--secondary-scenes', type=str.split, nargs='+', required=True)
    args = parser.parse_args()

    args.reference_scenes = [item for sublist in args.reference_scenes for item in sublist]
    args.secondary_scenes = [item for sublist in args.secondary_scenes for item in sublist]

    dot_netrc = Path.home() / '.netrc'
    if args.username and (not dot_netrc.exists()):
        dot_netrc.write_text(f'machine urs.earthdata.nasa.gov '
                             f'login {args.username} password '
                             f'{args.password}\n')
        dot_netrc.chmod(0o000600)
    else:  # either arg.username is not supplied or dot_netrc exists
        netrc_ob = netrc.netrc()
        earthdata_url = 'urs.earthdata.nasa.gov'
        if earthdata_url not in netrc_ob.hosts.keys():
            raise ValueError('Not updating your existing `~/.netrc`. '
                             'Your `~/.netrc` needs Earthdata credentials')

    loc_data = localize_data(args.reference_scenes,
                             args.secondary_scenes,
                             dry_run=args.dry_run)

    # Allows for easier re-inspection of processing, packaging, and delivery
    # after job completes
    json.dump(loc_data,
              open('loc_data.json', 'w'),
              indent=2,
              cls=MetadataEncoder)

    topsapp_processing(reference_slc_zips=loc_data['ref_paths'],
                       secondary_slc_zips=loc_data['sec_paths'],
                       reference_orbit_path=loc_data['ref_orbit'],
                       secondary_orbit_path=loc_data['sec_orbit'],
                       extent=loc_data['extent'],
                       dem_for_proc=loc_data['full_res_dem_path'],
                       dem_for_geoc=loc_data['low_res_dem_path'],
                       dry_run=args.dry_run
                       )

    ref_properties = loc_data['reference_properties']
    sec_properties = loc_data['secondary_properties']
    extent = loc_data['extent']

    nc_path = package_gunw_product(isce_data_directory=Path.cwd(),
                                   reference_properties=ref_properties,
                                   secondary_properties=sec_properties,
                                   extent=extent
                                   )

    # Move final product to current working directory
    final_directory = prepare_for_delivery(nc_path, loc_data)

    if args.bucket:
        for file in final_directory.glob('S1-GUNW*'):
            aws.upload_file_to_s3(file, args.bucket, args.bucket_prefix)


if __name__ == '__main__':
    main()
