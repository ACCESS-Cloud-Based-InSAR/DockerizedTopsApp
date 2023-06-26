# Author: Marin Govorcin
# Copyright 2023
# California Institute of Technology

import datetime
import os
import shutil
import site
from pathlib import Path
from typing import Type, Union

import numpy as np
import scipy.signal as ss
from isce.applications import topsApp
from isce.components import isceobj
from isce.components.isceobj.TopsProc import runIon
from isce.components.isceobj.TopsProc.runMergeBursts import (
    adjustValidWithLooks, interpolateDifferentNumberOfLooks,
    mergeBox, mergeBursts2, mergeBurstsVirtual, multilook)
from numpy.typing import NDArray
from osgeo import gdal
from skimage import morphology
from tqdm import tqdm

'''
Reference: Liang et al. (2019): Ionospheric Correction of InSAR Time Series
Analysis of C-band Sentinel-1 TOPS Data, doi:0.1109/TGRS.2019.2908494

List of parameters for ionospheric correction:
        isce2/examples/input_files/topsApp.xml#L182
'''

GEOCODE_LIST_ION = ["merged/topophase.ion"]


def iono_processing(
    *,
    topsapp_xml_filename: str = 'topsApp.xml',
    mask_filename: str = '',
    correct_burst_jumps: bool = True,
        ) -> None:

    '''
    NOTE: If water mask is not used, the code will return to its
        default processing with addition of using briding of unwrapped
        phase components, and modifed adaptive gaussian filtering.
        Outlier removal and masking using connected component 0 will
        be skipped
    '''

    # Update PATH with ISCE2 applications
    # Need for isce2/bin/imageMath.py in runIon.unwrap function
    isce_app_path = Path(f"{site.getsitepackages()[0]}" "/isce/applications/")
    os.environ["PATH"] += ":" + str(isce_app_path)

    # Use Connected component 0 to mask unwrapped interferogram
    # to improve masking after using water mask, e.g. remove noisy
    # pixels along the coastline
    conncomp_flag = True if mask_filename else False

    # Use outlier removal only is water mask exist
    # if False return to defualt topsProc iono processing
    outlier_removal = True if mask_filename else False

    # Outlier removal settings for gaussian filtering
    if outlier_removal:
        coh_threshold = 0.8
        sigma_rule = 1  # remove value above mean +- 1*std
    else:
        coh_threshold = 0.0
        sigma_rule = 0

    # Load input file
    topsapp = topsApp.TopsInSAR(name="topsApp", cmdline=[topsapp_xml_filename])
    topsapp.configure()

    # Load topsApp PICKLE object from previous topsApp step: fineresamp
    topsapp_dir = Path('.').resolve()
    topsapp.loadPickleObj(str(topsapp_dir / 'PICKLE/fineresamp'))

    # IONOSPHERE
    # Run iono setup
    ionParam = runIon.setup(topsapp)

    # Run iono step subband
    # Generate lower and upper band  fin interferograms
    runIon.subband(topsapp, ionParam)

    # Mask fine interferograms
    if mask_filename:
        # Project mask to burst image rdr coordinate space
        mask_iono_ifg_bursts(topsapp_dir, mask_filename)

    if ionParam.calIonWithMerged:
        # Run iono step rawion : merge
        runIon.merge(topsapp, ionParam)

        # Run iono step rawion : unwrap
        unwrap(topsapp, ionParam,
               use_bridging=True, use_conncomp=conncomp_flag)

        # Run iono step rawion : ionosphere
        ionosphere(topsapp, ionParam)
    else:
        # This mode is used for cross
        # Sentinel-1A/B interferogram
        # runIon.ionSwathBySwath(topsapp, ionParam)
        ionSwathBySwath(topsapp, ionParam,
                        use_bridging=True, conncomp_flag=conncomp_flag)

    # Run iono step grd2ion
    # Resample ionosphere from ground to iono layer
    # NOTE: this is not necessary as filtering is using
    #       not projected raw ionosphere (on the ground)
    # runIon.grd2ion(topsapp, ionParam)

    # Run iono step; filt_gaussian
    filt_gaussian(topsapp, ionParam,
                  coh_threshold=coh_threshold, sigma_rule=sigma_rule)

    # Step when using azimuth shift correction
    # between bursts, misregistration due to high iono content
    # based on long wavelength ionosphere delay estimation
    # NOTE: wrong long-wavelength iono estimates can effect this steps
    if correct_burst_jumps:
        # ionosphere shift
        runIon.ionosphere_shift(topsapp, ionParam)

        # resample from ionospheric layer to ground layer,
        # get ionosphere for each burst
        runIon.ion2grd(topsapp, ionParam)

        # esd
        runIon.esd(topsapp, ionParam)

        # Create merged/topophase.ion.az_shift file
        # using ion/ion_burst/ files
        merge_multilook_bursts(topsapp, input_dir='ion/ion_burst',
                               output_filename='topophase.ion.az_shift')

        GEOCODE_LIST_ION.extend('topophase.ion.az_shift')

        # Iono long wavelength
        merge_bursts(input_file="ion/ion_cal/filt.ion",
                     output_filename="topophase.ion")

    else:
        # Create merged/topophase.ion file
        merge_bursts(input_file="ion/ion_cal/filt.ion",
                     output_filename="topophase.ion")

    # Geocode ionospheric correction outputs
    topsapp.runGeocode(GEOCODE_LIST_ION, topsapp.do_unwrap,
                       topsapp.geocode_bbox)

    # Create attribute iono processing dict
    if correct_burst_jumps:
        steps = ionParam.allSteps
    else:
        steps = ionParam.allSteps[:-3]
    # as we skip grd2ion projection to ionospheric thin shell
    del steps[2]
    steps.append('geocode')

    # attributes dict items must be in the following
    # format: str, Number, ndarray, number, list, tuple
    iono_dict = dict(
        processing_steps=steps,
        water_mask=str(mask_filename),
        mask_connected_component_zero=str(conncomp_flag),
        do_phase_bridging=str(True),
        estimate_burst_jumps=str(ionParam.considerBurstProperties),
        burst_jumps_description=('calculation of burst jumps'
                                 ' (scalloping effect) due'
                                 ' to misaligment in coregistration'
                                 ' caused be large ionosphere'
                                 ' content/delay, typically low or'
                                 ' high latitudes'),
        swath_mode=str(False) if ionParam.calIonWithMerged else str(True),
        swath_ramp_removal=str(np.bool_(ionParam.rampRemovel)),
        swath_mode_description=('raw_ion ionosphere calculation'
                                ' done per swath rather per scene'
                                ' to adjust for misaligment between'
                                ' swaths when doing processing on cross'
                                ' Sentinel 1A/B pair or when there'
                                ' is a different starting range between'
                                ' reference and secondary image'),
        multilook_az_rg1=[ionParam.numberAzimuthLooks,
                          ionParam.numberRangeLooks],
        multilook_az_rg2=[ionParam.numberAzimuthLooks0,
                          ionParam.numberRangeLooks0],
        iono_height=ionParam.ionHeight
        )

    return iono_dict


