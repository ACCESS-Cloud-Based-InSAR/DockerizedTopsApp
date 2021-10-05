FROM continuumio/miniconda3

LABEL description="TopsApp Container"

# Build context must be from root of this repository!
# Because we enventuall run: COPY . /home/ops/DockerizedTopsApp

# Copying environment.yml separately ensures that changes to repo changes
# Won't affect Docker Cache step because if files copied are changed, then build
# Cannot be cached per
# https://docs.docker.com/develop/develop-images/dockerfile_best-practices/#leverage-build-cache
COPY environment.yml /home/ops/environment.yml

# Create the environment with mamba
RUN conda install mamba -n base -c conda-forge
RUN mamba env create -f /home/ops/environment.yml

# Ensure that environment is activated on startup
RUN echo "conda activate topsapp_env" >> ~/.bashrc

# Copy repo before pip install
COPY . /home/ops/DockerizedTopsApp

# Install repository with pip; must be better way
# Just using pip install to base not env
RUN /bin/bash -c "/opt/conda/envs/topsapp_env/bin/pip install /home/ops/DockerizedTopsApp"

# set entrypoint
WORKDIR /home/ops
ENTRYPOINT ["/home/ops/DockerizedTopsApp/isce2_topsapp/etc/entrypoint.sh"]
CMD ["-h"]
