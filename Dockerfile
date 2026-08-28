FROM ghcr.io/prefix-dev/pixi:0.73.0-noble

LABEL description="TopsApp Container"

ARG DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=true

# git is required by setuptools_scm to derive the package version
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 unzip vim git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Create non-root user/group with default inputs
ARG UID=1000
ARG GID=1000

# noble ships a stock ubuntu user at 1000, which collides with UID/GID below
RUN userdel -r ubuntu && \
    groupadd -g "${GID}" --system iscer && \
    useradd -l -u "${UID}" -g "${GID}" --system -d /home/ops -m -s /bin/bash iscer

# Switch to non-root user
USER iscer
WORKDIR /home/ops/DockerizedTopsApp

# Ensures we cache the pixi solve per
# https://docs.docker.com/develop/develop-images/dockerfile_best-practices/#leverage-build-cache
COPY --chown=iscer:iscer pyproject.toml pixi.lock /home/ops/DockerizedTopsApp/

# Create the environment from the lock file
RUN pixi install --locked && \
    pixi clean cache --yes

COPY --chown=iscer:iscer . /home/ops/DockerizedTopsApp

# Install repository into the pixi environment
RUN pixi run --frozen python -m pip install --no-deps --no-cache-dir .

# set entrypoint
ENTRYPOINT ["/home/ops/DockerizedTopsApp/isce2_topsapp/etc/entrypoint.sh"]
CMD ["-h"]