def mask_iono_ifg_bursts(tops_dir: Path,
                         mask_filename: Union[str, Path]) -> None:
    # Project mask to burst image coordinate space

    def get_swath(x):
        return x.split("/")[-2]

    def get_burst(x):
        return x.split("/")[-1].split("_")[-1].split(".")[0]

    # Get all geometry files
    geom_files = list(tops_dir.glob("geom_reference/IW*/lat*.rdr"))

    # NOTE: This can be easily parallized, skip for now
    with tqdm(total=len(geom_files)) as pbar:
        for lat in geom_files:
            pbar.set_description(
                f"Geo2radar mask {get_swath(str(lat))}"
                f" /{get_burst(str(lat))}"
            )

            lon = str(lat).replace("lat", "lon")
            # Get the swath and burst number
            swath = get_swath(str(lat))
            burst = get_burst(str(lat))
            # Get output dir and file
            output_dir = tops_dir / f"mask/{swath}"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"msk_{burst}.rdr"
            # Project mask to radar coordinate space
            raster_geo2radar(mask_filename, str(lat), lon, str(output_file))
            pbar.update()

    # Get lower and upper band full-resolution interferograms
    iono_location = "ion/{band}/fine_interferogram/IW*/burst*.int"
    lower_band_ifgs = list(tops_dir.glob(iono_location.format(band="lower")))
    upper_band_ifgs = list(tops_dir.glob(iono_location.format(band="upper")))

    # Lower band interferograms
    with tqdm(total=len(lower_band_ifgs + upper_band_ifgs)) as pbar:
        for ifg in lower_band_ifgs + upper_band_ifgs:
            band = str(ifg).split("/")[-4]
            pbar.set_description(
                f"Masking {band}-iono interferograms"
                f" {get_swath(str(ifg))}/{get_burst(str(ifg))}"
            )

            # Get the swath and burst number
            swath = get_swath(str(ifg))
            burst = get_burst(str(ifg))
            # Get mask
            mask_file = tops_dir / f"mask/{swath}/msk_{burst}.rdr.vrt"
            mask_ds = gdal.Open(str(mask_file), gdal.GA_ReadOnly)
            # Mask
            mask_interferogram(str(ifg), mask_ds.ReadAsArray())
            mask_ds = None  # close
            pbar.update()


def merge_bursts(
    input_file: str = "ion/ion_cal/filt.ion",
    output_filename: str = "topophase.ion",
    range_looks: int = 19,
    azimuth_looks: int = 7,
    ion_rangeLooks: int = 200,
    ion_azimuthLooks: int = 50,
    mergedir: Union[str, Path] = "./merged",
) -> None:
    """
    Reference:
    isce2/components/isceobj/TopsProc/runMergeBursts.py#L851

    NOTE: change interpolation method from 'cubic' to 'nearest' in
        interpolateDifferentNumberOfLooks for raw ionosphere merge.
        Cubic creates artifacts around the edges.

    """
    mergedIfgname = "topophase.flat"
    #########################################

    img = isceobj.createImage()
    img.load(input_file + ".xml")

    ionFiltImage = (
        np.fromfile(input_file, dtype=np.float32).reshape(
            img.length * 2, img.width)
    )[1: img.length * 2: 2, :]
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
    ionFiltOut = os.path.join(mergedir, output_filename)
    ionFiltImageOut.astype(np.float32).tofile(ionFiltOut)

    image = isceobj.createImage()
    image.setDataType("FLOAT")
    image.setFilename(ionFiltOut)
    image.extraFilename = ionFiltOut + ".vrt"
    image.setWidth(img.width)
    image.setLength(img.length)
    image.renderHdr()


def merge_multilook_bursts(self: Type[topsApp.TopsInSAR],
                           input_dir: str = 'ion/ion_burst',
                           output_filename: str = 'topophase.ion',
                           mergedir: Union[str, Path] = "./merged") -> None:
    """
    Reference:
    isce2/components/isceobj/TopsProc/runMergeBursts.py#L776
    """

    if (self.numberRangeLooks == 1) and (self.numberAzimuthLooks == 1):
        suffix = ''
    else:
        suffix = '.full'

    # Get frames (subswaths)
    frames = []
    burstIndex = []
    swathList = self._insar.getValidSwathList(self.swaths)
    for swath in swathList:
        minBurst, maxBurst = self._insar.commonReferenceBurstLimits(swath-1)
        if minBurst == maxBurst:
            print('Skipping processing of swath {0}'.format(swath))
            continue
        ifg = self._insar.loadProduct(os.path.join(
            self._insar.fineIfgDirname, 'IW{0}.xml'.format(swath)))
        frames.append(ifg)
        burstIndex.append([int(swath), minBurst, maxBurst])

    # Determine merged size
    box = mergeBox(frames)

    # Merge iono products
    mergeBursts2(frames,
                 os.path.join(input_dir, 'IW%d',  'burst_%02d.ion'),
                 burstIndex, box,
                 os.path.join(mergedir, output_filename+suffix),
                 virtual=True, validOnly=True)

    # Create merged/topophase.ion file
    multilook(os.path.join(mergedir, output_filename+suffix),
              outname=os.path.join(mergedir, output_filename),
              alks=self.numberAzimuthLooks,
              rlks=self.numberRangeLooks)


