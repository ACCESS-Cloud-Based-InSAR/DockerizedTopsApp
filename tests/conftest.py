from pathlib import Path

import pytest

test_dir = Path(__file__).parents[0].resolve()


@pytest.fixture(scope='session')
def test_dir_path() -> Path:
    return test_dir


@pytest.fixture(scope='session')
def orbit_files_for_set() -> dict:
    orbit_paths = {'reference': (test_dir / 'set_test_data' /
                                 'S1B_OPER_AUX_POEORB_OPOD_20210812T111941_V20210722T225942_20210724T005942.EOF'),
                   'secondary': (test_dir / 'set_test_data' /
                                 'S1B_OPER_AUX_POEORB_OPOD_20210731T111940_V20210710T225942_20210712T005942.EOF')
                   }
    return orbit_paths


@pytest.fixture(scope='session')
def gunw_path_for_set() -> Path:
    return test_dir / 'set_test_data' / 'S1-GUNW-A-R-064-tops-20210723_20210711-015000-00119W_00033N-PP-6267-v2_0_6.nc'


@pytest.fixture(scope='session')
def gunw_path_for_set_2() -> Path:
    return test_dir / 'set_test_data' / 'S1-GUNW-A-R-064-tops-20220113_20220101-015048-00119W_00034N-PP-3b1f-v2_0_5.nc'


@pytest.fixture(scope='session')
def orbit_files_for_set_2() -> dict:
    orbit_paths = {'reference': (test_dir / 'set_test_data' /
                                 'S1A_OPER_AUX_POEORB_OPOD_20220202T081558_V20220112T225942_20220114T005942.EOF'),
                   'secondary': (test_dir / 'set_test_data' /
                                 'S1A_OPER_AUX_POEORB_OPOD_20220121T121549_V20211231T225942_20220102T005942.EOF')
                   }
    return orbit_paths
