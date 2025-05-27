from datetime import date

from isce2_topsapp import enumeration


# TODO test helper functions

def test_get_slcs_by_date_and_frame():
    assert enumeration.get_slcs_for_date_and_frame(date(2018, 2, 18), 16584) == [
        'S1A_IW_SLC__1SDV_20180218T003445_20180218T003512_020654_0235ED_81FB',
        'S1A_IW_SLC__1SDV_20180218T003420_20180218T003447_020654_0235ED_D95D',
    ]
    assert enumeration.get_slcs_for_date_and_frame(date(2016, 1, 29), 1928) == [
        'S1A_IW_SLC__1SSV_20160129T142226_20160129T142252_009710_00E2CF_E92E',
        'S1A_IW_SLC__1SSV_20160129T142201_20160129T142228_009710_00E2CF_05D3',
    ]
    assert enumeration.get_slcs_for_date_and_frame(date(2020, 12, 22), 17949) == [
        'S1B_IW_SLC__1SDV_20201222T152007_20201222T152034_024817_02F3D5_9C80',
        'S1B_IW_SLC__1SDV_20201222T151943_20201222T152010_024817_02F3D5_4D14',
        'S1B_IW_SLC__1SDV_20201222T151918_20201222T151945_024817_02F3D5_F283',
    ]
    # TODO add test cases for single-pol, crossing midnight, no scenes found