# UTILITIES FOR MASKING
def raster_geo2radar(
    rasterFilename: Union[str, Path],
    latFilename: Union[str, Path],
    lonFilename: Union[str, Path],
    outputFilename: Union[str, Path],
    saveFlag: bool = True,
) -> NDArray:
    """
    This routine translates raster
    from geographical to radar(image) coordinate space

    rasterFilename : str
            path to georeferenced raster (must have vrt extension)
    latFilename : str
            path to radar lat.rdr file
            bursts: geom_reference/IW{1,2,3}/lat_burst.rdr
                    merged: merged/lat.rdr.full.vrt
    lonFilename : str
            path to radar lon.rdr file
            bursts: geom_reference/IW{1,2,3}/lon_burst.rdr
                    merged: merged/lon.rdr.full.vrt
    outputFilename : str
            path to save output file
    saveFlag : bool
            flag to locally save output in radar coordinates
            if False, function returns rdr numpy array
    """

    # Open mask file
    mask_ds = gdal.Open(str(rasterFilename) + ".vrt")
    # Open lon and lat file
    lon_ds = gdal.Open(str(lonFilename) + ".vrt")
    lat_ds = gdal.Open(str(latFilename) + ".vrt")

    # Get lon and lat arrays
    lons = lon_ds.ReadAsArray()
    lats = lat_ds.ReadAsArray()

    # Translate raster from geographical to radar coordinate space
    lineIdx = np.array(
        (lats - mask_ds.GetGeoTransform()[3]) /
        mask_ds.GetGeoTransform()[5] + 0.5, dtype=np.int32)
    sampleIdx = np.array(
        (lons - mask_ds.GetGeoTransform()[0]) /
        mask_ds.GetGeoTransform()[1] + 0.5, dtype=np.int32)
    inboundIndex = np.logical_and(
        np.logical_and(lineIdx >= 0, lineIdx <= mask_ds.RasterYSize - 1),
        np.logical_and(sampleIdx >= 0, sampleIdx <= mask_ds.RasterXSize - 1),
    )
    # Convert
    mask_radarcoord = np.empty(lats.shape)
    mask_radarcoord[inboundIndex] = mask_ds.ReadAsArray()[
        lineIdx[inboundIndex], sampleIdx[inboundIndex]
    ]

    # Save in isce format
    if saveFlag:
        mask_radarcoord.astype(np.int8).tofile(outputFilename)
        image = isceobj.createImage()
        image.setDataType("BYTE")
        image.setFilename(outputFilename)
        image.extraFilename = str(outputFilename) + ".vrt"
        image.setWidth(mask_radarcoord.shape[1])
        image.setLength(mask_radarcoord.shape[0])
        image.renderHdr()

    # close gdal instances
    mask_ds = None
    lon_ds = None
    lat_ds = None

    return mask_radarcoord


def mask_interferogram(
    ifgFilename: Union[str, Path],
    maskArray: NDArray,
    outFilename: Union[str, Path] = '',
) -> None:
    """
    This routine uses mask np.array in rdr to mask wrapped interferogram
    ifgFilename : str
            path to georeferenced mask raster (must have vrt extension)
    maskArray : np.array
            mask 2d array  in rdr coordinates
            1: mask values, 0; no-mask values
    outFilename : str
            path where to save masked interferogram
            default: None = overwrite existing
    """

    # Read interferogram
    int_ds = gdal.Open(str(ifgFilename) + ".vrt")
    int_array = int_ds.ReadAsArray()

    if not np.array_equal(int_array.shape, maskArray.shape):
        raise ValueError('Mask array dimensions do not match'
                         ' the interferogram dimensions!'
                         f'mask: {maskArray.shape} vs'
                         f'ifg: {int_array.shape}')

    # Mask interferogram
    int_array.imag[np.bool_(maskArray)] = 0
    int_array.real[np.bool_(maskArray)] = 0

    # Write masked interferogram
    if outFilename:
        driver = gdal.GetDriverByName("ISCE")
        outdata = driver.CreateCopy(str(ifgFilename) + "_msk", int_ds)
        outdata.GetRasterBand(1).WriteArray(int_array)
        outdata.FlushCache()  # saves to disk!!
        outdata = None

        # create isce aux files
        image = isceobj.createIntImage()
        image.setDataType("cfloat")
        image.setFilename(str(outFilename) + "_msk")
        image.extraFilename = str(outFilename) + "_msk" + ".vrt"
        image.setWidth(int_ds.RasterXSize)
        image.setLength(int_ds.RasterYSize)
        image.setAccessMode("READ")
        image.renderHdr()
        int_ds = None
    else:
        # Overwrite existing interferogram
        int_ds = None
        int_array.astype(np.complex64).tofile(ifgFilename)


