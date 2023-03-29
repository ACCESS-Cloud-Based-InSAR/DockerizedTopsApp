import os
import site

import subprocess
from pathlib import Path
from typing import Union

import numpy as np
from jinja2 import Template
from tqdm import tqdm

from numpy.typing import NDArray
from isce.components import isceobj
from isce.components.isceobj.TopsProc.runMergeBursts import (
    interpolateDifferentNumberOfLooks,
)

from osgeo import gdal

# List of parameters for ionospheric correction:
# https://github.com/isce-framework/isce2/blob/8af43d2b9f291e2370e9112a3ead1449d0f2a386/examples/input_files/topsApp.xml#L182

IONO_STEPS = ["subband", "rawion", "grd2ion", "filt_gaussian"]

TEMPLATE_DIR = Path(__file__).parent / "templates"

GEOCODE_LIST_BASE = ["merged/topophase.ion"]


def iono_processing(
    *,
    reference_slc_zips: list,
    secondary_slc_zips: list,
    orbit_directory: str,
    extent: list,
    dem_for_proc: str,
    dem_for_geoc: str,
    azimuth_looks: int = 7,
    range_looks: int = 19,
    swaths: list = None,
    do_esd: bool = False,
    esd_coherence_threshold: float = 0.7,
    mask_filename: str = None,
):
    swaths = swaths or [1, 2, 3]
    # for [ymin, ymax, xmin, xmax]
    extent_isce = [extent[k] for k in [1, 3, 0, 2]]

    # Update PATH with ISCE2 applications
    isce_app_path = Path(f"{site.getsitepackages()[0]}" "/isce/applications/")
    os.environ["PATH"] += ":" + str(isce_app_path)

    # Define topsApp input xml parameters
    ion_kwargs = {
        "orbit_directory": orbit_directory,
        "output_reference_directory": "reference",
        "output_secondary_directory": "secondary",
        "ref_zip_file": reference_slc_zips,
        "sec_zip_file": secondary_slc_zips,
        "region_of_interest": extent_isce,
        "demFilename": dem_for_proc,
        "geocodeDemFilename": dem_for_geoc,
        "filter_strength": 0.5,
        "do_unwrap": True,
        "use_virtual_files": True,
        "do_esd": do_esd,
        "esd_coherence_threshold": esd_coherence_threshold,
        # IONO PARAMETERS
        "estimate_ionosphere_delay": True,
        "ion_burstProperties": False,
        "ion_polyFit": True,
        "ion_correctAzimuthshift": 1,
        "azimuth_looks": azimuth_looks,
        "range_looks": range_looks,
        "swaths": swaths,
        "geocode_list": GEOCODE_LIST_BASE,
    }

    with open(TEMPLATE_DIR / "topsapp_iono_template.xml", "r") as file:
        template = Template(file.read())

    # Step-1 Run ionospheric correction step subband
    iono_xml = template.render(
        **ion_kwargs, ion_startStep=IONO_STEPS[0], ion_stopStep=IONO_STEPS[0]
    )

    with open("ionoApp.xml", "w") as file:
        file.write(iono_xml)

    tops_app_cmd = f"{isce_app_path}/topsApp.py"

    step_cmd = f"{tops_app_cmd} ionoApp.xml --dostep=ion"
    result = subprocess.run(step_cmd, shell=True)
    if result.returncode != 0:
        raise ValueError("TopsApp failed at step: ion-subband")

    # Step-2 Mask upper and lower band burst wrapped interferograms
    # path to burst ifgs:
    # ion/lower|upper/fine_interferogram/IW{1,2,3}/burst_{##}.int
    # path to burst geometry: geom_reference/IW{1,2,3}/lat|lon_{##}.rdr

    if mask_filename:
        # Project mask to burst image coordinate space
        workdir = Path(".").absolute()

        def get_swath(x):
            return x.split("/")[-2]

        def get_burst(x):
            return x.split("/")[-1].split("_")[-1].split(".")[0]

        # Get all geometry files
        geom_files = list(workdir.glob("geom_reference/IW*/lat*.rdr"))

        # NOTE: THis can be easily parallized, skipped for now
        with tqdm(total=len(geom_files)) as pbar:
            for lat in geom_files:
                pbar.set_description(
                    f"Geo2radar mask {get_swath(str(lat))}\
                                        /{get_burst(str(lat))}"
                )

                lon = str(lat).replace("lat", "lon")
                # Get the swath and burst number
                swath = get_swath(str(lat))
                burst = get_burst(str(lat))
                # Get output dir and file
                output_dir = workdir / f"mask/{swath}"
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"msk_{burst}.rdr"
                # Projct mask to radar coordinate space
                mask_geo2radar(mask_filename, str(lat), lon, str(output_file))
                pbar.update()

        # Get lower and upper band full-resolution interferograms
        iono_location = "ion/{band}/fine_interferogram/IW*/burst*.int"
        lower_band_ifgs = workdir.glob(iono_location.format(band="lower"))
        upper_band_ifgs = workdir.glob(iono_location.format(band="upper"))

        # Lower band interferograms
        with tqdm(total=len(lower_band_ifgs + upper_band_ifgs)) as pbar:
            for ifg in lower_band_ifgs + upper_band_ifgs:
                band = str(ifg).split("/")[-4]
                pbar.set_description(
                    f"Masking {band}-iono interferograms \
                                     {get_swath(str(ifg))}\
                                     /{get_burst(str(ifg))}"
                )

                # Get the swath and burst number
                swath = get_swath(str(ifg))
                burst = get_burst(str(ifg))
                # Get mask
                mask_file = workdir / f"mask/{swath}/msk_{burst}.rdr.vrt"
                mask_ds = gdal.Open(str(mask_file), gdal.GA_ReadOnly)
                # Mask
                mask_interferogram(str(ifg), mask_ds.ReadAsArray())
                mask_ds = None  # close
                pbar.update()

    # Step-3 Compute ionospheric correction
    iono_xml = template.render(
        **ion_kwargs, ion_startStep=IONO_STEPS[1], ion_stopStep=IONO_STEPS[-1]
    )

    with open("ionoApp.xml", "w") as file:
        file.write(iono_xml)

    step_cmd = f"{tops_app_cmd} ionoApp.xml --dostep=ion"
    result = subprocess.run(step_cmd, shell=True)
    if result.returncode != 0:
        raise ValueError("TopsApp failed at step: ion-rawion2esd")

    # Step-4 mergeBursts
    # Create merged/topophase.ion file
    merge_bursts(range_looks=range_looks, azimuth_looks=azimuth_looks)

    # Step-5 Geocode ionospheric correction outputs
    step_cmd = f"{tops_app_cmd} ionoApp.xml --dostep=geocode"
    result = subprocess.run(step_cmd, shell=True)
    if result.returncode != 0:
        raise ValueError("TopsApp failed at step: geocode (ion)")


