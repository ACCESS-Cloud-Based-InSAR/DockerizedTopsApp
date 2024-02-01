import json
from pathlib import Path

import numpy as np
import rasterio
from numpy.testing import assert_almost_equal

from isce2_topsapp.packaging import (
    DATASET_VERSION,
    get_geocoded_layer_means,
    get_gunw_id,
    read_baselines,
)

test_dir = Path(__file__).parent


def test_gunw_id_generation_crossing_dateline():
    sample_json_path = test_dir / "midnight_crossing_metadata.json"
    metadata = json.load(open(sample_json_path))
    gunw_id = get_gunw_id(
        metadata["reference_properties"],
        metadata["secondary_properties"],
        metadata["extent"],
    )
    version_str = DATASET_VERSION.replace(".", "_")
    assert (
        gunw_id
        == f"S1-GUNW-D-R-048-tops-20230106_20221214-235959-00090E_00040N-PP-c254-v{version_str}"
    )


def test_extract_baselines(tops_proc_xml_path):
    baseline_dict = read_baselines(tops_proc_xml_path)

    expected_output = {
        "parallel_baselines": [
            69.3390287211759,
            69.2260273326017,
            80.19268495122755,
            80.10734013261386,
            88.90972511062476,
            88.87192713792777,
        ],
        "perpendicular_baselines": [
            -136.44791837773963,
            -136.90239009351285,
            -130.29490212547398,
            -130.8679894611411,
            -124.43579341000144,
            -125.01252133117457,
        ],
    }

    assert baseline_dict == expected_output


def test_mean_of_geocoded_isce_outputs():
    """This uses the data in the public bucket to demonstrate and verify that the layer means are correct"""
    out = get_geocoded_layer_means(
        merged_dir="https://gunw-development-testing.s3.us-west-2.amazonaws.com/sample_merged_data"
    )
    expected_out = {
        "mean_filtered_coherence_without_water_mask": 0.4395995,
        "mean_filtered_coherence_with_water_mask": 0.4649538,
        "mean_unfiltered_coherence_without_water_mask": 0.33125195,
        "mean_unfiltered_coherence_with_water_mask": 0.33531728,
        "mean_incidence_angle": 38.845047,
        "mean_azimuth_angle": -169.84756469726562,
    }

    for key in expected_out:
        assert_almost_equal(expected_out[key], out[key], decimal=5)

    # Use output GUNW and compare means
    gunw_s3_path = (
        "/vsis3/gunw-development-testing/sample_merged_data"
        "/S1-GUNW-A-R-164-tops-20220212_20220131-222829-00071W_00047N-PP-3d6c-v3_0_0.nc"
    )

    vars_data_0 = {var: f"//science/grids/data/{var}" for var in ["unfilteredCoherence", "coherence"]}
    vars_data_1 = {var: f"//science/grids/imagingGeometry/{var}" for var in ["azimuthAngle", "incidenceAngle"]}
    vars_data = {**vars_data_0, **vars_data_1}

    gunw_mean_data = {}
    for var, var_path in vars_data.items():
        with rasterio.open(f"HDF5:{gunw_s3_path}:{var_path}") as ds:
            X = ds.read()
            # 0 is the nodata for all the variables we consider
            gunw_mean_data[var] = np.mean(X[X != 0])

    # Ensure the GUNW cubes and rasters (with lower resolution than geocoded ISCE2 data) are within a reasonable range
    # of the geocoded rasters that ICE2 produces
    assert np.abs(out['mean_filtered_coherence_without_water_mask'] - gunw_mean_data['coherence']) < .01
    assert np.abs(out['mean_unfiltered_coherence_without_water_mask'] - gunw_mean_data['unfilteredCoherence']) < .01
    assert np.abs(out['mean_azimuth_angle'] - gunw_mean_data['azimuthAngle']) < 1
    assert np.abs(out['mean_incidence_angle'] - gunw_mean_data['incidenceAngle']) < 1

    # Sanity checks - make sure that applying a water mask *increases* the coherence as water has low coherence
    assert out['mean_filtered_coherence_without_water_mask'] < out['mean_filtered_coherence_with_water_mask']
    assert out['mean_unfiltered_coherence_without_water_mask'] < out['mean_unfiltered_coherence_with_water_mask']
