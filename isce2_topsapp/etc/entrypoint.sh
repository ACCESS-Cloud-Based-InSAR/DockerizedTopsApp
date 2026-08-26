#!/bin/bash
set -e
cd /home/ops/DockerizedTopsApp
exec pixi run --frozen python -um isce2_topsapp "$@"