def merge_bursts(
    range_looks: int = 19,
    azimuth_looks: int = 7,
    ion_rangeLooks: int = 200,
    ion_azimuthLooks: int = 50,
    mergedir: Union[str, Path] = "./merged",
) -> None:
    """
    Reference:
      https://github.com/isce-framework/isce2/blob/8af43d2b9f291e2370e9112a3ead1449d0f2a386/components/isceobj/TopsProc/runMergeBursts.py#L851

    """
    mergedIfgname = "topophase.flat"
    mergedIonname = "topophase.ion"
    #########################################

    ionFilt = "ion/ion_cal/filt.ion"
    img = isceobj.createImage()
    img.load(ionFilt + ".xml")
    ionFiltImage = (
        np.fromfile(ionFilt, dtype=np.float32).reshape(img.length * 2, img.width)
    )[1 : img.length * 2 : 2, :]
    img = isceobj.createImage()
    img.load(os.path.join(mergedir, mergedIfgname + ".xml"))

    # interpolate original
    ionFiltImageOut = interpolateDifferentNumberOfLooks(
        ionFiltImage,
        img.length,
        img.width,
        range_looks,
        azimuth_looks,
        ion_rangeLooks,
        ion_azimuthLooks,
    )
    ionFiltOut = os.path.join(mergedir, mergedIonname)
    ionFiltImageOut.astype(np.float32).tofile(ionFiltOut)

    image = isceobj.createImage()
    image.setDataType("FLOAT")
    image.setFilename(ionFiltOut)
    image.extraFilename = ionFiltOut + ".vrt"
    image.setWidth(img.width)
    image.setLength(img.length)
    image.renderHdr()


