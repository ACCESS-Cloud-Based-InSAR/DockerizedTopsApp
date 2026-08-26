import re
import warnings
from datetime import date, datetime, timedelta

import pytest
from isce2_topsapp.localize_slc import (
    S1D_MIN_DATE,
    check_date_order,
    check_flight_direction,
    check_if_s1d_has_valid_date,
    check_track_numbers,
    download_slcs,
    get_asf_slc_objects,
    get_interferogram_geo,
    get_slcs_for_date_and_frame,
)


def test_intersection_geometry() -> None:
    # Disconnected Tracks
    ref_ids = ['S1A_IW_SLC__1SDV_20230130T140853_20230130T140921_047014_05A3AA_C991']
    sec_ids = ['S1A_IW_SLC__1SDV_20221004T135226_20221004T135254_045293_056A34_1026']

    ref_ob = get_asf_slc_objects(ref_ids)
    sec_ob = get_asf_slc_objects(sec_ids)

    with pytest.raises(ValueError, match=r'The overlap between reference and secondary scenes is empty'):
        get_interferogram_geo(ref_ob, sec_ob)

    # Disconnected Secondary
    ref_ids = ['S1B_IW_SLC__1SDV_20210723T014947_20210723T015014_027915_0354B4_B3A9']
    sec_ids = [
        'S1B_IW_SLC__1SDV_20210711T014922_20210711T014949_027740_034F80_859D',
        'S1B_IW_SLC__1SDV_20210711T015011_20210711T015038_027740_034F80_376C',
    ]

    ref_ob = get_asf_slc_objects(ref_ids)
    sec_ob = get_asf_slc_objects(sec_ids)

    with pytest.raises(
        ValueError,
        match=r'Reference and/or secondary dates were not connected in their coverage',
    ):
        get_interferogram_geo(ref_ob, sec_ob)


def test_bad_flight_direction() -> None:
    # Overlapping areas, same day, Ascending/Descending
    ref_ids = ['S1A_IW_SLC__1SDV_20221121T015133_20221121T015200_045986_0580C5_EBF0']
    sec_ids = ['S1A_IW_SLC__1SDV_20221121T135136_20221121T135203_045993_058110_0FB0']

    ref_obs = get_asf_slc_objects(ref_ids)
    sec_obs = get_asf_slc_objects(sec_ids)

    ref_props = [ob.properties for ob in ref_obs]
    sec_props = [ob.properties for ob in sec_obs]

    assert not check_flight_direction(ref_props + sec_props)


def test_sequential_tracks() -> None:
    # Tracks 86 and 87
    slc_ids = [
        'S1A_IW_SLC__1SDV_20220830T153309_20220830T153343_044784_055914_7B42',
        'S1A_IW_SLC__1SDV_20220830T153244_20220830T153311_044783_055914_19AE',
    ]
    slc_obs = get_asf_slc_objects(slc_ids)
    props = [ob.properties for ob in slc_obs]

    assert check_track_numbers(props)


def test_bad_tracks_with_same_flight_direction() -> None:
    slc_ids = [
        'S1A_IW_SLC__1SDV_20220830T153244_20220830T153311_044783_055914_19AE',
        'S1A_IW_SLC__1SDV_20220823T154053_20220823T154119_044681_05559C_4B0E',
    ]
    slc_obs = get_asf_slc_objects(slc_ids)
    props = [ob.properties for ob in slc_obs]

    assert not check_track_numbers(props)


def test_warnings_over_water() -> None:
    wtr_msg = 'If there are not enough bursts over land - ISCE2 will fail.'

    # Intersection over water
    ref_ids = ['S1B_IW_SLC__1SDV_20211210T153506_20211210T153533_029965_0393C6_D840']
    sec_ids = ['S1A_IW_SLC__1SDV_20211122T153535_20211122T153602_040686_04D3DB_520A']

    with pytest.warns(RuntimeWarning) as warning_records:
        download_slcs(ref_ids, sec_ids, frame_id=-1, dry_run=True)
    assert any([wtr_msg in str(r.message) for r in warning_records])

    # Tibet (no water)
    ref_ids = ['S1A_IW_SLC__1SDV_20170817T120001_20170817T120028_017963_01E230_A23A']
    sec_ids = [
        'S1A_IW_SLC__1SSV_20160717T115946_20160717T120014_012188_012E84_F684',
        'S1A_IW_SLC__1SSV_20160717T120012_20160717T120039_012188_012E84_4198',
    ]

    # Make sure water warning is not thrown
    with warnings.catch_warnings(record=True) as warning_records:
        download_slcs(ref_ids, sec_ids, frame_id=-1, dry_run=True)
    if warning_records:
        assert all([wtr_msg not in str(r.message) for r in warning_records])


