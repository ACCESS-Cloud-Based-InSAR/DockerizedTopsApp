from pathlib import Path

import numpy as np
from shapely.geometry import box
from isce.components.isceobj.Alos2Proc.runDownloadDem import download_wbd


def download_water_mask(
    extent: list, water_name: str = "SWDB", buffer: float = 0.1
) -> dict:
    output_dir = Path(".").absolute()

    extent_geo = box(*extent)
    extent_buffered = list(extent_geo.buffer(buffer).bounds)
    extent_buffered = [
        np.floor(extent_buffered[0]),
        np.floor(extent_buffered[1]),
        np.ceil(extent_buffered[2]),
        np.ceil(extent_buffered[3]),
    ]

    if water_name == "SWDB":
        # Download SRTM-SWDB water mask
        mask_filename = download_wbd(
            extent_buffered[1],
            extent_buffered[3],
            extent_buffered[0],
            extent_buffered[2],
        )

    elif water_name == "GSHHS":
        # from water_mask import get_water_mask_raster
        raise NotImplementedError("Your Message")

    return {"water_mask": str(output_dir / mask_filename)}
