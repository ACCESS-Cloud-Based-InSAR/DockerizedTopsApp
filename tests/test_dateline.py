from shapely.geometry import box

from isce2_topsapp.dateline import unwrap_geometry


def test_wrapping():
    bbox_unwrapped = box(-181, 51, -179, 53)
    bbox_wrapped = box(-179, 51, 179, 53)

    out_bbox_unwrapped = unwrap_geometry(bbox_wrapped)

    # Set equality is demonstrated by double containment
    bbox_unwrapped.contains(out_bbox_unwrapped)
    out_bbox_unwrapped.contains(bbox_unwrapped)