def test_bad_date_order() -> None:
    ref_ids = ['S1A_IW_SLC__1SDV_20220422T141557_20220422T141624_042887_051EA4_CD2E']
    sec_ids = ['S1A_IW_SLC__1SDV_20220504T141557_20220504T141624_043062_05246D_3C67']

    ref_obs = get_asf_slc_objects(ref_ids)
    sec_obs = get_asf_slc_objects(sec_ids)

    ref_props = [ob.properties for ob in ref_obs]
    sec_props = [ob.properties for ob in sec_obs]

    assert not check_date_order(ref_props, sec_props)


def test_min_frame_coverage() -> None:
    ref_ids = [
        'S1A_IW_SLC__1SDV_20220212T222803_20220212T222830_041886_04FCA3_2B3E',
        'S1A_IW_SLC__1SDV_20220212T222828_20220212T222855_041886_04FCA3_A3E2',
    ]
    sec_ids = [
        'S1A_IW_SLC__1SDV_20220131T222803_20220131T222830_041711_04F690_8F5F',
        'S1A_IW_SLC__1SDV_20220131T222828_20220131T222855_041711_04F690_28D7',
    ]
    frame_id = 25502

    ref_ob = get_asf_slc_objects(ref_ids)
    sec_ob = get_asf_slc_objects(sec_ids)

    get_interferogram_geo(ref_ob, sec_ob, frame_id=frame_id, min_frame_coverage=0.72)

    match = (
        r'IFG area (i.e. ref and sec overlap) covers only 72.08% of Frame area; '
        r'the requested minimum coverage was 73.00%.'
    )
    with pytest.raises(ValueError, match=re.escape(match)):
        get_interferogram_geo(ref_ob, sec_ob, frame_id=frame_id, min_frame_coverage=0.73)


def test_min_frame_coverage_default() -> None:
    ref_ids = [
        'S1A_IW_SLC__1SDV_20230125T135954_20230125T140021_046941_05A132_D35C',
        'S1A_IW_SLC__1SDV_20230125T140019_20230125T140046_046941_05A132_82DF',
    ]
    sec_ids = [
        'S1A_IW_SLC__1SDV_20221220T135956_20221220T140023_046416_058F77_B248',
        'S1A_IW_SLC__1SDV_20221220T140020_20221220T140047_046416_058F77_5213',
    ]
    frame_id = 0

    ref_ob = get_asf_slc_objects(ref_ids)
    sec_ob = get_asf_slc_objects(sec_ids)

    get_interferogram_geo(ref_ob, sec_ob, frame_id=frame_id, min_frame_coverage=0.0)

    match = (
        r'IFG area (i.e. ref and sec overlap) covers only 0.00% of Frame area; '
        r'the requested minimum coverage was 1.00%.'
    )
    with pytest.raises(ValueError, match=re.escape(match)):
        get_interferogram_geo(ref_ob, sec_ob, frame_id=frame_id)


reference_list = [
    # Tibet
    ['S1A_IW_SLC__1SDV_20170817T120001_20170817T120028_017963_01E230_A23A'],
    # California
    ['S1A_IW_SLC__1SDV_20220504T141557_20220504T141624_043062_05246D_3C67'],
    # Aleutian
    ['S1A_IW_SLC__1SDV_20210925T172118_20210925T172137_039841_04B68A_7D82'],
    # Frame Example
    [
        'S1A_IW_SLC__1SDV_20230125T135954_20230125T140021_046941_05A132_D35C',
        'S1A_IW_SLC__1SDV_20230125T140019_20230125T140046_046941_05A132_82DF',
    ],
]

