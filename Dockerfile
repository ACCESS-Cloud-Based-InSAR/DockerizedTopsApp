FROM continuumio/miniconda3

LABEL description="TopsApp Container"

# Build context must be from root of this repository
COPY . /home/ops/DockerizedTopsApp

# Create the environment with mamba
RUN conda install mamba -n base -c conda-forge
RUN mamba env create -f /home/ops/DockerizedTopsApp/environment.yml

# Ensure that environment is activated on startup
RUN echo "conda activate topsapp_env" >> ~/.bashrc

# Install repository with pip; must be better way
# Just using pip install to base not env
RUN /bin/bash -c "/opt/conda/envs/topsapp_env/bin/pip install /home/ops/DockerizedTopsApp"

# set entrypoint
WORKDIR /home/ops
ENTRYPOINT ["/home/ops/DockerizedTopsApp/isce2_topsapp/etc/entrypoint.sh"]
CMD ["-h"]
