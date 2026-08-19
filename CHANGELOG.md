# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.3]

### Fixed
* `isce2_topsapp` CLI dispatch raised `KeyError: 'console_scripts'` on Python 3.12. Now uses the `entry_points(group=..., name=...)` API, resolving the long-standing `FIXME`.
* Updated dem to match NISAR-DEM within 1 cm.
* The JRC/Pekel water mask no longer punches holes in the open ocean. The `255` no-data code is now honored (previously it was reprojected with bilinear resampling, which averaged `255` into neighboring occurrence values and painted a spurious water halo along every no-data edge) and the occurrence threshold dropped from `95` to `90` percent, since open ocean dithers between ~90 and 100 along Landsat WRS-2 scene edges. No-data blocks are dilated by 3 pixels to swallow the thin rim of `0`-occurrence pixels that reads as land and draws hairline seams through the sea. The thresholding logic lives in `water_mask.water_mask_from_occurrence` and is shared by the browse-image mask (`water_mask.py`) and the ISCE2 processing mask (`localize_mask.py`), so the two can no longer drift apart. The processing mask filename now tracks the threshold constant.

### Changed
* Migrated environment management from `conda`/`mamba` to [`pixi`](https://pixi.sh). All configuration now lives in `pyproject.toml` under the `[tool.pixi.*]` tables and the resolved set is locked in `pixi.lock`.
* `environment.yml` is retained as an unvalidated, transitional path for `conda`/`mamba` users; it will be removed once it stops solving. `pyproject.toml`/`pixi.lock` is the source of truth and is what CI and the Docker image build from.
* Supported platforms are `linux-64` and `osx-64` (`ISCE2` is Intel-only, and pixi runs `osx-64` under Rosetta on Apple Silicon).
* Python 3.11 and 3.12 are now separate pixi environments (`py311`, `py312`); `default` is `py311`. The PyTest matrix iterates over these environments.
* `Dockerfile` builds from `ghcr.io/prefix-dev/pixi` and installs from `pixi.lock` with `pixi install --locked`; the entrypoint uses `pixi run`.
* Replaced the `reusable-ruff` and `reusable-version-info` ASFHyP3 workflows with inline pixi jobs, as both consumed `environment.yml`.
* The three notebooks previously executed by `papermill` in `tests/test_notebooks.py` are now plain pytest modules (`tests/test_localize.py` and `tests/test_delivery_prep.py`); the notebooks themselves are kept for interactive use in `tests/legacy_notebooks/`.
* Solid earth tide test data is computed once per session via the `gunw_paths_with_set` fixture rather than recomputed by each test, and the notebook-derived tests read local test data instead of downloading a GUNW from ASF.
* Tests that write to the working directory now run under `tmp_path`, so DEMs, orbits and AUX_CAL files no longer accumulate in the repository root.
* Moved the sample delivered GUNW metadata from the repository root into `tests/test_data/`.
* Loosened the stale `scipy<1.10` and `jsonschema==3.2.0` pins (neither is required by the code) and pinned remaining dependencies with semver bounds. 
* `isce2` has been updated v2.6.5 to enable full S1C and S1D support. `isce2` is still strictly pinned to `==2.6.5`.

### Removed
* `tox.ini`, which only carried `flake8` configuration superseded by `ruff`.
* `papermill` as a dependency, along with the `tests/out` notebook output directory.
* `tests/test_notebooks.py` and the stray delivered-GUNW directory that the delivery notebook left in the repository root.

### Added
* Support for downloading Sentinel-1 SLC granules from the Copernicus Data Space Ecosystem (CDSE) as an alternative to ASF. Metadata retrieval and bounding box checks continue to use ASF. Download from CDSE uses the compressed `.zip` archive directly, leveraging ISCE2's virtual file access to reduce download traffic.
* Sentinel-1D support: updated AUX_CAL downloads, DAAC ingest schema, and SLC localization to accept S1D data. AUX_CAL downloads for S1C/S1D gracefully skip with a warning if the files are not yet published.
* `notebooks/water_mask/water_mask_check.ipynb`, which reproduces the browse-image mask over a Southern California GUNW and sweeps the occurrence threshold and no-data handling that motivated the fix above.
* Added `S1D_MIN_DATE` (2026-06-24) placeholder to reject uncalibrated S1D acquisitions, mirroring the existing `S1C_MIN_DATE` check. This is currently the ARIA/OPERA agreed upon date (as noted in compass [here](https://github.com/opera-adt/COMPASS/blob/5bdef5e1199de52e83a1f31afb1c9a6ec8a33e9d/scripts/README.md?plain=1#L126)).

## [1.0.2]

### Changed
- Upgraded to `asf_search>=10.0.5` to resolve jobs failing with `ASFAuthenticationError: Username or password is incorrect`
  due to https://github.com/asfadmin/Discovery-asf_search/issues/396.

## [1.0.1]

### Added
* Support for latest ISCE2 and therefore python 3.10 - 3.12!
* Sentinel-1C support (inherited from ISCE2). Ensure we are not filtering for S1C in localization.
* Error out for S1C data generated prior to May 19th, 2025 as noted here: https://sentinels.copernicus.eu/-/sentinel-1c-products-are-now-calibrated
* Use ruff rather than flake8 (added to environment.yml), update actions to latest, and ensure we are up-to-date for CI/CD.
* Fix ruff formatting across repository


## [1.0.0]
This update provides new functionality for production of an the earthquake-specific, sensor-agnostic `COSEIS_SAR` product, while leaving the standard `GUNW` product generation functionality (`0.6.0`) unchanged.

### Added
* `coseis_sar` entry point and `coseis_sar` function added in `__main__.py` and `setup.py`, enabling generation of `COSEIS_SAR` products using existing `GUNW` framework.
* `create_viz.py` added to generate visualization files (single-band geotiffs, multi-band geotiffs,and imgtiffs) for delivery to S3 alongside `COSEIS_SAR` netCDF product (only when `++process coseis_sar` is specified).
* `convert_offsets.py` added to convert dense pixel offsets (range/azimuth) units from pixels to meters for `COSEIS_SAR` product (only when `++process coseis_sar` is specified).
* `convert_unwrapped.py` added to convert unwrapped phase from units of radians to meters for `COSEIS_SAR` product (only when `++process coseis_sar` is specified).

### Changed
* Updated `delivery_prep.py`, `packaging.py`, `__main__.py` to accommodate a variable naming scheme (currently `GUNW` and `COSEIS_SAR` are supported) and corresponding versioning for each product.
  - `product_naming_scheme` function added to `packaging.py` to return product name/version based `product` specified by user (`GUNW` or `COSEIS_SAR`). `GUNW` remains the default naming/versioning scheme if no `product` is specified.
  - `product` argument added to `prepare_for_delivery` and `format_metadata` functions in `delivery_prep.py` and to `package_gunw_product`, `get_gunw_id`, `perform_netcdf_packaging`, and `_write_json_config` functions in `packaging.py`. These modifications leverage new `product_naming_scheme` function from `packaging.py` to generate name/version dynamically for metadata and netCDF file naming purposes.
* Updated tests to accommodate dynamic naming/versioning scheme for `GUNW` and `COSEIS_SAR` products.
  - Rather than importing `DATASET_VERSION` from `packaging.py`, the `product_naming_scheme` function is imported and run in `GUNW` mode for testing.
  - `prepare-for-delivery.ipynb` modified to accommodate changes to `prepare_for_delivery` function in `delivery_prep.py`.
* Renamed `nc_packaging_template.json` to `nc_packaging_template_gunw.json` (no content changes) and added `nc_packaging_template_coseis-sar.json` with modifications replacing `unwrappedPhase` (radians) with `losDisplacement` (meters) for `COSEIS_SAR` product. Updated `read_netcdf_packaging_template` in `templates/__init__.py` to return the template corresponding to the specified `product`.
* `rangePixelOffsets` and `azimuthPixelOffsets` units changed from `rad` to `meter` and `input_relative_path` changed from `filt_dense_offsets.geo` to `filt_dense_offsets_m.geo` in `additional_layers.json`.
* Ampcor window size changed from 64x64 to 32x128 pixels in `topsapp_proc.py`. This change was made to account for ground resolution differences in range/azimuth direction (2.3m/14m), making range/azimuth pixel offset outputs approximately square, rather than rectangular.
* Updated `iono_processing` function in `iono_proc.py` to take and assign `range_looks` and `azimuth_looks` as arguments based on CLI-defined `output-resolution`. This is necessary for iono layer resolution to match 30- and 90-meter products. Corresponding updates were made in `__main__.py` when calling `iono_processing`.
* Updated download URLs for S1 AUX_CAL files from sar-mpc.eu to ASF-managed https://d3g9emy65n853h.cloudfront.net/ URLs. Fixes https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/issues/218.

### Fixed 
* Code formatting updated to comply with Flake8 rules.

## [0.6.0]

### Added
* `isce2_topsapp.__main__.gunw_slc` now accepts `--reference-date` and `--secondary-date` parameters as alternatives to
  `--reference-scenes` and `--secondary-scenes`. When provided, `gunw_slc` will process all Sentinel-1 IW SLC scenes for
  the given date and `--frame-id` in order to generate an ARIA_S1_GUNW product.

## [0.5.0]

### Added
* `--min-frame-coverage` parameter to `gunw_slc` entrypoint and `isce2_topsapp.__main__:gunw_slc`. Specifies a minimum
  percent of the ARIA Frame that the intersection of reference/secondary scenes must cover. Jobs not meeting the given
  threshold will raise an error rather than generating a GUNW product.
* Pushed formatting changes.

## [0.4.0]

### Changed
* Use `s1_orbits` rather than `hyp3lib` to download Sentinel-1 orbits files in `localize_orbits.download_orbits`

### Removed
* ESA username/password requirement; these credentials are no longer needed to download Sentinel-1 orbit files.

## [0.3.8]

### Fixed
* Aux cal files are now distributed from new locations and have nesting that must be removed. (See [PR](https://github.com/ASFHyP3/hyp3-isce2/pull/265/) from hyp3-isce2)


## [0.3.7]
* Updates dem-stitcher to 2.5.8 to ensure new (ARIA-managed) url for reading the Geoid EGM 2008. See this [issue](https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/issues/96).
* Ensure version/docker build use python 3 as done here: https://github.com/dbekaert/RAiDER/blob/32697d2e4e6908b8feb3b81a1df30cb5f4e49a24/.github/workflows/build.yml#L16-L17

## [0.3.6]

* Updates dem-stitcher to 2.5.6 to which updated to a new url for reading the Geoid EGM 2008. See this [issue](https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/issues/96).

## [0.3.5]

### Added
* Include `dask` in environment.yml as it appears to not be correctly handled in pandera: https://github.com/unionai-oss/pandera/issues/1525

## [0.3.4]

### Changed
* ISCE2 shenanigans (PYTHON_PATH, PATH, and logging changes) are now handled in the `isce2_topsapp.__init__` ensuring we only have to do it once, no matter where we are in the package.
* Update dataset version from `3.0.0` -> `3.0.1` to track products over areas processed during development of v3 product. In other words, large scale processing was done during v3 development but not all v3 products will be delivered to DAAC - we have standardized numerous attributes and layers. Utlimately, 3.0.0 and 3.0.1 at the DAAC will represent the v3 products created by this repository.

### Fixed
* The root logger is no longer set to DEBUG by ISCE2 preventing excessive logging from all packages in the environment

## [0.3.3]

### Fixed
* Orbit downloading cleanup - ensures no circular references seen in partial function

## [0.3.2]

### Changed
* We ensured that ASF is checked for orbits before ESA to improve reliability. Aims to resolve orbit download issues seen [here](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/issues/169) seen in large processing campaigns and possible errors associated with ESA downloading. 
* We include natural earth data in the plugin to exclude hitting the natural earth server and aims to resolve such issues identified [here](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/issues/170) in large processing campaigns.

## [0.3.1]

### Added
* Provides CLI options for:
  - output resolution: 30 meters or 90 meters (the latter is default and the standardized GUNW resolution)
  - unfiltered coherence layer (True/False)
  - Goldstein filtering power - power that phase is raised to in patch FFT - default .5 (can be any number >= 0)
  - Dense offsets layers (True/false)
* Codifies (in documentation and in plugin) what is meant by "standard" GUNW with respect to exposed parameters including:
  - 90 m resolution
  - .5 value in the Goldstein filter for InSAR phase
  - No ESD or dense offsets
  - Additional layers: ionosophere, SET, and unfiltered coherence.
  - uses pydantic to record relevant topsapp parameters for "standard" GUNW
* Records parameters in the product including the CLI command to regenerate said product
* If parameters are not standard uses prefix `S1-GUNW_CUSTOM-...`
* Pydantic dependency for parameter accounting

### Changed
* The CLI now *requires* `frame_id` (use `frame_id = -1` for old API and what is now considered a "non"-standard product)
* Water mask now uses `tile-mate>=0.0.8` to download and merge water mask tiles (Pekel Occurence data >= 95 is the default) 
* All water masks applied to processing/packaging use Pekel Occurence (>= 95 percent occurence): ionosphere processing, browse imagery, and global attributes associate with mean coherence
* Some function names associated to writing global attributes in the netcdf file were renamed to be more descriptive e.g. `record_stats` became `record_stats_as_global_attrs`

## [0.3.0]

### Added
* `check_esa_credentials` function to `__main__.py` to check for the existence of Dataspace credentials before processing begins.

### Changed
* Updated `hyp3lib` to  v2.0.2+, which uses the new Copernicus Dataspace Ecosystem API to download orbit files.
* Calls to `downloadSentinelOrbitFile` now specify the `esa_credentials` argument.

## [0.2.5]

### Fixed
* For SET azimuth time interpolation, overlapping orbits produces errors with prepping state vectors for azimuth time grid. We now ensure state-vecotors are both unique and in order before creating a orbit object in ISCE2.

## [0.2.4]

### Added
* `++omp-num-threads` parameter to the `main()` entrypoint to limit the number of threads used by ISCE2 during
  multiprocessing.

### Fixed
* For Solid Earth Tide computation, use azimuth timing to calculate solid earth tide in `science/grids/imagingGeometry` reference frame using ISCE2 rdr2geo.
* Include topsapp_iono template.
* Increases DEM buffer to .4 from .1 to ensure the extent of at least two bursts (~40 km) are added when retrieving DEM (because estimated footprint can differ from what ISCE2 generates for a GUNW extent)
* Catch warnings in tests and match messages to ensure package warnings do not fail test suite
* Read low resolution Natural Earth land masses from public url due to removal from geopandas package.
* For ionosphere computation over water, includes masking conncomp zero, phase bridging, and modified adaptive gaussian filtering
* Fix for #135, skip iono computation if there are not land (all zero values) and skip using water mask if the area is outside of SWBD coverage
* Fix for #145 and SET - duplicate orbit xmls for computing azimuth time grid with ISCE2 geo2rdr (duplicate state vectors likely culprit). Ensures orbit object is intialized with unique set of orbit xmls passed. Also, localized metadata appropriately.

### Added
* localize_data within __main__.py added option to use/not use water mask for ionosphere processing
* Added option to estimate burst phase jumps in ionosphere computation
* Added additional attributes for ionosphere computation into GUNW ionosphere layer metadata: processing_steps, water_mask, mask_connected_component_zero (flag) , do_phase_bridging (flag), swath_mode (flag), swath_ramp_removal (flag), swath_mode_description, multilook_az_rg1, multilook_az_rg2, iono_height
* Added packing of additional attributes for ionosphere computation into GUNW
* fsspec is now required in environment due to burst processing.

## [0.2.3]

### Updated
* Explode footprints polygons
* Added support for using water mask in ionospheric correction computation

### Removed
* Python 3.8 Support

## [0.2.2]

### Added
* Provide prototype (internal) for burst analysis thanks to Forrest Williams and Joseph Kennedy (see PR #73)
* CLI (and API) can switch between burst and SLC ifg generation thanks to entry point magic (see PR #73 for details)
* Exposes a number of new corrections/ISCE2 processing options including: `ionosphere`, and `ESD threshold` arguments in CLI. Examples in README.
* Exposes `frame-id` parameter for fixed frame cropping. Discussion, references, and examples in README.
* Latitude aligned frames and their expected extents are added as geojson in repository as zip file.
* Pins ISCE2 version to 2.6.1 and numpy / scipy to previous versions (see environment.yml) - to be amended when newest ISCE2 build is sorted out
* Includes `frame_id` and `temporal_baseline_days` in json metadata for CMR handshake. The former is the fixed frame id and the latter is the number of days between images (will be multiple of 6).
* Added support to compute and embed solid earth tide correction layers into GUNW products (see PR #91) - reference and secondary have own groups
* Raises warning if there is at least 80% of water in the IFG area using Natural Earth Land mask.

## Fixed
* Ensures that when Solid Earth Tide or Ionosphere is added to GUNW, that the internal version attribute is updated from '1b' to '1c'
* Ensures that correct (i.e. enough) DEM extents are obtained for frame job submission
* Uses dem-stitcher 2.4.0 to resolve #89 - ensures only polygonal intersection of tiles
* Fix variable name error in localize_slc.py
* Removes dummy Solid Earth Tide variable from GUNW
* Ensures dates and time in GUNW name are derived from center of secondary and reference pass.

## Changed
* Metadata `intersection_geo` is changed to `gunw_geo`.
* Differentiates `gunw_geo` (and bounds) for DEM acquisition and `processing_geo` for ISCE2 for frame job submission.

## [0.2.1]

* Fixes write of start/stop sensing times due to changes in ASF Search v5.0.0 (see #79)

## [0.2.0]

### Added
* A prototype burst processing skeleton (non-functional)

### Changed
* Uses updated API dem-stitcher for square resolution cells and translation/resampling (>=2.2.0)
* Updates dataset (patch change) from 2.0.5 to 2.0.6
* Sort imports for updated files

### Fixed
* Uses dem-stitcher>=v2.3.0, which by default, fills in `glo-30` tiles that are missing over Armenia and Azerbaijan with the available `glo-90` tiles (upsampled).
* Uses dem-stitcher>=v2.3.1 to fix URLs for `glo-30` and `srtm_v3`

## [0.1.2]

### Fixed
* Sentinel-1 A/B `aux-cal` files are found at url: https://sar-mpc.eu/ipf-adf/aux_cal/
* Unpack `aux-cal` with python standard package `zipfile`
* Fix aux-cal bug (only S1A was being downloaded)

## [0.1.1]

### Fixed
* DEM bounds are rounded to the nearest integer to reflect ISCE convention and avoid geocoding artifacts.

## [0.1.0]

Initial release of the ARIA/JPL DockerizedTopsApp science processor, and [HyP3](https://hyp3-docs.asf.alaska.edu)
plugin, for generating an ARIA Sentinel-1 [Geocoded Unwrapped Interferogram](https://aria.jpl.nasa.gov/products/standard-displacement-products.html)
(GUNW) product from a collection of valid Sentinel-1 IW-mode Single Look Complex (SLC) scenes using [ISCE2](https://github.com/isce-framework/isce2).
