import os
import shutil
import subprocess

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib import colors
from rasterio.warp import Resampling, reproject


def colorize_netCDF_layer_COG(netcdf_path, output_dir, water_raster):

    """
    Function to produce 4-band cloud optimized GeoTIFFs from a NetCDF sublayers.
    """
    # Remove the main 'cogs' directory, if it already exists, and create a new one
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    with rasterio.open(netcdf_path) as dataset:
        subdatasets = dataset.subdatasets
        if not subdatasets:
            print(f"No subdatasets found in {netcdf_path}")
            return

    # Define the rasters to process
    rasters = ['amplitude', 'azimuthPixelOffsets', 'rangePixelOffsets', 'unfilteredCoherence', 'losDisplacement']

    # Ensure the output directories exist
    single_band_dir = os.path.join(output_dir, "cogs_1band")
    img_tif_dir = os.path.join(output_dir, "imgtiffs")
    viz_dir = os.path.join(output_dir, "cogs_4band")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(single_band_dir, exist_ok=True)
    os.makedirs(img_tif_dir, exist_ok=True)
    os.makedirs(viz_dir, exist_ok=True)

    for raster in rasters:
        subdataset_name = f"NETCDF:\"{netcdf_path}\":/science/grids/data/{raster}"
        conn_comp = f"NETCDF:\"{netcdf_path}\":/science/grids/data/connectedComponents"
        unfiltered_coherence = f"NETCDF:\"{netcdf_path}\":/science/grids/data/unfilteredCoherence"

        print(f"Processing layer: {raster}")

        # Construct output paths
        color_table_file = os.path.join(output_dir, f"{raster}_color_table.txt")
        output_single_band = os.path.join(single_band_dir, f"{raster}.tif")
        output_colorized = os.path.join(output_dir, f"{raster}_colorized.tif")
        colorized_float32 = os.path.join(output_dir, f"{raster}_colorized_float32.tif")
        output_imgtiff = os.path.join(img_tif_dir, f"{raster}_img.tif")
        vrt_file = os.path.join(output_dir, f"{raster}_temp.vrt")
        final_output = os.path.join(viz_dir, f"{raster}.tif")

        # Determine the colormap based on the raster layer
        if raster in ['azimuthPixelOffsets', 'rangePixelOffsets', 'losDisplacement']:
            cmap = plt.get_cmap("RdBu_r")
            is_grayscale = False
        else:
            cmap = plt.get_cmap("Greys_r")
            is_grayscale = True

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
            data = 10 * np.log10(np.where(data > 0, data, np.nan))
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
                resampling=Resampling.nearest
            )

            # Set the nodata value where aligned_water == 255
            if nodata_value is not None:
                data[aligned_water == 255] = nodata_value
                data = np.ma.masked_equal(data, nodata_value)

        # Open the connected components raster and mask the data
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

        # Write the single-band raster as a compressed Cloud Optimized GeoTIFF (COG)
        with rasterio.open(
            output_single_band, 'w',
            driver='GTiff',
            count=1,
            dtype=data.dtype,
            width=data_width,
            height=data_height,
            crs=data_crs,
            transform=data_transform,
            nodata=nodata_value,
            compress="DEFLATE",   # Apply DEFLATE compression
            tiled=True,           # Enable tiling for COG compatibility
            predictor=2,          # Use horizontal differencing predictor (good for float data)
            bigtiff="YES"         # Support large files
        ) as dst:
            dst.write(data, 1)  # Write the masked data to the first band

        # Calculate 2nd and 98th percentiles for visualization
        p2 = np.percentile(data.compressed(), 2)
        p98 = np.percentile(data.compressed(), 98)
        print(f"{subdataset_name}: p2 = {p2}, p98 = {p98}")

        # Create a normalized colormap from the percentile range
        norm = colors.Normalize(vmin=p2, vmax=p98)

        # Generate color table content
        color_table_lines = []

        for value in np.linspace(p2, p98, 256):
            if is_grayscale:
                intensity = int(255 * (value - p2) / (p98 - p2))
                intensity = max(intensity, 1)
                color_table_lines.append(f"{value:.5f} {intensity} {intensity} {intensity}")
            else:
                rgba = cmap(norm(value))
                rgb = tuple(max(int(c * 255), 1) for c in rgba[:3])  # Normalize to 0-255 and replace 0 with 1
                color_table_lines.append(f"{value:.5f} {rgb[0]} {rgb[1]} {rgb[2]}")

        # Handle nodata values by adding "nodata" for the nodata range
        if nodata_value is not None:
            color_table_lines.insert(0, f"{nodata_value:.5f} 0 0 0")

        # Save the color table to the output directory
        with open(color_table_file, "w") as f:
            f.write("\n".join(color_table_lines))
        print(f"Color table saved as {color_table_file}")

        # Run gdaldem color-relief to generate the colorized raster with three bands (RGB)
        subprocess.run(
            [
                "gdaldem", "color-relief", output_single_band, color_table_file, output_colorized,
                "-co", "COMPRESS=DEFLATE",       # Use DEFLATE compression
                "-co", "PREDICTOR=2",            # Use horizontal differencing predictor
                "-co", "TILED=YES"               # Enable tiling for better performance
            ],
            check=True
        )

        # Convert the color bands (RGB) to float32
        subprocess.run(
            [
                "gdal_translate", output_colorized, colorized_float32,
                "-ot", "Float32",               # Convert to float32
                "-co", "COMPRESS=DEFLATE",      # Use DEFLATE compression
                "-co", "PREDICTOR=2",           # Use horizontal differencing predictor
                "-co", "TILED=YES"              # Enable tiling for better performance
            ],
            check=True
        )

        # Modify pixel values of 0 to nodata_value in any band, which is needed for merging
        subprocess.run(
            [
                "gdal_calc.py",
                "-A", f"{colorized_float32}",  # Input raster
                "--calc", f"where(A==0, {nodata_value}, A)",  # Apply the conditional operation
                "--NoDataValue", str(nodata_value),  # Set NoData value dynamically
                "--allBands=A",                      # Process all bands from the input raster
                "--outfile", output_imgtiff,  # Specify the output raster
                "--co", "COMPRESS=DEFLATE",          # Use DEFLATE compression
                "--co", "PREDICTOR=2",               # Use horizontal differencing predictor
                "--co", "TILED=YES"                  # Enable tiling for better performance
            ],
            check=True
        )

        # Create individual 1-band VRTs for each of the colorized bands (RGB)
        rgb_vrts = []
        for band_idx in range(1, 4):  # Bands 1, 2, 3 for RGB
            vrt_band_file = os.path.join(output_dir, f"{raster}_colorized_band{band_idx}.vrt")
            subprocess.run(
                [
                    "gdal_translate",
                    "-of", "VRT",
                    "-b", str(band_idx),
                    output_imgtiff,
                    vrt_band_file
                ],
                check=True
            )
            rgb_vrts.append(vrt_band_file)

        # Now build the 4-band VRT, including the original subdataset (band 1) and the 3 RGB bands
        subprocess.run(
            [
                "gdalbuildvrt", "-separate", "-overwrite",
                vrt_file, subdataset_name, *rgb_vrts
            ],
            check=True
        )

        # Create the final 4-band GeoTIFF as a Cloud Optimized GeoTIFF (COG)
        subprocess.run(
            [
                "gdal_translate", vrt_file, final_output,
                "-a_nodata", str(nodata_value),     # Set nodata value
                "-co", "COMPRESS=DEFLATE",          # DEFLATE compression
                "-co", "PREDICTOR=2",               # Horizontal differencing predictor
                "-co", "TILED=YES",                 # Enable tiling (required for COG)
                "-co", "BIGTIFF=YES",               # Ensures support for large files
            ],
            check=True
        )

        print(f'Final COG saved as {final_output}')
        # Delete intermediate files (except the final output)
        temp_files = [color_table_file, output_colorized, colorized_float32, vrt_file, *rgb_vrts]

        # Remove all temporary files
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                print(f"Deleted temporary file: {temp_file}")

    return


def create_viz_files(nc, outdir_viz, water_mask_path):
    print("=====================================")
    print("Making viz files...")
    print("=====================================")
    colorize_netCDF_layer_COG(nc, outdir_viz, water_mask_path)
    print("=====================================")
    print("Viz files generated successfully.")
    print("=====================================")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Process netCDF files.")
    parser.add_argument('nc', help="Path to the netCDF file")
    parser.add_argument('outdir_viz', help="Path to the output directory")
    parser.add_argument('water_mask', help="Path to the water mask raster")
    args = parser.parse_args()
    create_viz_files(args.nc, args.outdir_viz, args.water_mask)