def deramp(data: NDArray,
           mask_in: NDArray = None,
           ramp_type: str = 'linear') -> NDArray:
    '''
    REF: https://github.com/insarlab/MintPy
                        /src/mintpy/objects/ramp.py#L23

    This function preforms deramping of unwrapped phase

    data : NDarray
        2D array data to be derampped
    mask_in : NDarray
        2D np.ndarray, mask of pixels used for ramp estimation
    ramp_type : str
        name of ramp to be estimated. "linear" or 'quadratic"

    '''

    dshape = data.shape
    length, width = dshape[-2:]

    # for 2d only
    data = data.reshape(-1, 1)
    dmean = np.array(data).flatten()

    if mask_in is None:
        mask_in = np.ones((length, width), dtype=np.float32)
    mask = (mask_in != 0).flatten()
    del mask_in

    # 2. ignore pixels with NaN and/or zero data value
    mask *= ~np.isnan(dmean)
    mask *= (dmean != 0.)
    del dmean

    # design matrix
    xx, yy = np.meshgrid(np.arange(0, width),
                         np.arange(0, length))
    xx = np.array(xx, dtype=np.float32).reshape(-1, 1)
    yy = np.array(yy, dtype=np.float32).reshape(-1, 1)
    ones = np.ones(xx.shape, dtype=np.float32)
    if ramp_type == 'linear':
        G = np.hstack((yy, xx, ones))
    elif ramp_type == 'quadratic':
        G = np.hstack((yy**2, xx**2, yy*xx, yy, xx, ones))
    else:
        raise ValueError(f'un-recognized ramp type: {ramp_type}')

    # estimate ramp
    X = np.dot(np.linalg.pinv(G[mask, :], rcond=1e-15), data[mask, :])
    ramp = np.dot(G, X)
    ramp = np.array(ramp, dtype=data.dtype)

    return ramp.reshape(dshape)


def brige_components(unwrapped_ifg: str,
                     connected_components: str) -> None:
    """
    This routine preforms "bridging' of unwrapped phase
    connected components. Each component is shifted with
    its median value

    unwrapped_ifg : str
            path to unwrapped interferogram
    connected_components : str
            path to connected components (labels)
    """
    print(f'Do bridging {unwrapped_ifg}')
    ifg = gdal.Open(unwrapped_ifg, gdal.GA_Update)
    ifg_conn = gdal.Open(connected_components)

    # Load the interferogram and the connected component labels
    interferogram = ifg.GetRasterBand(2).ReadAsArray()  # unw Phase
    labels = ifg_conn.GetRasterBand(1).ReadAsArray()

    # Loop over each connected component in the interferogram
    for i in range(1, np.max(labels)+1):

        # Create a binary mask for the current component
        mask = np.zeros_like(interferogram, dtype=bool)
        mask = (labels == i)

        # Apply a binary closing operation to the mask
        mask = morphology.binary_closing(mask)

        # Deramp the data, to remove any trend
        # before estimating median
        # NOTE: move this out of loop, first test it out
        ramp = deramp(data=interferogram, mask_in=mask,
                      ramp_type='linear')
        derampped_interferogram = interferogram - ramp

        # Calculate the median phase value for the current component
        median_phase = np.median(derampped_interferogram[mask])

        # Subtract the median phase from the current component
        # to remove any phase jumps
        interferogram[mask] -= median_phase

    # Write
    ifg.GetRasterBand(2).WriteArray(interferogram)
    ifg.FlushCache()
    ifg = None


# MODIFIED FUNCTIONS FROM ISCE2/TOPSPROC, TRIED TO KEEP THEM
# IN AN ORIGINAL FORM

def unwrap(self: Type[topsApp.TopsInSAR],
           ionParam: Type[runIon.dummy],
           use_bridging: bool = True,
           use_conncomp: bool = True) -> None:
    '''
    unwrap lower and upper band interferograms
    ref: isce2/components/isceobj/TopsProc/runIon.py#L915

    M.G. April 2023 : Added option to use connected component 0
        to mask out unreliable pixels in unwrapped interferograms
        Added option to use bridging between diconnected unwrapped
        phase components
    '''

    # Get number of looks for second multilooking
    nrange0 = ionParam.numberRangeLooks0
    nazimuth0 = ionParam.numberAzimuthLooks0

    # Set number of looks for range0 and azimuth 0
    # same as for range and azimuth to skip multilook unw at first
    ionParam.numberRangeLooks0 = ionParam.numberRangeLooks
    ionParam.numberAzimuthLooks0 = ionParam.numberAzimuthLooks

    # Run Snaphu unwrapping
    runIon.unwrap(self, ionParam)

    # Bridge and mask using connected components
    if use_bridging | use_conncomp:
        lower_unw_ifg = Path(ionParam.ionDirname, ionParam.lowerDirname,
                             ionParam.mergedDirname,
                             self._insar.unwrappedIntFilename)
        upper_unw_ifg = Path(ionParam.ionDirname, ionParam.upperDirname,
                             ionParam.mergedDirname,
                             self._insar.unwrappedIntFilename)

        for ion_ifg in [lower_unw_ifg, upper_unw_ifg]:
            # Shifted unwrapped componentes with their median value
            if use_bridging:
                brige_components(str(ion_ifg), str(ion_ifg) + '.conncomp')
            # Use connected component 0 to mask unwrapped interferograms
            if use_conncomp:
                runIon.maskUnwrap(str(ion_ifg), str(ion_ifg) + '.conncomp')

    # Multilook
    ionParam.numberRangeLooks0 = nrange0
    ionParam.numberAzimuthLooks0 = nazimuth0
    runIon.multilook_unw(self, ionParam, ionParam.mergedDirname)


