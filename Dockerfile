FROM condaforge/mambaforge:latest

LABEL description="TopsApp Container"

# run commands in a bash login shell
SHELL ["/bin/bash", "-l", "-c"]

# Build context must be from root of this repository
COPY . /home/ops/DockerizedTopsApp

# Create the environment with mamba
RUN mamba env create -f /home/ops/DockerizedTopsApp/environment.yml && \
    conda clean -afy

# Ensure that environment is activated on startup
RUN echo ". /opt/conda/etc/profile.d/conda.sh" > ~/.profile && \
    echo "conda activate topsapp_env" >> ~/.profile

# Install repository with pip
RUN python -m pip install --no-cache-dir /home/ops/DockerizedTopsApp

# set entrypoint
WORKDIR /home/ops
ENTRYPOINT ["/home/ops/DockerizedTopsApp/isce2_topsapp/etc/entrypoint.sh"]
CMD ["-h"]
