from pathlib import Path

import pytest

test_dir = Path(__file__).parents[0].resolve()


@pytest.fixture(scope='session')
def test_dir_path() -> Path:
    return test_dir


@pytest.fixture(scope='session')
def isce_data_dir_for_set() -> Path:
    return test_dir / 'set_test_data'


@pytest.fixture(scope='session')
def gunw_path_for_set() -> Path:
    return test_dir / 'set_test_data' / 'S1-GUNW-A-R-064-tops-20210723_20210711-015000-00119W_00033N-PP-6267-v2_0_6.nc'
