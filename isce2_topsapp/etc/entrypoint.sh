#!/bin/bash --login
set -e
conda activate topsapp_env
exec python -um isce_topsapp "$@"
