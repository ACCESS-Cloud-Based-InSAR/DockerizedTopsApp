# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4]

### Added
* Provide prototype (internal) for burst analysis thanks to Forrest Williams and Joseph Kennedy (see PR #73)
* CLI (and API) can switch between burst and SLC ifg generation thanks to entry point magic (see PR #73 for details)
* Exposes Ionosphere correction in CLI (and API)
* Exposes ESD and ESD threshold in CLI (and API)


## [0.1.3]

### Changed
* Uses updated API dem-stitcher for square resolution cells and translation/resampling (>=2.2.0)
* Updates dataset (patch change) from 2.0.5 to 2.0.6
* Sort imports for updated files

### Fixed
* Uses dem-stitcher>=v2.3.0, which by default, fills in `glo-30` tiles that are missing over Armenia and Azerbaijan with the available `glo-90` tiles (upsampled).

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

