FROM condaforge/mambaforge:latest

LABEL description="TopsApp Container"

ARG DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=true

# Install libgl1-mesa-glx unzip vim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1-mesa-glx unzip vim curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# run commands in a bash login shell
SHELL ["/bin/bash", "-l", "-c"]

# Create non-root user/group with default inputs
ARG UID=1000
ARG GID=1000

RUN groupadd -g "${GID}" --system iscer && \
    useradd -l -u "${UID}" -g "${GID}" --system -d /home/ops -m  -s /bin/bash iscer && \
    chown -R iscer:iscer /opt

# Switch to non-root user
USER iscer
WORKDIR /home/ops

# Ensures we cached mamba install per
# https://docs.docker.com/develop/develop-images/dockerfile_best-practices/#leverage-build-cache
COPY --chown=iscer:iscer environment.yml /home/ops/environment.yml
COPY --chown=iscer:iscer . /home/ops/DockerizedTopsApp

# Create the environment with mamba
RUN mamba env create -f /home/ops/DockerizedTopsApp/environment.yml && \
    conda clean -afy

# TODO: Remove this when ISCE2 releases S1D Fixes
RUN TARGET_DIR=$(conda run -n topsapp_env python -c "import isce; import os; print(os.path.dirname(isce.__file__))") && \
    curl -sSL -o "${TARGET_DIR}/components/isceobj/Sensor/TOPS/Sentinel1.py" \
    https://raw.githubusercontent.com/isce-framework/isce2/7bd57893ed9ae2d7ac0f7dd0e06625e337b0b993/components/isceobj/Sensor/TOPS/Sentinel1.py

# Ensure that environment is activated on startup
RUN echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.profile && \
    echo "conda activate topsapp_env" >> ~/.profile

# Install repository with pip
RUN python -m pip install --no-cache-dir /home/ops/DockerizedTopsApp

# set entrypoint
ENTRYPOINT ["/home/ops/DockerizedTopsApp/isce2_topsapp/etc/entrypoint.sh"]
CMD ["-h"]
