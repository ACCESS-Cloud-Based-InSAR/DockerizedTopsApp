FROM continuumio/miniconda3

LABEL description="TopsApp Container"

# Build context must be from root of this repository
COPY . /home/ops/DockerizedTopsApp

# Create the environment:
RUN conda install mamba -n base -c conda-forge
RUN mamba env create -f /home/ops/hyp3-topsApp/environment.yaml

# Ensure that environment is activated on startup
RUN echo "conda activate topsapp_env" >> ~/.bashrc

# set entrypoint
WORKDIR /home/ops
CMD ["/bin/bash"]