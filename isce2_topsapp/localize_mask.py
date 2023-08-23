from pathlib import Path

import numpy as np
from isce.components.isceobj.Alos2Proc.runDownloadDem import download_wbd
from shapely.geometry import box


def download_water_mask(
    extent: list, water_name: str = "SWBD", buffer: float = 0.1
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

    if water_name == "SWBD":
        # Download SRTM-SWDB water mask
        # Water mask dataset extent
        # Latitude S55 - N60

        lats = [extent_buffered[1], extent_buffered[3]]
        if (np.abs(lats) < 59.9).all():
            mask_filename = download_wbd(
                extent_buffered[1],
                extent_buffered[3],
                extent_buffered[0],
                extent_buffered[2],
            )
            mask_filename = str(output_dir / mask_filename)
        else:
            print('Request out of SWBD coverage ',
                  'Skip downloading water mask!!')
            mask_filename = ''

    elif water_name == "GSHHS":
        # from water_mask import get_water_mask_raster
        raise NotImplementedError("TODO, GSHHS not yet available")

    return {"water_mask": mask_filename}