def filt_gaussian(self: Type[topsApp.TopsInSAR],
                  ionParam: Type[runIon.dummy],
                  coh_threshold: float = 0.5,
                  sigma_rule: int = 2) -> None:
    '''
    This function filters image using gaussian filter

    REF: isce2/components/isceobj/TopsProc/runIon.py#L1906

    M.G. April 2023 : Added option to mask out pixel using coherence
    threshold  and sigma rule for outlier removal before gaussian
    filtering
    '''

    print('filtering ionosphere')
    # Using not projected ionosphere
    ionfile = Path(ionParam.ionDirname, ionParam.ioncalDirname,
                   ionParam.ionRawNoProj)
    corfile = Path(ionParam.ionDirname, ionParam.ioncalDirname,
                   ionParam.ionCorNoProj)

    outfile = Path(ionParam.ionDirname, ionParam.ioncalDirname,
                   ionParam.ionFilt)

    # Read files using gdal
    iono_ds = gdal.Open(str(ionfile))
    cor_ds = gdal.Open(str(corfile))

    ion = iono_ds.GetRasterBand(2).ReadAsArray()
    amp = iono_ds.GetRasterBand(1).ReadAsArray()
    # Coherence is also stored as 2 band float file
    cor = cor_ds.GetRasterBand(2).ReadAsArray()

    length = iono_ds.RasterYSize
    width = iono_ds.RasterXSize

    # NOTE from runIon: AFTER COHERENCE IS RESAMPLED
    #   AT grd2ion, THERE ARE SOME WIRED VALUES
    cor[np.nonzero(cor < 0)] = 0.0
    cor[np.nonzero(cor > 1)] = 0.0

    # Get surface fitted to iono correction, polynomial fitting
    # weight_fitting(iono_phase, coherence, width, length,
    #                num_range_looks-input, num_azimuth_looks-input
    #                num_range_looks-output, num_azimuth_looks-output
    #                polynomial_order, coherence_threshold)

    if ionParam.ionFit:
        ion_fit = runIon.weight_fitting(ion, cor, width, length,
                                        1, 1, 1, 1, 2, 0.85)
        ion -= ion_fit * (ion != 0)
    else:
        ion_fit = np.zeros(ion.shape)

    # MG. Remove pixels with low coherence
    #     NOTE output is more smoothed, as
    #     filtering is less affected with noisy pixels

    if coh_threshold != 0.0:
        ion[cor < coh_threshold] = 0

    # Remove outliers using std
    if sigma_rule != 0:
        mean = np.mean(np.ma.masked_equal(ion, 0))
        std = np.std(np.ma.masked_equal(ion, 0))

        ion[ion > mean + sigma_rule*std] = 0
        ion[ion < mean - sigma_rule*std] = 0

    # Run modifed adaptive filtering MG April 2023
    filt = adaptive_gaussian(ion, cor**14,
                             ionParam.ionFilteringWinsizeMax,
                             ionParam.ionFilteringWinsizeMin)

    # Add estimated surface if exists
    filt += ion_fit * (filt != 0)

    # Save
    ion = np.zeros((length*2, width), dtype=np.float32)
    ion[0:length*2:2, :] = amp
    ion[1:length*2:2, :] = filt
    ion.astype(np.float32).tofile(str(outfile))
    img = isceobj.createImage()
    img.load(str(ionfile) + '.xml')
    img.filename = str(outfile)
    img.extraFilename = str(outfile) + '.vrt'
    img.renderHdr()

    # Close gdal files
    iono_ds = None
    cor_ds = None


def adaptive_gaussian(ionos: NDArray, wgt: NDArray,
                      size_max: int = 200, size_min: int = 100) -> NDArray:
    '''
    This program performs Gaussian filtering with adaptive window size.

    REF: isce2/components/isceobj/TopsProc/runIon.py#L1846

    ionos: ionosphere
    wgt: weight
    size_max: maximum window size
    size_min: minimum window size

    MG. NOTE: masking out with zeros is messing with statistics std
        and mean, so it is important to mask zeros (aka nans)
        before calculation

    '''

    length = (ionos.shape)[0]
    width = (ionos.shape)[1]
    flag = (ionos != 0) * (wgt != 0)
    ionos *= flag
    wgt *= flag

    size_num = 100
    size = np.linspace(size_min, size_max, num=size_num, endpoint=True)
    std = np.zeros((length, width, size_num))
    flt = np.zeros((length, width, size_num))
    out = np.zeros((length, width, 1))

    # calculate filterd image and standard deviation
    # sigma of window size: size_max
    sigma = size_max / 2.0
    for i in range(size_num):
        size2 = np.int32(np.around(size[i]))
        if size2 % 2 == 0:
            size2 += 1
        if (i+1) % 10 == 0:
            print('min win: %4d, max win: %4d, current win: %4d' % (
                np.int32(np.around(size_min)),
                np.int32(np.around(size_max)),
                size2))

        g2d = runIon.gaussian(size2, sigma*size2/size_max, scale=1.0)
        scale = ss.fftconvolve(wgt, g2d, mode='same')
        flt[:, :, i] = ss.fftconvolve(
            ionos*wgt, g2d, mode='same') / (scale + (scale == 0))

        # variance of resulting filtered sample
        scale = scale**2
        var = ss.fftconvolve(wgt, g2d**2, mode='same') / (scale + (scale == 0))
        # in case there is a large area without data where scale is very small,
        # which leads to wired values in variance
        var[~flag] = 0  # MG mask the variance where there are 0s in input data
        var[np.nonzero(var < 0)] = 0
        std[:, :, i] = np.sqrt(var)

    std_mv = np.mean(std[np.nonzero(std != 0)], dtype=np.float64)
    diff_max = np.amax(np.absolute(std - std_mv)) + std_mv + 1
    std[np.nonzero(std == 0)] = diff_max

    # Find indexes with minimum values along the axis 2
    ixs = np.argmin(np.absolute(std - std_mv), axis=2)

    index = np.nonzero(np.ones((length, width))) + \
        (ixs.reshape(length*width), )

    out = flt[index]
    out = out.reshape((length, width))

    # MG: use mean value to replace masked value, zeros introduce
    # artifacts at the edges in the final output
    out[~flag] = np.mean(np.ma.masked_array(out, mask=~flag))

    # remove artifacts due to varying wgt
    size_smt = size_min
    if size_smt % 2 == 0:
        size_smt += 1
    g2d = runIon.gaussian(size_smt, size_smt/2.0, scale=1.0)
    scale = ss.fftconvolve((out != 0), g2d, mode='same')
    out2 = ss.fftconvolve(out, g2d, mode='same') / (scale + (scale == 0))

    return out2


