FROM continuumio/miniconda3

LABEL description="Alos2App PGE Container"

# Build context must be from root of this repository
COPY . /home/ops/hyp3-topsApp

# Create the environment:
RUN conda env create -f /home/ops/hyp3-topsApp/environment.yaml

# Ensure that environment is activated on startup
RUN echo "conda activate topsapp_env && python -m ipykernel install --user" >> ~/.bashrc

# set entrypoint
WORKDIR /home/ops
CMD ["/bin/bash"]