import json
from pathlib import Path

from isce2_topsapp.packaging import DATASET_VERSION, get_gunw_id, read_baselines

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
