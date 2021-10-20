FROM condaforge/mambaforge:latest

LABEL description="TopsApp Container"

# run commands in a bash login shell
SHELL ["/bin/bash", "-l", "-c"]

# Create non-root user/group with default inputs
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG USERNAME=iscer

ENV UID $USER_ID
ENV GID $GROUP_ID
ENV UNAME $USERNAME

RUN addgroup --gid $GID $UNAME
RUN adduser --disabled-password --gecos '' --uid $UID --gid $GID $UNAME

# Build context must be from root of this repository
# Ensures we cached mamba install per
# https://docs.docker.com/develop/develop-images/dockerfile_best-practices/#leverage-build-cache
COPY environment.yml /home/ops/environment.yml
RUN chown $UID:$GID /home/ops/environment.yml

# Create the environment with mamba
RUN mamba env create -f /home/ops/environment.yml && \
    conda clean -afy

# Build context must be from root of this repository
COPY . /home/ops/DockerizedTopsApp
RUN chown -R $UID:$GID /home/ops/DockerizedTopsApp

# Ensure that environment is activated on startup
RUN echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.profile && \
    echo "conda activate topsapp_env" >> ~/.profile

# Install repository with pip
RUN python -m pip install --no-cache-dir /home/ops/DockerizedTopsApp

# Switch to non-root user
USER $UNAME

# set entrypoint
WORKDIR /home/ops
ENTRYPOINT ["/home/ops/DockerizedTopsApp/isce2_topsapp/etc/entrypoint.sh"]
CMD ["-h"]