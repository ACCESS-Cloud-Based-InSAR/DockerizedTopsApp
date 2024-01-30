import json
from pathlib import Path

from numpy.testing import assert_almost_equal

from isce2_topsapp.packaging import (
    DATASET_VERSION,
    get_gunw_id,
    get_geocoded_layer_means,
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
        "mean_filtered_coherence_without_water_mask": 0.3126283,
        "mean_filtered_coherence_with_water_mask": 0.32342613,
        "mean_incidence_angle": 28.281992,
        "mean_azimuth_angle": -99.18769836425781,
    }

    for key in expected_out:
        assert_almost_equal(expected_out[key], out[key], decimal=5)
