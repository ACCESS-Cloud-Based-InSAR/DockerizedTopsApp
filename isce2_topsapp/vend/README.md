# Vendored ISCE2 modules for the DockerizedTopsApp HyP3 plugin

This directory contains modules needed for the DockerizedTopsApp HyP3 plugin that couldn't
be easily incorporated from a package manager or installed appropriately.

## Contents

* `stageS1_earthdata.py` -- The module is required stage ASF data virtually for TOPS processing
  and is included in the [ISCE2 source code](https://github.com/isce-framework/isce2/blob/v2.6.0/contrib/stack/topsStack/stageS1_earthdata.py)
  but not distributed as part of the package. The version located in this directory corresponds
  to ISCE release [`v2.6.0`](https://github.com/isce-framework/isce2/releases/tag/v2.6.0).

## Applied patches

Changes, as listed in `CHANGES.diff`, were done to facilitate better packaging and distribution
of these modules, as well as make them easier to integrate into this codebase.