def ionSwathBySwath(self: Type[topsApp.TopsInSAR],
                    ionParam: Type[runIon.dummy],
                    use_bridging: bool = True,
                    conncomp_flag: bool = True) -> None:
    '''
    This routine merge, unwrap and compute ionosphere swath by swath,
    and then adjust phase difference between adjacent swaths caused
    by relative range timing error between adjacent swaths.

    This routine includes the following steps in the merged-swath
    processing:

    merge(self, ionParam)
    unwrap(self, ionParam)
    ionosphere(self, ionParam)

    MG: did little clean up of the code, replaced step 2 & 3 with
        functions
    '''

    #########################################
    # SET PARAMETERS HERE
    numberRangeLooks = ionParam.numberRangeLooks
    numberAzimuthLooks = ionParam.numberAzimuthLooks
    numberRangeLooks0 = ionParam.numberRangeLooks0
    numberAzimuthLooks0 = ionParam.numberAzimuthLooks0
    mergedDirname = ionParam.mergedDirname  # MG
    ioncalDirname = ionParam.ioncalDirname  # MG

    # THESE SHOULD BE GOOD ENOUGH, NO NEED TO SET IN setup(self)
    corThresholdSwathAdj = 0.85

    #########################################

    print('computing ionosphere swath by swath')
    # if ionParam.calIonWithMerged == False:
    warningInfo = (f'{datetime.datetime.now()} calculating ionosphere'
                   f'swath by swath, there may be slight phase error'
                   f'between subswaths\n')
    with open(os.path.join(ionParam.ionDirname, ionParam.warning), 'a') as f:
        f.write(warningInfo)

    # get bursts
    numValidSwaths = 0
    swathList = self._insar.getValidSwathList(self.swaths)
    for swath in swathList:
        minBurst, maxBurst = self._insar.commonReferenceBurstLimits(swath-1)
        if minBurst == maxBurst:
            # print('Skipping processing of swath {0}'.format(swath))
            continue
        numValidSwaths += 1

    if numValidSwaths <= 1:
        raise Exception(
            'There are less than one subswaths, no need to use swath-by-swath'
            'method to compute ionosphere!')
    else:
        xmlDirname = os.path.join(
            ionParam.ionDirname, ionParam.lowerDirname, ionParam.fineIfgDirname
            )

        merge_kwargs = {'numberRangeLooks': ionParam.numberRangeLooks,
                        'numberAzimuthLooks': ionParam.numberAzimuthLooks}

        (box, burstValidBox,
         burstValidBox2, frames) = runIon.getMergeBox(self, xmlDirname,
                                                      **merge_kwargs)

    # compute ionosphere swath by swath
    corList = []
    ampList = []
    ionosList = []
    nswath = len(swathList)
    ii = -1
    for i in range(nswath):
        swath = swathList[i]
        # MG Change merged dir for each swath
        ionParam.mergedDirname = mergedDirname + '_IW{0}'.format(swath)
        ionParam.ioncalDirname = ioncalDirname + '_IW{0}'.format(swath)

        minBurst, maxBurst = self._insar.commonReferenceBurstLimits(swath-1)
        if minBurst == maxBurst:
            print('Skipping processing of swath {0}'.format(swath))
            continue
        else:
            ii += 1

        ########################################################
        # STEP 1. MERGE THE BURSTS OF A SWATH
        ########################################################

        dirs = [ionParam.lowerDirname, ionParam.upperDirname]
        for dirx in dirs:
            outputFilename = self._insar.mergedIfgname
            outputDirname = os.path.join(
                ionParam.ionDirname, dirx, ionParam.mergedDirname)
            os.makedirs(outputDirname, exist_ok=True)
            suffix = '.full'
            if (numberRangeLooks0 == 1) and (numberAzimuthLooks0 == 1):
                suffix = ''

            # merge
            burstPattern = 'burst_%02d.int'
            burstDirname = os.path.join(
                ionParam.ionDirname, dirx, ionParam.fineIfgDirname)

            ifg = self._insar.loadProduct(os.path.join(
                burstDirname, 'IW{0}.xml'.format(swath)))
            bst = [os.path.join(burstDirname, f'IW{swath}',
                                burstPattern % (x+1)) for x in range(minBurst,
                                                                     maxBurst)]

            # doing adjustment before use
            adjustment_rvalid = np.int32(np.around(numberRangeLooks/8.0))
            adjustValidWithLooks([ifg], box,
                                 numberAzimuthLooks, numberRangeLooks,
                                 edge=0, avalid='strict',
                                 rvalid=adjustment_rvalid)
            mergeBurstsVirtual([ifg], [bst], box, os.path.join(
                outputDirname, outputFilename+suffix))

            # take looks
            if suffix not in ['', None]:
                multilook(os.path.join(outputDirname, outputFilename+suffix),
                          os.path.join(outputDirname, outputFilename),
                          numberAzimuthLooks0,
                          numberRangeLooks0)
            else:
                print('skipping multilooking')

        # The orginal coherence calculated by topsApp.py is not good at all,
        # use the following coherence instead
        lowerintfile = os.path.join(ionParam.ionDirname,
                                    ionParam.lowerDirname,
                                    ionParam.mergedDirname,
                                    self._insar.mergedIfgname)
        upperintfile = os.path.join(ionParam.ionDirname,
                                    ionParam.upperDirname,
                                    ionParam.mergedDirname,
                                    self._insar.mergedIfgname)
        corfile = os.path.join(ionParam.ionDirname,
                               ionParam.lowerDirname,
                               ionParam.mergedDirname,
                               self._insar.correlationFilename)

        img = isceobj.createImage()
        img.load(lowerintfile + '.xml')
        width = img.width
        length = img.length
        lowerint = np.fromfile(
            lowerintfile, dtype=np.complex64).reshape(length, width)
        upperint = np.fromfile(
            upperintfile, dtype=np.complex64).reshape(length, width)

        ########################################################
        # slight filtering to improve the estimation accuarcy
        # of swath difference
        if 1 and shutil.which('psfilt1') is not None:
            cmd1 = 'mv {} tmp'.format(lowerintfile)
            cmd2 = 'psfilt1 tmp {} {} .3 32 8'.format(lowerintfile, width)
            cmd3 = 'rm tmp'
            cmd4 = 'mv {} tmp'.format(upperintfile)
            cmd5 = 'psfilt1 tmp {} {} .3 32 8'.format(upperintfile, width)
            cmd6 = 'rm tmp'

            runIon.runCmd(cmd1)
            runIon.runCmd(cmd2)
            runIon.runCmd(cmd3)
            runIon.runCmd(cmd4)
            runIon.runCmd(cmd5)
            runIon.runCmd(cmd6)
        ###############################################################

        # compute coherence only using interferogram
        # here I use differential interferogram of lower and upper band
        # interferograms so that coherence is not affected by fringes
        cord = runIon.cal_coherence(
            lowerint*np.conjugate(upperint), win=3, edge=4)
        cor = np.zeros((length*2, width), dtype=np.float32)
        cor[0:length*2:2,
            :] = np.sqrt((np.absolute(lowerint)+np.absolute(upperint))/2.0)
        cor[1:length*2:2, :] = cord
        cor.astype(np.float32).tofile(corfile)

        # img = isceobj.Image.createUnwImage()
        img = isceobj.createOffsetImage()
        img.setFilename(corfile)
        img.extraFilename = corfile + '.vrt'
        img.setWidth(width)
        img.setLength(length)
        img.renderHdr()

        # MG: replace unwrap, and compute iono code as
        # the only change is the iono merged directory

        # STEP 2. UNWRAP SWATH INTERFEROGRAM
        unwrap(self, ionParam,
               use_bridging=use_bridging,
               use_conncomp=conncomp_flag)

        # STEP 3. COMPUTE IONOSPHERE
        ionosphere(self, ionParam)

        # Load the results of ionosphere computation
        outDir = os.path.join(ionParam.ionDirname, ionParam.ioncalDirname)
        outFilename = os.path.join(outDir, ionParam.ionRawNoProj)
        corFilename = os.path.join(outDir, ionParam.ionCorNoProj)

        img = isceobj.createImage()
        img.load(outFilename + '.xml')
        width = img.width
        length = img.length

        ionos = (np.fromfile(outFilename, dtype=np.float32).reshape(
            length*2, width))[1:length*2:2, :]
        amp = (np.fromfile(outFilename, dtype=np.float32).reshape(
            length*2, width))[0:length*2:2, :]
        cor = (np.fromfile(corFilename, dtype=np.float32).reshape(
            length*2, width))[1:length*2:2, :]

        ionosList.append(ionos)
        corList.append(cor)
        ampList.append(amp)

    # MG Get the last lower unwrapped
    # interferogram path
    lowerUnwfile = os.path.join(ionParam.ionDirname,
                                ionParam.lowerDirname,
                                ionParam.mergedDirname,
                                self._insar.unwrappedIntFilename)

    # MG: use image size from lower unwrapped
    # interferogram swath
    img = isceobj.createImage()
    img.load(lowerUnwfile + '.xml')
    width = img.width
    length = img.length

    # MG: reset ionParm mergedDirname
    ionParam.mergedDirname = mergedDirname
    ionParam.ioncalDirname = ioncalDirname

    # do adjustment between adjacent swaths
    if numValidSwaths == 3:
        adjustList = [ionosList[0], ionosList[2]]
    else:
        adjustList = [ionosList[0]]
    for adjdata in adjustList:
        masked_cor = corList[1] > corThresholdSwathAdj
        index = np.nonzero(
            (adjdata != 0) * (ionosList[1] != 0) * masked_cor)
        if index[0].size < 5:
            print(f'WARNING: too few samples available for adjustment'
                  f' between swaths: {index[0].size} with coherence '
                  f'threshold: {corThresholdSwathAdj}')
            print('         no adjustment made!')
            print(
                '         to do ajustment, please consider using'
                ' lower coherence threshold')
        else:
            print(f'number of samples available for adjustment in the'
                  f' overlap area: {index[0].size}')

            # use weighted mean instead
            wgt = corList[1][index]**14
            diff = np.sum((ionosList[1] - adjdata)[index] * wgt /
                          np.sum(wgt, dtype=np.float64), dtype=np.float64)

            index2 = np.nonzero(adjdata != 0)
            adjdata[index2] = adjdata[index2] + diff

    # get merged ionosphere
    ampMerged = np.zeros((length, width), dtype=np.float32)
    corMerged = np.zeros((length, width), dtype=np.float32)
    ionosMerged = np.zeros((length, width), dtype=np.float32)
    for i in range(numValidSwaths):
        nBurst = len(burstValidBox[i])
        for j in range(nBurst):

            # index after multi-looking in merged image, index
            # starts from 1
            first_line = np.int32(
                np.around((burstValidBox[i][j][0] - 1) /
                          numberAzimuthLooks + 1))
            last_line = np.int32(
                np.around(burstValidBox[i][j][1] /
                          numberAzimuthLooks))
            first_sample = np.int32(
                np.around((burstValidBox[i][j][2] - 1) /
                          numberRangeLooks + 1))
            last_sample = np.int32(
                np.around(burstValidBox[i][j][3] /
                          numberRangeLooks))

            corMerged[first_line-1:last_line-1+1,
                      first_sample-1:last_sample-1+1] = \
                corList[i][first_line-1:last_line-1 +
                           1, first_sample-1:last_sample-1+1]

            ampMerged[first_line-1:last_line-1+1,
                      first_sample-1:last_sample-1+1] = \
                ampList[i][first_line-1:last_line-1 +
                           1, first_sample-1:last_sample-1+1]

            ionosMerged[first_line-1:last_line-1+1,
                        first_sample-1:last_sample-1+1] = \
                ionosList[i][first_line-1:last_line -
                             1+1, first_sample-1:last_sample-1+1]

    # remove an empirical ramp
    # MG this part can be commented out as ramp is not applied to iono
    # leave it here for now
    if ionParam.rampRemovel != 0:
        warningInfo = (f'{datetime.datetime.now()} calculating ionosphere for '
                       f'cross S-1A/B interferogram, an empirical ramp is '
                       f'removed from estimated ionosphere\n')

        warning_file = os.path.join(ionParam.ionDirname, ionParam.warning)
        with open(warning_file, 'a') as f:
            f.write(warningInfo)

        abramp = runIon.cal_cross_ab_ramp(
            swathList, box[1], numberRangeLooks, ionParam.passDirection)
        if ionParam.rampRemovel == -1:
            abramp *= -1.0
        # currently do not apply this
        # ionosMerged -= abramp[None, :]

    # dump ionosphere
    outDir = os.path.join(ionParam.ionDirname, ionParam.ioncalDirname)
    os.makedirs(outDir, exist_ok=True)
    outFilename = os.path.join(outDir, ionParam.ionRawNoProj)
    ion = np.zeros((length*2, width), dtype=np.float32)
    ion[0:length*2:2, :] = ampMerged
    ion[1:length*2:2, :] = ionosMerged
    ion.astype(np.float32).tofile(outFilename)
    img.filename = outFilename
    img.extraFilename = outFilename + '.vrt'
    img.renderHdr()

    # dump coherence
    outFilename = os.path.join(outDir, ionParam.ionCorNoProj)
    ion[1:length*2:2, :] = corMerged
    ion.astype(np.float32).tofile(outFilename)
    img.filename = outFilename
    img.extraFilename = outFilename + '.vrt'
    img.renderHdr()


