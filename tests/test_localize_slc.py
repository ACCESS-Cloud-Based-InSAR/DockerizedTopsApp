import warnings

import pytest

from isce2_topsapp.localize_slc import (check_date_order,
                                        check_flight_direction,
                                        check_track_numbers, download_slcs,
                                        get_asf_slc_objects,
                                        get_intersection_geo)


def test_intersection_geometry():
    # Disconnected Tracks
    ref_ids = ['S1A_IW_SLC__1SDV_20230130T140853_20230130T140921_047014_05A3AA_C991']
    sec_ids = ['S1A_IW_SLC__1SDV_20221004T135226_20221004T135254_045293_056A34_1026']

    ref_ob = get_asf_slc_objects(ref_ids)
    sec_ob = get_asf_slc_objects(sec_ids)

    with pytest.raises(ValueError):
        get_intersection_geo(ref_ob, sec_ob)

    # Disconnected Secondary
    ref_ids = ['S1B_IW_SLC__1SDV_20210723T014947_20210723T015014_027915_0354B4_B3A9']
    sec_ids = ['S1B_IW_SLC__1SDV_20210711T014922_20210711T014949_027740_034F80_859D',
               'S1B_IW_SLC__1SDV_20210711T015011_20210711T015038_027740_034F80_376C']

    ref_ob = get_asf_slc_objects(ref_ids)
    sec_ob = get_asf_slc_objects(sec_ids)

    with pytest.raises(ValueError):
        get_intersection_geo(ref_ob, sec_ob)


def test_bad_flight_direction():
    # Overlapping areas, same day, Ascending/Descending
    ref_ids = ['S1A_IW_SLC__1SDV_20221121T015133_20221121T015200_045986_0580C5_EBF0']
    sec_ids = ['S1A_IW_SLC__1SDV_20221121T135136_20221121T135203_045993_058110_0FB0']

    ref_obs = get_asf_slc_objects(ref_ids)
    sec_obs = get_asf_slc_objects(sec_ids)

    ref_props = [ob.properties for ob in ref_obs]
    sec_props = [ob.properties for ob in sec_obs]

    assert not check_flight_direction(ref_props + sec_props)


def test_sequential_tracks():
    # Tracks 86 and 87
    slc_ids = ['S1A_IW_SLC__1SDV_20220830T153309_20220830T153343_044784_055914_7B42',
               'S1A_IW_SLC__1SDV_20220830T153244_20220830T153311_044783_055914_19AE']
    slc_obs = get_asf_slc_objects(slc_ids)
    props = [ob.properties for ob in slc_obs]

    assert check_track_numbers(props)


def test_bad_tracks_with_same_flight_direction():
    slc_ids = ['S1A_IW_SLC__1SDV_20220830T153244_20220830T153311_044783_055914_19AE',
               'S1A_IW_SLC__1SDV_20220823T154053_20220823T154119_044681_05559C_4B0E']
    slc_obs = get_asf_slc_objects(slc_ids)
    props = [ob.properties for ob in slc_obs]

    assert not check_track_numbers(props)


def test_warnings_over_water():

    # Intersection over water
    ref_ids = ['S1B_IW_SLC__1SDV_20211210T153506_20211210T153533_029965_0393C6_D840']
    sec_ids = ['S1A_IW_SLC__1SDV_20211122T153535_20211122T153602_040686_04D3DB_520A']

    with pytest.warns(RuntimeWarning):
        download_slcs(ref_ids, sec_ids, frame_id=-1, dry_run=True)

    # Tibet (no water)
    ref_ids = ['S1A_IW_SLC__1SDV_20170817T120001_20170817T120028_017963_01E230_A23A']
    sec_ids = ['S1A_IW_SLC__1SSV_20160717T115946_20160717T120014_012188_012E84_F684',
               'S1A_IW_SLC__1SSV_20160717T120012_20160717T120039_012188_012E84_4198']
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        download_slcs(ref_ids, sec_ids, frame_id=-1, dry_run=True)


def test_bad_date_order():
    ref_ids = ['S1A_IW_SLC__1SDV_20220422T141557_20220422T141624_042887_051EA4_CD2E']
    sec_ids = ['S1A_IW_SLC__1SDV_20220504T141557_20220504T141624_043062_05246D_3C67']

    ref_obs = get_asf_slc_objects(ref_ids)
    sec_obs = get_asf_slc_objects(sec_ids)

    ref_props = [ob.properties for ob in ref_obs]
    sec_props = [ob.properties for ob in sec_obs]

    assert not check_date_order(ref_props, sec_props)


def test_bad_frame_with_intersection():
    ref_ids = ['S1A_IW_SLC__1SDV_20230125T135954_20230125T140021_046941_05A132_D35C',
               'S1A_IW_SLC__1SDV_20230125T140019_20230125T140046_046941_05A132_82DF']
    sec_ids = ['S1A_IW_SLC__1SDV_20221220T135956_20221220T140023_046416_058F77_B248',
               'S1A_IW_SLC__1SDV_20221220T140020_20221220T140047_046416_058F77_5213']
    frame_id = 0

    ref_ob = get_asf_slc_objects(ref_ids)
    sec_ob = get_asf_slc_objects(sec_ids)

    with pytest.raises(ValueError):
        get_intersection_geo(ref_ob, sec_ob, frame_id=frame_id)


reference_list = [
                  # Tibet
                  ['S1A_IW_SLC__1SDV_20170817T120001_20170817T120028_017963_01E230_A23A'],
                  # California
                  ['S1A_IW_SLC__1SDV_20220504T141557_20220504T141624_043062_05246D_3C67'],
                  # Aleutian
                  ['S1A_IW_SLC__1SDV_20210925T172118_20210925T172137_039841_04B68A_7D82'],
                  # Frame Example
                  ['S1A_IW_SLC__1SDV_20230125T135954_20230125T140021_046941_05A132_D35C',
                   'S1A_IW_SLC__1SDV_20230125T140019_20230125T140046_046941_05A132_82DF'],
                  ]

secondary_list = [
                  # Tibet
                  ['S1A_IW_SLC__1SSV_20160717T115946_20160717T120014_012188_012E84_F684',
                   'S1A_IW_SLC__1SSV_20160717T120012_20160717T120039_012188_012E84_4198'],
                  # California
                  ['S1A_IW_SLC__1SDV_20220422T141557_20220422T141624_042887_051EA4_CD2E'],
                  # Aleutian
                  ['S1A_IW_SLC__1SDV_20200930T172045_20200930T172114_034591_0406F4_8C2F',
                   'S1A_IW_SLC__1SDV_20200930T172112_20200930T172131_034591_0406F4_17D7'],
                  # Frame Example
                  ['S1A_IW_SLC__1SDV_20221220T135956_20221220T140023_046416_058F77_B248',
                   'S1A_IW_SLC__1SDV_20221220T140020_20221220T140047_046416_058F77_5213'],
                  ]

frame_id_list = [-1, -1, -1, 22438]


@pytest.mark.parametrize("reference_ids, secondary_ids, frame_id", zip(reference_list, secondary_list, frame_id_list))
def test_localize_slc_with_valid_pairs(reference_ids, secondary_ids, frame_id):
    assert download_slcs(reference_ids, secondary_ids, frame_id=frame_id, dry_run=True)
