# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### Added

## [0.2.2]

### Added
* Provide prototype (internal) for burst analysis thanks to Forrest Williams and Joseph Kennedy (see PR #73)
* CLI (and API) can switch between burst and SLC ifg generation thanks to entry point magic (see PR #73 for details)
* Exposes a number of new corrections/ISCE2 processing options including: `ionosphere`, and `ESD threshold` arguments in CLI. Examples in README.
* Exposes `frame-id` parameter for fixed frame cropping. Discussion, references, and examples in README.
* Latitude aligned frames and their expected extents are added as geojson in repository as zip file.
* Pins ISCE2 version to 2.6.1 and numpy / scipy to previous versions (see environment.yml) - to be amended when newest ISCE2 build is sorted out
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