def ionosphere(self, ionParam):

    ###################################
    # SET PARAMETERS HERE
    # THESE SHOULD BE GOOD ENOUGH, NO NEED TO SET IN setup(self)
    corThresholdAdj = 0.85
    ###################################

    print('computing ionosphere')
    # get files
    unw_filename = self._insar.unwrappedIntFilename
    cor_filename = self._insar.correlationFilename

    lowerUnwfile = os.path.join(ionParam.ionDirname, ionParam.lowerDirname,
                                ionParam.mergedDirname, unw_filename)
    upperUnwfile = os.path.join(ionParam.ionDirname, ionParam.upperDirname,
                                ionParam.mergedDirname, unw_filename)
    corfile = os.path.join(ionParam.ionDirname, ionParam.lowerDirname,
                           ionParam.mergedDirname, cor_filename)

    # use image size from lower unwrapped interferogram
    img = isceobj.createImage()
    img.load(lowerUnwfile + '.xml')
    width = img.width
    length = img.length

    lowerUnw = np.fromfile(lowerUnwfile, dtype=np.float32)
    lowerUnw = lowerUnw.reshape(length*2, width)[1:length*2:2, :]
    upperUnw = np.fromfile(upperUnwfile, dtype=np.float32)
    upperUnw = upperUnw.reshape(length*2, width)[1:length*2:2, :]
    lowerAmp = np.fromfile(lowerUnwfile, dtype=np.float32)
    lowerAmp = lowerAmp.reshape(length*2, width)[0:length*2:2, :]
    upperAmp = np.fromfile(upperUnwfile, dtype=np.float32)
    upperAmp = upperAmp.reshape(length*2, width)[0:length*2:2, :]
    cor = np.fromfile(corfile, dtype=np.float32)
    cor = cor.reshape(length*2, width)[1:length*2:2, :]
    amp = np.sqrt(lowerAmp**2+upperAmp**2)

    # masked out user-specified areas
    if ionParam.maskedAreas is not None:
        maskedAreas = runIon.reformatMaskedAreas(ionParam.maskedAreas,
                                                 length, width)
        for area in maskedAreas:
            lowerUnw[area[0]:area[1], area[2]:area[3]] = 0
            upperUnw[area[0]:area[1], area[2]:area[3]] = 0
            cor[area[0]:area[1], area[2]:area[3]] = 0

    # MG: Check if there is data for compution iono
    # skip if array is all 0s
    if np.flatnonzero(lowerUnw).size == 0:
        print('WARNING: lower/upper band data all zero'
              ' skip iono computation!')
        ionos = np.zeros_like(lowerUnw)
    else:
        # compute ionosphere
        fl = runIon.SPEED_OF_LIGHT / ionParam.radarWavelengthLower
        fu = runIon.SPEED_OF_LIGHT / ionParam.radarWavelengthUpper
        # polynomial method for removing relative phase unwrapping errors
        adjFlag = 1
        ionos = runIon.computeIonosphere(lowerUnw, upperUnw, cor, fl, fu,
                                         adjFlag, corThresholdAdj, 0)

    # dump ionosphere
    outDir = os.path.join(ionParam.ionDirname, ionParam.ioncalDirname)
    os.makedirs(outDir, exist_ok=True)
    outFilename = os.path.join(outDir, ionParam.ionRawNoProj)
    ion = np.zeros((length*2, width), dtype=np.float32)
    ion[0:length*2:2, :] = amp
    ion[1:length*2:2, :] = ionos
    ion.astype(np.float32).tofile(outFilename)
    img.filename = outFilename
    img.extraFilename = outFilename + '.vrt'
    img.renderHdr()

    # dump coherence
    outFilename = os.path.join(ionParam.ionDirname,
                               ionParam.ioncalDirname,
                               ionParam.ionCorNoProj)
    ion[1:length*2:2, :] = cor
    ion.astype(np.float32).tofile(outFilename)
    img.filename = outFilename
    img.extraFilename = outFilename + '.vrt'
    img.renderHdr()
