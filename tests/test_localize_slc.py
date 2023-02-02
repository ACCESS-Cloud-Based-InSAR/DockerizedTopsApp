import pytest

from isce2_topsapp.localize_slc import download_slcs

reference_list = [['S1A_IW_SLC__1SDV_20230130T140853_20230130T140921_047014_05A3AA_C991'],  # different tracks
                  ['S1B_IW_SLC__1SDV_20210723T014947_20210723T015014_027915_0354B4_B3A9'],  # disconnected secondary
                  ]

secondary_list = [['S1A_IW_SLC__1SDV_20221004T135226_20221004T135254_045293_056A34_1026'],
                  ['S1B_IW_SLC__1SDV_20210711T014922_20210711T014949_027740_034F80_859D',
                   'S1B_IW_SLC__1SDV_20210711T015011_20210711T015038_027740_034F80_376C']
                  ]

frame_id_list = [-1, -1]


@pytest.mark.parametrize("reference_ids, secondary_ids, frame_id", zip(reference_list, secondary_list, frame_id_list))
def test_localize_slc_with_bad_pairs(reference_ids, secondary_ids, frame_id):
    with pytest.raises(RuntimeError):
        download_slcs(reference_ids, secondary_ids, frame_id=frame_id, dry_run=True)
