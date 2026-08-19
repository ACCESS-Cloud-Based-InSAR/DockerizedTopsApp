import json
import shutil
from pathlib import Path

import h5py
import jsonschema
import numpy as np
import pytest
import rasterio
from affine import Affine
from isce2_topsapp.delivery_prep import get_dataset_schema, prepare_for_delivery
from isce2_topsapp.packaging import update_gunw_internal_version_attribute
from isce2_topsapp.packaging_utils.additional_layers import add_2d_layer
from isce2_topsapp.water_mask import get_water_mask_raster_for_browse_image
from rasterio import default_gtiff_profile
from rasterio.crs import CRS
from rasterio.windows import Window, transform


DELIVERED_METADATA_NAME = 'S1-GUNW-A-R-064-tops-20210723_20210711-015001-35393N_33512N-PP-6267-v2_0_4.json'


def write_ionosphere_placeholder(merged_dir: Path) -> Path:
    """`additional_layers.json` expects the ionosphere layer at `merged/ionosphere_for_gunw.geo`."""
    merged_dir.mkdir(exist_ok=True)

    profile = default_gtiff_profile.copy()
    profile.update(
        driver='ISCE',
        crs=CRS.from_epsg(4326),
        transform=Affine(1, 0, -1, 0, 1, -1),
        width=12,
        height=12,
        count=1,
    )

    geo_path = merged_dir / 'ionosphere_for_gunw.geo'
    with rasterio.open(geo_path, 'w', **profile) as ds:
        ds.write(np.ones((12, 12)), 1)
    return geo_path


def test_delivered_metadata_matches_schema(test_dir_path: Path) -> None:
    metadata = json.loads((test_dir_path / 'test_data' / DELIVERED_METADATA_NAME).read_text())

    assert jsonschema.validate(instance=metadata, schema=get_dataset_schema()) is None


def test_water_mask_for_browse_image(sample_gunw_path: Path) -> None:
    with rasterio.open(f'netcdf:{sample_gunw_path}:/science/grids/data/connectedComponents') as ds:
        profile = ds.profile

    # The south west corner of this GUNW is over the Pacific; a small window keeps this to one tile
    window = Window(0, profile['height'] - 512, 512, 512)
    profile.update(width=512, height=512, transform=transform(window, profile['transform']))

    mask = get_water_mask_raster_for_browse_image(profile)

    assert mask.shape == (512, 512)
    assert mask.dtype == bool


def test_prepare_for_delivery(
    sample_gunw_path: Path,
    sample_loc_metadata: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    nc_path = Path(sample_gunw_path.name)
    shutil.copy(sample_gunw_path, nc_path)

    write_ionosphere_placeholder(Path('merged'))
    add_2d_layer('ionosphere', nc_path)

    out_dir = prepare_for_delivery(nc_path, sample_loc_metadata, 'GUNW')

    gunw_id = out_dir.name
    assert sorted(p.name for p in out_dir.glob('*')) == [f'{gunw_id}.json', f'{gunw_id}.nc', f'{gunw_id}.png']

    update_gunw_internal_version_attribute(out_dir / f'{gunw_id}.nc', new_version='1c')
    with h5py.File(out_dir / f'{gunw_id}.nc') as file:
        assert file.attrs['version'] == '1c'

    metadata = json.loads((out_dir / f'{gunw_id}.json').read_text())
    assert jsonschema.validate(instance=metadata, schema=get_dataset_schema()) is None
