from pathlib import Path

import pytest
from isce2_topsapp import (
    download_aux_cal,
    download_dem_for_isce2,
    download_orbits,
    download_slcs,
)
from isce2_topsapp.packaging import get_gunw_id


REFERENCE_SCENES = ['S1B_IW_SLC__1SDV_20210723T014947_20210723T015014_027915_0354B4_B3A9']
SECONDARY_SCENES = [
    'S1B_IW_SLC__1SDV_20210711T014922_20210711T014949_027740_034F80_859D',
    'S1B_IW_SLC__1SDV_20210711T014947_20210711T015013_027740_034F80_D404',
    'S1B_IW_SLC__1SDV_20210711T015011_20210711T015038_027740_034F80_376C',
]


def test_localize_slcs_and_orbits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    out_slc = download_slcs(REFERENCE_SCENES, SECONDARY_SCENES, dry_run=True)
    out_orbit = download_orbits(REFERENCE_SCENES, SECONDARY_SCENES)
    out = {**out_slc, **out_orbit}

    orbits = out['reference_orbits'] + out['secondary_orbits']
    assert orbits
    assert all(Path(orbit).exists() for orbit in orbits)

    gunw_id = get_gunw_id(
        reference_properties=out['reference_properties'],
        secondary_properties=out['secondary_properties'],
        extent=out['extent'],
    )
    assert gunw_id.startswith('S1-GUNW-A-R-064-tops-20210723_20210711-')


def test_localize_dem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    # A sub-degree extent without buffer keeps this smoke test to a single DEM tile
    out_dem = download_dem_for_isce2([-118.6, 34.1, -118.4, 34.3], buffer=0.0)

    assert out_dem['full_res_dem_path'].exists()
    assert out_dem['low_res_dem_path'].exists()
    assert Path(f'{out_dem["full_res_dem_path"]}.xml').exists()
    assert Path(f'{out_dem["low_res_dem_path"]}.xml').exists()


def test_localize_aux_cal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    out_aux_cal = download_aux_cal()

    assert list(Path(out_aux_cal['aux_cal_dir']).glob('S1*_AUX_CAL_*.SAFE'))
