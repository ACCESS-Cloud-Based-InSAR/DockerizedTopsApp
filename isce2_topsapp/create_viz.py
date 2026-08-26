import shutil
from pathlib import Path

import numpy as np
import rasterio
from osgeo import gdal
from rasterio.warp import Resampling, reproject


def colorize_netCDF_layer_COG(
    netcdf_path: str | Path,
    output_dir: str | Path,
    water_raster: str | Path,
    unfiltered_coherence: bool = False,
    dense_offsets: bool = False,
) -> None:
    """Produce 1-band cloud optimized GeoTIFFs from the NetCDF sublayers."""
    # Remove the main 'cogs' directory, if it already exists, and create a new one
    if Path(output_dir).exists():
        shutil.rmtree(output_dir)
    Path(output_dir).mkdir(parents=True)

    with rasterio.open(netcdf_path) as dataset:
        subdatasets = dataset.subdatasets
        if not subdatasets:
            print(f'No subdatasets found in {netcdf_path}')
            return

    # Define the rasters to process (based on DockerizedTopsApp inputs)
    if dense_offsets and unfiltered_coherence:
        rasters = [
            'amplitude',
            'azimuthPixelOffsets',
            'rangePixelOffsets',
            'unfilteredCoherence',
            'losDisplacement',
            'denseOffsetsSNR',
        ]
    elif dense_offsets and not unfiltered_coherence:
        rasters = [
            'amplitude',
            'azimuthPixelOffsets',
            'rangePixelOffsets',
            'losDisplacement',
            'denseOffsetsSNR',
        ]
    elif not dense_offsets and unfiltered_coherence:
        rasters = ['amplitude', 'unfilteredCoherence', 'losDisplacement']
    else:
        rasters = ['amplitude', 'losDisplacement']

    # Ensure the output directories exist
    single_band_dir = Path(output_dir) / 'cogs_1band'
    single_band_dir.mkdir(parents=True, exist_ok=True)

    for raster in rasters:
        subdataset_name = f'NETCDF:"{netcdf_path}":/science/grids/data/{raster}'
        conn_comp = f'NETCDF:"{netcdf_path}":/science/grids/data/connectedComponents'
        unfiltered_coherence = f'NETCDF:"{netcdf_path}":/science/grids/data/unfilteredCoherence'

        print(f'Processing layer: {raster}')

        # Construct output paths
        output_single_band = str(single_band_dir / f'{raster}.tif')

        # Open the subdataset to get its metadata and grid
        with rasterio.open(subdataset_name) as src:
            data = src.read(1)
            data_transform = src.transform
            data_crs = src.crs
            data_width = src.width
            data_height = src.height
            nodata_value = src.nodata

        # For amplitude layer, convert to dB (log scale)
        if raster == 'amplitude':
            data = 20 * np.log10(np.where(data > 0, data, np.nan))
            data = np.nan_to_num(data, nan=0)

        # Open the water raster and align it to the data raster
        with rasterio.open(water_raster) as src:
            # Create an empty array to store the resampled water raster
            aligned_water = np.empty((data_height, data_width), dtype=src.meta['dtype'])

            # Reproject the water raster to align with the data raster
            reproject(
                source=rasterio.band(src, 1),
                destination=aligned_water,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=data_transform,
                dst_crs=data_crs,
                dst_width=data_width,
                dst_height=data_height,
                resampling=Resampling.nearest,
            )

            # Set the nodata value where aligned_water == 255
            if nodata_value is not None:
                data[aligned_water == 255] = nodata_value
                data = np.ma.masked_equal(data, nodata_value)

        # Apply connected components and coherence mask to all layers except
        # rangePixelOffsets and azimuthPixelOffsets
        if raster not in [
            'rangePixelOffsets',
            'azimuthPixelOffsets',
            'denseOffsetsSNR',
        ]:
            with rasterio.open(conn_comp) as src:
                connComp = src.read(1)

            msk = np.array(connComp) * -1
            msk[msk < 0] = 1

            with rasterio.open(unfiltered_coherence) as src:
                unfCoherence = src.read(1)

            # Apply additional mask for unfiltered_coherence < 0.5
            msk[unfCoherence < 0.5] = 0  # Update mask where coherence is low

            # Apply the combined mask
            data = data * msk
            data[data == 0] = nodata_value  # Convert all zeros to nodata_value
            data = np.ma.masked_equal(data, nodata_value)  # Apply masking

        # Change nodata pixels to -10000 and update nodata value
        new_nodata_value = -10000
        data[data == nodata_value] = new_nodata_value
        nodata_value = new_nodata_value

        # Write the single-band raster as a compressed Cloud Optimized GeoTIFF (COG)
        with rasterio.open(
            output_single_band,
            'w',
            driver='GTiff',
            count=1,
            dtype=data.dtype,
            width=data_width,
            height=data_height,
            crs=data_crs,
            transform=data_transform,
            nodata=nodata_value,
            compress='DEFLATE',  # Apply DEFLATE compression
            tiled=True,  # Enable tiling for COG compatibility
            predictor=2,  # Use horizontal differencing predictor (good for float data)
            bigtiff='YES',  # Support large files
        ) as dst:
            dst.write(data, 1)  # Write the masked data to the first band

        # Create a temporary file in the same directory
        temp_output = output_single_band + '.tmp.tif'

        # Write as a proper COG to the temp file
        gdal.Translate(
            temp_output,
            output_single_band,
            options=gdal.TranslateOptions(
                format='COG',
                creationOptions=['COMPRESS=DEFLATE', 'BIGTIFF=YES', 'PREDICTOR=2'],
            ),
        )

        # Replace the original with the temp file
        Path(temp_output).replace(output_single_band)

    return


def create_viz_files(
    nc: str | Path,
    outdir_viz: str | Path,
    water_mask_path: str | Path,
    unfiltered_coherence: bool,
    dense_offsets: bool,
) -> None:
    print('=====================================')
    print('Making viz files...')
    print('=====================================')
    colorize_netCDF_layer_COG(nc, outdir_viz, water_mask_path, unfiltered_coherence, dense_offsets)
    print('=====================================')
    print('Viz files generated successfully.')
    print('=====================================')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Process netCDF files.')
    parser.add_argument('nc', help='Path to the netCDF file')
    parser.add_argument('outdir_viz', help='Path to the output directory')
    parser.add_argument('water_mask', help='Path to the water mask raster')
    parser.add_argument('unfiltered_coherence', help='True/False for unfiltered coherence arg')
    parser.add_argument('dense_offsets', help='True/False for dense offsets arg')
    args = parser.parse_args()
    create_viz_files(
        args.nc,
        args.outdir_viz,
        args.water_mask,
        args.unfiltered_coherence,
        args.dense_offsets,
    )
