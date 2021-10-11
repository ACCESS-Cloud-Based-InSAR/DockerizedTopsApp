FROM condaforge/mambaforge:latest

LABEL description="TopsApp Container"

<<<<<<< HEAD
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
=======
# run commands in a bash login shell
SHELL ["/bin/bash", "-l", "-c"]

# Build context must be from root of this repository
COPY . /home/ops/DockerizedTopsApp

# Create the environment with mamba
RUN mamba env create -f /home/ops/DockerizedTopsApp/environment.yml && \
    conda clean -afy
>>>>>>> fb95733cc5e965312c57fa0dee3b82932593ba91

# Ensure that environment is activated on startup
RUN echo ". /opt/conda/etc/profile.d/conda.sh" > ~/.profile && \
    echo "conda activate topsapp_env" >> ~/.profile

<<<<<<< HEAD
# Copy repo before pip install
COPY . /home/ops/DockerizedTopsApp

# Install repository with pip; must be better way
# Just using pip install to base not env
RUN /bin/bash -c "/opt/conda/envs/topsapp_env/bin/pip install /home/ops/DockerizedTopsApp"
=======
# Install repository with pip
RUN python -m pip install --no-cache-dir /home/ops/DockerizedTopsApp
>>>>>>> fb95733cc5e965312c57fa0dee3b82932593ba91

# set entrypoint
WORKDIR /home/ops
ENTRYPOINT ["/home/ops/DockerizedTopsApp/isce2_topsapp/etc/entrypoint.sh"]
CMD ["-h"]
