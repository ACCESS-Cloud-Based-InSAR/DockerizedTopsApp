import json
import shutil
from pathlib import Path

import pytest
from isce2_topsapp.solid_earth_tides import update_gunw_with_solid_earth_tide
from shapely.geometry import shape


test_dir = Path(__file__).parents[0].resolve()


@pytest.fixture(scope='session')
def test_dir_path() -> Path:
    return test_dir


@pytest.fixture(scope='session')
def orbit_files_for_set() -> list[dict]:
    """Is aligned with gunw_paths_for_set."""
    orbit_paths_0 = {
        'reference': (
            test_dir / 'set_test_data' / 'S1B_OPER_AUX_POEORB_OPOD_20210812T111941_V20210722T225942_20210724T005942.EOF'
        ),
        'secondary': (
            test_dir / 'set_test_data' / 'S1B_OPER_AUX_POEORB_OPOD_20210731T111940_V20210710T225942_20210712T005942.EOF'
        ),
    }
    orbit_paths_1 = {
        'reference': (
            test_dir / 'set_test_data' / 'S1A_OPER_AUX_POEORB_OPOD_20220202T081558_V20220112T225942_20220114T005942.EOF'
        ),
        'secondary': (
            test_dir / 'set_test_data' / 'S1A_OPER_AUX_POEORB_OPOD_20220121T121549_V20211231T225942_20220102T005942.EOF'
        ),
    }
    return [orbit_paths_0, orbit_paths_1]


@pytest.fixture(scope='session')
def gunw_paths_for_set() -> list[Path]:
    """Is alignd with orbit_files_for_set."""
    p1 = test_dir / 'set_test_data' / 'S1-GUNW-A-R-064-tops-20210723_20210711-015000-00119W_00033N-PP-6267-v2_0_6.nc'
    p2 = test_dir / 'set_test_data' / 'S1-GUNW-A-R-064-tops-20220113_20220101-015048-00119W_00034N-PP-3b1f-v2_0_5.nc'
    data = [p1, p2]
    return data


@pytest.fixture(scope='session')
def gunw_paths_with_set(
    tmp_path_factory: pytest.TempPathFactory,
    gunw_paths_for_set: list[Path],
    orbit_files_for_set: list[dict],
) -> list[Path]:
    """Return copies of gunw_paths_for_set updated with reference and secondary solid earth tides.

    Session scoped because the tide computation dominates the runtime of the test suite and every
    consumer only reads the result.
    """
    out_dir = tmp_path_factory.mktemp('gunws_with_set')

    def update(index: int, gunw_path: Path, orbit_dict: dict) -> Path:
        out_path = out_dir / f'{index}.nc'
        shutil.copy(gunw_path, out_path)
        [
            update_gunw_with_solid_earth_tide(out_path, acq_type, [orbit_dict[acq_type]])
            for acq_type in ['reference', 'secondary']
        ]
        return out_path

    return [
        update(index, gunw_path, orbit_dict)
        for index, (gunw_path, orbit_dict) in enumerate(zip(gunw_paths_for_set, orbit_files_for_set))
    ]


@pytest.fixture(scope='session')
def sample_gunw_path(gunw_paths_for_set: list[Path]) -> Path:
    """GUNW whose reference scene is the one described by sample_loc_metadata.json."""
    return gunw_paths_for_set[0]


@pytest.fixture()
def sample_loc_metadata() -> dict:
    """Localization metadata as `isce2_topsapp.localize_*` would hand it to the packaging routines."""
    metadata = json.loads((test_dir / 'sample_loc_metadata.json').read_text())
    metadata.update({key: Path(metadata[key]) for key in ['orbit_directory', 'full_res_dem_path', 'low_res_dem_path']})
    metadata.update({key: [Path(orbit) for orbit in metadata[key]] for key in ['reference_orbits', 'secondary_orbits']})
    metadata['gunw_geo'] = shape(metadata['gunw_geo'])
    return metadata


@pytest.fixture(scope='session')
def get_overlapping_orbits_for_set_test() -> list[Path]:
    p1 = test_dir / 'set_test_data' / 'S1A_OPER_AUX_POEORB_OPOD_20230705T080713_V20230614T225942_20230616T005942.EOF'
    p2 = test_dir / 'set_test_data' / 'S1A_OPER_AUX_POEORB_OPOD_20230706T080750_V20230615T225942_20230617T005942.EOF'
    data = [p1, p2]
    return data


@pytest.fixture(scope='session')
def tops_proc_xml_path() -> Path:
    """Is alignd with orbit_files_for_set."""
    return test_dir / 'test_data' / 'topsProc.xml'
