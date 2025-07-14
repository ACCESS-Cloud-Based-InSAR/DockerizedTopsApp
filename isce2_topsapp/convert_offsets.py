import numpy as np


def load_product(xml_name):
    """Load the product using Product Manager.
    :param xml_name: The name of the xml file to load.
    :return: The loaded product.
    """
    from iscesys.Component.ProductManager import ProductManager

    pm = ProductManager()
    pm.configure()
    return pm.loadProduct(xml_name)


def get_conversion_factors(reference_xml):
    """Get the conversion factors for converting offsets from pixels to meters.
    :param reference_xml: The reference xml file.
    :return: The conversion factors used for converting azimuth and range from pixels to meters.
    """
    from isceobj.Planet.Planet import Planet

    obj = load_product(reference_xml)
    burst = obj.bursts[0]
    rangePixelSize = burst.rangePixelSize

    # Get azimuthPixelSize from satellite speed and height
    azimuthTimeInterval = burst.azimuthTimeInterval
    sensingMid = burst.sensingMid
    orb = obj.orbit
    Vs = np.linalg.norm(orb.interpolateOrbit(sensingMid,
                                             method='hermite').getVelocity())  # satellite velocity at center
    Ps_vec = orb.interpolateOrbit(sensingMid, method='hermite').getPosition()
    Ps = np.linalg.norm(Ps_vec)  # satellite position at center

    # Approximate terrain height
    terrainHeight = burst.terrainHeight

    # Latitude, Longitude, Elevation at image center
    midRange = burst.midRange
    llh_cen = orb.rdr2geo(sensingMid, midRange, height=terrainHeight)

    refElp = Planet(pname='Earth'). ellipsoid
    xyz_cen = refElp.llh_to_xyz(llh_cen)  # xyz coordinate at image center

    Re = np.linalg.norm(xyz_cen)
    cosb = (Ps**2 + Re**2 - midRange**2)/(2*Ps*Re)
    Vg = (Re*cosb)*Vs/Ps

    azimuthPixelSize = azimuthTimeInterval*Vg

    print('satellite velocity (m/s)', Vs)
    print('satellite velocity over the ground (m/s)', Vg)
    print('rangePixelSize (m)', rangePixelSize)
    print('azimuthPixelSize (m)', azimuthPixelSize)
    return azimuthPixelSize, rangePixelSize


def convert_offsets(dense_offsets, amplitude, reference_xml):
    """Convert dense offsets from pixels to meters.
    :param dense_offsets: The dense offsets file.
    :param amplitude: The amplitude file.
    :param reference_xml: The reference xml file.
    """

    from osgeo import gdal

    # Get the conversion factors
    azimuthPixelSize, rangePixelSize = get_conversion_factors(reference_xml)

    # Open the input raster
    dense_offsets_pix = gdal.Open(dense_offsets)
    if not dense_offsets_pix:
        raise RuntimeError(f"Failed to open file: {dense_offsets_pix}")

    # Open amplitude which will be used for masking
    amplitude_pix = gdal.Open(amplitude)
    if not amplitude_pix:
        raise RuntimeError(f"Failed to open file: {amplitude}")
    amp = amplitude_pix.GetRasterBand(1).ReadAsArray()
    amp_NoData = amplitude_pix.GetRasterBand(1).GetNoDataValue()
    if amp_NoData is None:
        amp_NoData = 0  # Default to 0 if NoData value is not explicitly set

    # NoData value for the output raster
    nodata_value = -10000

    # Read the first band (azimuth) and convert, set nodata value where amplitude is nodata
    azimuth_pix = dense_offsets_pix.GetRasterBand(1).ReadAsArray()
    azimuth_m = np.where(
        (amp == amp_NoData) | (azimuth_pix == nodata_value),
        nodata_value,
        azimuth_pix * azimuthPixelSize
    )

    # Read the second band (range) and convert
    range_pix = dense_offsets_pix.GetRasterBand(2).ReadAsArray()
    range_m = np.where(
        (amp == amp_NoData) | (range_pix == nodata_value),
        nodata_value,
        range_pix * rangePixelSize
    )

    # Write the converted arrays to a new raster
    driver = gdal.GetDriverByName("ISCE")
    outfile = "merged/filt_dense_offsets_m.geo"

    # Create the new raster
    dense_offsets_m = driver.Create(outfile, dense_offsets_pix.RasterXSize,
                                    dense_offsets_pix.RasterYSize, 2, gdal.GDT_Float32)

    # Get the raster bands
    band1 = dense_offsets_m.GetRasterBand(1)
    band2 = dense_offsets_m.GetRasterBand(2)

    # Set the NoData value for both bands before writing data
    band1.SetNoDataValue(nodata_value)
    band2.SetNoDataValue(nodata_value)

    # Write the azimuth_m array to band 1 and range_m array to band 2
    band1.WriteArray(azimuth_m)
    band2.WriteArray(range_m)

    # Flush data to disk
    band1.FlushCache()
    band2.FlushCache()

    # Ensure georeferencing information is same as input
    dense_offsets_m.SetGeoTransform(dense_offsets_pix.GetGeoTransform())
    dense_offsets_m.SetProjection(dense_offsets_pix.GetProjection())

    return