secondary_list = [
    # Tibet
    [
        'S1A_IW_SLC__1SSV_20160717T115946_20160717T120014_012188_012E84_F684',
        'S1A_IW_SLC__1SSV_20160717T120012_20160717T120039_012188_012E84_4198',
    ],
    # California
    ['S1A_IW_SLC__1SDV_20220422T141557_20220422T141624_042887_051EA4_CD2E'],
    # Aleutian
    [
        'S1A_IW_SLC__1SDV_20200930T172045_20200930T172114_034591_0406F4_8C2F',
        'S1A_IW_SLC__1SDV_20200930T172112_20200930T172131_034591_0406F4_17D7',
    ],
    # Frame Example
    [
        'S1A_IW_SLC__1SDV_20221220T135956_20221220T140023_046416_058F77_B248',
        'S1A_IW_SLC__1SDV_20221220T140020_20221220T140047_046416_058F77_5213',
    ],
]

frame_id_list = [-1, -1, -1, 22438]


@pytest.mark.parametrize(
    'reference_ids, secondary_ids, frame_id',
    zip(reference_list, secondary_list, frame_id_list),
)
def test_localize_slc_with_valid_pairs(reference_ids: list[str], secondary_ids: list[str], frame_id: int) -> None:
    assert download_slcs(reference_ids, secondary_ids, frame_id=frame_id, dry_run=True)


def test_get_slcs_by_date_and_frame() -> None:
    with pytest.raises(ValueError, match=r'^No Sentinel-1A/1B/1C/1D SLCs found for date '):
        get_slcs_for_date_and_frame(date(2018, 2, 17), 16584)

    assert get_slcs_for_date_and_frame(date(2018, 2, 18), 16584) == [
        'S1A_IW_SLC__1SDV_20180218T003445_20180218T003512_020654_0235ED_81FB',
        'S1A_IW_SLC__1SDV_20180218T003420_20180218T003447_020654_0235ED_D95D',
    ]
    assert get_slcs_for_date_and_frame(date(2016, 1, 29), 1928) == [
        'S1A_IW_SLC__1SSV_20160129T142226_20160129T142252_009710_00E2CF_E92E',
        'S1A_IW_SLC__1SSV_20160129T142201_20160129T142228_009710_00E2CF_05D3',
    ]
    assert get_slcs_for_date_and_frame(date(2020, 12, 22), 17949) == [
        'S1B_IW_SLC__1SDV_20201222T152007_20201222T152034_024817_02F3D5_9C80',
        'S1B_IW_SLC__1SDV_20201222T151943_20201222T152010_024817_02F3D5_4D14',
        'S1B_IW_SLC__1SDV_20201222T151918_20201222T151945_024817_02F3D5_F283',
    ]

    # earlier scene crossing midnight
    assert get_slcs_for_date_and_frame(date(2021, 5, 15), 18829) == [
        'S1B_IW_SLC__1SDV_20210516T000016_20210516T000043_026922_033760_77C5',
        'S1B_IW_SLC__1SDV_20210515T235951_20210516T000019_026922_033760_F8C1',
    ]
    assert get_slcs_for_date_and_frame(date(2021, 5, 16), 18829) == [
        'S1B_IW_SLC__1SDV_20210516T000016_20210516T000043_026922_033760_77C5',
        'S1B_IW_SLC__1SDV_20210515T235951_20210516T000019_026922_033760_F8C1',
    ]

    # later scene crossing midnight
    assert get_slcs_for_date_and_frame(date(2025, 1, 4), 25672) == [
        'S1A_IW_SLC__1SDV_20250103T235934_20250104T000002_057287_070C52_215C',
        'S1A_IW_SLC__1SDV_20250103T235910_20250103T235937_057287_070C52_1291',
    ]
    assert get_slcs_for_date_and_frame(date(2025, 1, 3), 25672) == [
        'S1A_IW_SLC__1SDV_20250103T235934_20250104T000002_057287_070C52_215C',
        'S1A_IW_SLC__1SDV_20250103T235910_20250103T235937_057287_070C52_1291',
    ]

    # ascending crossing equator with multiple relative orbits
    assert get_slcs_for_date_and_frame(date(2022, 5, 14), 13403) == [
        'S1A_IW_SLC__1SDV_20220514T153240_20220514T153307_043209_052911_51B2',
        'S1A_IW_SLC__1SDV_20220514T153215_20220514T153242_043208_052911_BBAE',
    ]

    # scenes close to midnight but not crossing
    with pytest.raises(ValueError, match=r'^No Sentinel-1A/1B/1C/1D SLCs found for date '):
        get_slcs_for_date_and_frame(date(2025, 1, 4), 25671)
    assert get_slcs_for_date_and_frame(date(2025, 1, 3), 25671) == [
        'S1A_IW_SLC__1SDV_20250103T235910_20250103T235937_057287_070C52_1291',
        'S1A_IW_SLC__1SDV_20250103T235845_20250103T235912_057287_070C52_5599',
    ]