# UTILITIES FOR MASKING
def mask_geo2radar(
    maskFilename: Union[str, Path],
    latFilename: Union[str, Path],
    lonFilename: Union[str, Path],
    outputFilename: Union[str, Path],
    saveFlag: bool = True,
) -> NDArray:
    """
    This routine translates mask raster
    from geographical to radar(image) coordinate space

    maskFilename : str
            path to georeferenced mask raster (must have vrt extension)
    latFilename : str
            path to radar lat.rdr file
            (bursts: geom_reference/IW{1,2,3}/lat_burst.rdr
                     merged: merged/lat.rdr.full.vrt)
    lonFilename : str
            path to radar lon.rdr file
            (bursts: geom_reference/IW{1,2,3}/lon_burst.rdr
                     merged: merged/lon.rdr.full.vrt)
    outputFilename : str
            path to save mask output file
    saveFlag : bool
            flag to locally save mask in radar coordinates
    """

    # Open mask file
    mask_ds = gdal.Open(maskFilename + ".vrt")
    # Open lon and lat file
    lon_ds = gdal.Open(lonFilename + ".vrt")
    lat_ds = gdal.Open(latFilename + ".vrt")

    # Get lon and lat arrays
    lons = lon_ds.ReadAsArray()
    lats = lat_ds.ReadAsArray()

    # Translate mask geo corrdinate to radar
    lineIdx = np.int32(
        (lats - mask_ds.GetGeoTransform()[3]) / mask_ds.GetGeoTransform()[5] + 0.5
    )
    sampleIdx = np.int32(
        (lons - mask_ds.GetGeoTransform()[0]) / mask_ds.GetGeoTransform()[1] + 0.5
    )
    inboundIndex = np.logical_and(
        np.logical_and(lineIdx >= 0, lineIdx <= mask_ds.RasterYSize - 1),
        np.logical_and(sampleIdx >= 0, sampleIdx <= mask_ds.RasterXSize - 1),
    )
    # Convert
    mask_radarcoord = np.empty(lats.shape)
    mask_radarcoord[inboundIndex] = mask_ds.ReadAsArray()[
        lineIdx[inboundIndex], sampleIdx[inboundIndex]
    ]
    # close gdal instances
    mask_ds = None
    lon_ds = None
    lat_ds = None

    # Save
    if saveFlag:
        mask_radarcoord.astype(np.int8).tofile(outputFilename)
        image = isceobj.createImage()
        image.setDataType("BYTE")
        image.setFilename(outputFilename)
        image.extraFilename = outputFilename + ".vrt"
        image.setWidth(mask_radarcoord.shape[1])
        image.setLength(mask_radarcoord.shape[0])
        image.renderHdr()

    return mask_radarcoord


def mask_interferogram(
    ifgFilename: Union[str, Path],
    maskArray: NDArray,
    outFilename: Union[str, Path] = None,
) -> None:
    """
    This routine uses mask np.array to mask wrapped interferogram
    ifgFilename : str
            path to georeferenced mask raster (must have vrt extension)
    maskArray : np.array
            mask 2d array  in rdr coordinates
            (1: mask values, 0; no-mask values))
    outFilename : str
            path where to save masked interferogram
            (default: None = overwrite existing)
    """

    # Read interferogram
    int_ds = gdal.Open(ifgFilename + ".vrt")
    int_array = int_ds.ReadAsArray()

    # Mask interferogram
    int_array.imag[np.bool_(maskArray)] = 0
    int_array.real[np.bool_(maskArray)] = 0

    # Write masked interferogram
    if outFilename:
        driver = gdal.GetDriverByName("ISCE")
        outdata = driver.CreateCopy(ifgFilename + "_msk", int_ds)
        outdata.GetRasterBand(1).WriteArray(int_array)
        outdata.FlushCache()  # saves to disk!!
        outdata = None

        # create isce aux files
        image = isceobj.createIntImage()
        image.setDataType("cfloat")
        image.setFilename(outFilename + "_msk")
        image.extraFilename = outFilename + "_msk" + ".vrt"
        image.setWidth(int_ds.RasterXSize)
        image.setLength(int_ds.RasterYSize)
        image.setAccessMode("READ")
        image.renderHdr()
        int_ds = None
    else:
        # Overwrite existing interferogram
        int_ds = None
        int_array.astype(np.complex64).tofile(ifgFilename)
