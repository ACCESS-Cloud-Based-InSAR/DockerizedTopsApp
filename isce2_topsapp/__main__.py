import click
import json
from isce2_topsapp import (download_slcs,
                           download_orbits,
                           download_dem_for_isce2,
                           download_aux_cal,
                           topsapp_processing)


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

    out = {**out_slc,
           **out_dem,
           **out_aux_cal,
           **out_orbit}
    return out


@click.command()
@click.argument('input_dataset', required=True, type=str, nargs=1)
@click.option('--dry-run',
              'dry_run',
              is_flag=True,
              default=False)
def main(input_dataset: str, dry_run: bool):
    data = json.load(open(input_dataset, 'r'))

    reference_scenes = data['reference_scenes']
    secondary_scenes = data['secondary_scenes']

    loc_data = localize_data(reference_scenes,
                             secondary_scenes,
                             dry_run=dry_run)

    topsapp_processing(reference_slc_zips=loc_data['ref_paths'],
                       secondary_slc_zips=loc_data['sec_paths'],
                       reference_orbit_path=loc_data['ref_orbit'],
                       secondary_orbit_path=loc_data['sec_orbit'],
                       extent=loc_data['extent'],
                       dem_for_proc=loc_data['full_res_dem_path'],
                       dem_for_geoc=loc_data['low_res_dem_path'],
                       dry_run=dry_run
                       )


if __name__ == '__main__':
    main()
