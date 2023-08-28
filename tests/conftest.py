from pathlib import Path

import pytest

test_dir = Path(__file__).parents[0].resolve()


@pytest.fixture(scope='session')
def test_dir_path() -> Path:
    return test_dir


@pytest.fixture(scope='session')
def orbit_files_for_set() -> list[dict]:
    """Is aligned with gunw_paths_for_set"""
    orbit_paths_0 = {'reference': (test_dir / 'set_test_data' /
                                   'S1B_OPER_AUX_POEORB_OPOD_20210812T111941_V20210722T225942_20210724T005942.EOF'),
                     'secondary': (test_dir / 'set_test_data' /
                                   'S1B_OPER_AUX_POEORB_OPOD_20210731T111940_V20210710T225942_20210712T005942.EOF')
                     }
    orbit_paths_1 = {'reference': (test_dir / 'set_test_data' /
                                   'S1A_OPER_AUX_POEORB_OPOD_20220202T081558_V20220112T225942_20220114T005942.EOF'),
                     'secondary': (test_dir / 'set_test_data' /
                                   'S1A_OPER_AUX_POEORB_OPOD_20220121T121549_V20211231T225942_20220102T005942.EOF')
                     }
    return [orbit_paths_0, orbit_paths_1]


@pytest.fixture(scope='session')
def gunw_paths_for_set() -> list[Path]:
    """Is alignd with orbit_files_for_set"""
    p1 = test_dir / 'set_test_data' / 'S1-GUNW-A-R-064-tops-20210723_20210711-015000-00119W_00033N-PP-6267-v2_0_6.nc'
    p2 = test_dir / 'set_test_data' / 'S1-GUNW-A-R-064-tops-20220113_20220101-015048-00119W_00034N-PP-3b1f-v2_0_5.nc'
    data = [p1, p2]
    return data


@pytest.fixture(scope='session')
def get_overlapping_orbits_for_set_test() -> list[Path]:
    p1 = test_dir / 'set_test_data' / 'S1A_OPER_AUX_POEORB_OPOD_20230705T080713_V20230614T225942_20230616T005942.EOF'
    p2 = test_dir / 'set_test_data' / 'S1A_OPER_AUX_POEORB_OPOD_20230706T080750_V20230615T225942_20230617T005942.EOF'
    data = [p1, p2]
    return data