def test_s1c_min_date() -> None:
    # download_slcs(slc_ids_ref,slc_ids_sec, 18830)
    slc_ids_ref = [
        'S1C_IW_SLC__1SDV_20250519T000015_20250519T000042_002392_005070_1A43',
        'S1C_IW_SLC__1SDV_20250518T235950_20250519T000017_002392_005070_A436',
    ]
    # get_slcs_for_date_and_frame(date(2025, 5, 6), 18830)
    slc_ids_sec = [
        'S1C_IW_SLC__1SDV_20250507T000014_20250507T000041_002217_004B5D_AAF1',
        'S1C_IW_SLC__1SDV_20250506T235949_20250507T000016_002217_004B5D_9EC8',
    ]
    error_msg = 'The Sentinel-1C acquisitions provided were before 2025-05-19 00:00:00\\+00:00'
    with pytest.raises(ValueError, match=error_msg):
        download_slcs(slc_ids_ref, slc_ids_sec, 18830)

    # slc_ids_sec = get_slcs_for_date_and_frame(date(2025, 5, 30), 18830)
    slc_ids_sec = [
        'S1C_IW_SLC__1SDV_20250531T000017_20250531T000043_002567_00554C_4284',
        'S1C_IW_SLC__1SDV_20250530T235952_20250531T000019_002567_00554C_911F',
    ]
    # slc_ids_ref = get_slcs_for_date_and_frame(date(2025, 6, 11), 18830)
    slc_ids_ref = [
        'S1C_IW_SLC__1SDV_20250612T000017_20250612T000044_002742_005A5F_A997',
        'S1C_IW_SLC__1SDV_20250611T235952_20250612T000019_002742_005A5F_F563',
    ]
    download_slcs(slc_ids_ref, slc_ids_sec, 18830, dry_run=True)


def s1d_id_and_props(dt: datetime) -> tuple[list[str], list[dict]]:
    stamp = dt.strftime('%Y%m%dT%H%M%S')
    stop = (dt + timedelta(seconds=27)).strftime('%Y%m%dT%H%M%S')
    return (
        [f'S1D_IW_SLC__1SDV_{stamp}_{stop}_000050_000050_BBBB'],
        [{'startTime': dt.strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'}],
    )


def test_s1d_min_date() -> None:
    # Test check_if_s1d_has_valid_date directly since no real S1D SLCs
    # exist in ASF yet (download_slcs would fail at ASF search)
    slc_ids, slc_props = s1d_id_and_props(S1D_MIN_DATE - timedelta(days=1))
    assert not check_if_s1d_has_valid_date(slc_ids, slc_props)

    slc_ids, slc_props = s1d_id_and_props(S1D_MIN_DATE + timedelta(days=1))
    assert check_if_s1d_has_valid_date(slc_ids, slc_props)

    # Non-S1D data should always pass
    slc_ids = [
        'S1A_IW_SLC__1SDV_20200101T120000_20200101T120027_000001_000001_AAAA',
    ]
    slc_props = [{'startTime': '2020-01-01T12:00:00.000000Z'}]
    assert check_if_s1d_has_valid_date(slc_ids, slc_props)
