FROM continuumio/miniconda3

LABEL description="TopsApp Container"

# Build context must be from root of this repository
COPY . /home/ops/DockerizedTopsApp
# Must have .env in repository
COPY .env /home/ops/.env

# Create the environment with mamba
RUN conda install mamba -n base -c conda-forge
RUN mamba env create -f /home/ops/DockerizedTopsApp/environment.yaml

# Ensure that environment is activated on startup
RUN echo "conda activate topsapp_env" >> ~/.bashrc

# Install repository with pip
RUN /bin/bash -c "pip install /home/ops/DockerizedTopsApp"

# set entrypoint
WORKDIR /home/ops
CMD ["/bin/bash"]