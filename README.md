# DockerizedTopsApp (aka ISCE2 TopsApp Hyp3-Plugin)

This repository represents a dockerized science processor for generating an ARIA Sentinel-1 [Geocoded Unwrapped Interferogram](https://aria.jpl.nasa.gov/products/standard-displacement-products.html) (GUNW) product from a collection of valid Sentinel-1 IW-mode Single Look Complex (SLC) IDs across a date pair using [ISCE2](https://github.com/isce-framework/isce2). The GUNW is a NISAR beta-product. The initial development of the GUNW was done under the Getting Ready for NISAR initiative and a collection of related ARIA-funded projects. This work has continued under the Project Enabling Cloud-Based InSAR Science for an Exploding NASA InSAR Data Archive (ACCESS19-0023) funded under the ACCESS program.

This processor plugs into the [HyP3](https://hyp3-docs.asf.alaska.edu/v2-transition/) platform and therefore can spawn processing at scale from an API. All of the necessary datasets required for processing are determined from the input SLC IDS and then downloaded from public APIs. Thus, this repository accomplishes two goals:

1. Integrates into [Hyp3](https://github.com/ASFHyP3/hyp3) platform so that this processing unit can be called directly from an API or the [hyp3-sdk](https://github.com/ASFHyP3/hyp3-sdk) to generate ARIA GUNWs.
2. Fashions a command line interface (CLI) for generating the GUNWs for local study and research.

We note all the input datasets are publicly available using a NASA Earthdata account. This codebase can be run locally both within a conda environment or within a docker container. To generate a GUNW, one needs to only specify valid SLC IDs that span a repeat-pass for a specific Sentinel-1 viewing geometry. The `main` branch of this repository is the stable release deployed via the HyP3 platform and can be accessed via the appropriate API.

## Background

[TopsApp](https://github.com/isce-framework/isce2-docs/blob/master/Notebooks/UNAVCO_2020/TOPS/topsApp.ipynb) is a an ISCE2 InSAR workflow for Sentinel-1 constellation SLCs corresponding to a repeat-pass date pair. ISCE2 TopsApp generates numerous SAR analysis ready products including a geocoded unwrapped interferogram. The ARIA GUNW product packages the ISCE2 analysis ready data products into a NISAR netcdf file as discussed [here](​https://asf.alaska.edu/data-sets/derived-data-sets/sentinel-1-interferograms/​). The ARIA project has generated numerous GUNWS over numerous Sentinel-1 tracks and for numerous date pairs ([here](https://search.asf.alaska.edu/#/?dataset=SENTINEL-1%20INTERFEROGRAM%20(BETA)&zoom=9.447&center=-117.753,33.588&polygon=POINT(-118.1724%2034.1996)&resultsLoaded=true&granule=S1-GUNW-A-R-137-tops-20210809_20210728-015757-34441N_32227N-PP-81c7-v2_0_4-amplitude) are some GUNWs over JPL). These products were first generated using the topsApp Product Generation Executable (PGE) written by [Mohammed Karim](https://github.com/mkarim2017) and [David Bekaert](https://github.com/dbekaert) in the [ariamh repo](https://github.com/aria-jpl/ariamh). The repo was later reorganized [here](https://github.com/aria-jpl/topsApp_pge). The current processor (also dubbed a plugin) is adapted from these two repositories adding necessary localization of datasets required so that this processor can be called via an API.


# Running Locally in Conda

## Installation

1. Clone this repo `git clone https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp.git`
2. Navigate with your terminal to the repo.
3. Create a new environment and install requirements using `conda env update --file environment.yml` (or use [`mamba`](https://github.com/mamba-org/mamba) to speed install up)
4. Install the package from cloned repo using `python -m pip install -e .`

## Additional setup

1. Ensure that your `~/.netrc` file has:
    ```
    machine urs.earthdata.nasa.gov
        login <username>
        password <password>
    ```
    The `username`/`password` are the appropriate Earthdata Login credentials that are used to access NASA data. This file is necessary for downloading the Sentinel-1 orbit files from the ASF DAAC. Additionally, the [`requests`](https://docs.python-requests.org/en/latest/) library automatically uses credentials stored in the `~/.netrc` for authentification when none are supplied.


## Generate a GUNW

Make sure you have `~/.netrc`. Run the following command:

```
isce2_topsapp --reference-scenes S1B_IW_SLC__1SDV_20210723T014947_20210723T015014_027915_0354B4_B3A9 \
              --secondary-scenes S1B_IW_SLC__1SDV_20210711T014922_20210711T014949_027740_034F80_859D \
                                 S1B_IW_SLC__1SDV_20210711T014947_20210711T015013_027740_034F80_D404 \
                                 S1B_IW_SLC__1SDV_20210711T015011_20210711T015038_027740_034F80_376C
```
Add `> topsapp_img.out 2> topsapp_img.err` to avoid unnecessary output to your terminal and record the stdout and stderr as files.
This is reflected in the [`sample_run.sh`](sample_run.sh).

To be even more explicity, you can use [`tee`](https://en.wikipedia.org/wiki/Tee_(command)) to record output to both including `> >(tee -a topsapp_img.out) 2> >(tee -a topsapp_img.err >&2)`.

## Customizations

### Estimating Ionospheric Phase Delay and ESD

This example shows how to obtain a layer with ionsopheric phase delay. The SLCs are over the Arabian peninusula where the ionosphere can be seen:

```
isce2_topsapp --reference-scenes S1B_IW_SLC__1SDV_20171117T145926_20171117T145953_008323_00EBAB_AFB8 \
              --secondary-scenes S1A_IW_SLC__1SDV_20171111T150004_20171111T150032_019219_0208AF_EE89 \
              --estimate-ionosphere-delay True \
              --esd-coherence-threshold .5 \
              > topsapp_img.out 2> topsapp_img.err
```
Not including `--esd-coherence-threshold` means no ESD correction will be applied. The ESD threshold refers to a coherence value and therefore must be in $[0, 1]$.

### Apply Solid Earth Tide Correction

```
isce2_topsapp --reference-scenes S1B_IW_SLC__1SDV_20210723T014947_20210723T015014_027915_0354B4_B3A9 \
              --secondary-scenes S1B_IW_SLC__1SDV_20210711T014922_20210711T014949_027740_034F80_859D \
                                 S1B_IW_SLC__1SDV_20210711T014947_20210711T015013_027740_034F80_D404 \
                                 S1B_IW_SLC__1SDV_20210711T015011_20210711T015038_027740_034F80_376C \
              --compute-solid-earth-tide True \
              > topsapp_img_set.out 2> topsapp_img_set.err
```

### Using "fixed frames" (experimental)

Sentinel-1 Frames are not constant over passes. We generate fixed frames [here](https://github.com/ACCESS-Cloud-Based-InSAR/s1-frame-generation) and enumerate interferograms using this [repo](https://github.com/ACCESS-Cloud-Based-InSAR/s1-frame-enumerator). This is highly experimental. We then ensure ISCE processes only over the frame. The key is overlap. We provide some examples of the additional options (you will need to run this in *two* separate directories because ISCE2 outputs are organized with respect to the working directory of the processing). For one frame over CA:
```
isce2_topsapp --reference-scenes S1A_IW_SLC__1SDV_20230125T135954_20230125T140021_046941_05A132_D35C \
                                 S1A_IW_SLC__1SDV_20230125T140019_20230125T140046_046941_05A132_82DF \
              --secondary-scenes S1A_IW_SLC__1SDV_20221220T135956_20221220T140023_046416_058F77_B248 \
                                 S1A_IW_SLC__1SDV_20221220T140020_20221220T140047_046416_058F77_5213 \
              --frame-id 22438 \
              > topsapp_img_f22438.out 2> topsapp_img_f22438.err
```
and an overlapping frame:
```
isce2_topsapp --reference-scenes S1A_IW_SLC__1SDV_20230125T140019_20230125T140046_046941_05A132_82DF \
                                 S1A_IW_SLC__1SDV_20230125T140044_20230125T140111_046941_05A132_59E7 \
              --secondary-scenes S1A_IW_SLC__1SDV_20221220T140020_20221220T140047_046416_058F77_5213 \
                                 S1A_IW_SLC__1SDV_20221220T140045_20221220T140112_046416_058F77_7692 \
              --frame-id 22439 \
              > topsapp_img_f22439.out 2> topsapp_img_f22439.err
```

# Running with Docker (locally or on a server)

1. When running locally with root privileges (i.e. at your local workstation), build the docker image using:
    ```
   docker build -f Dockerfile -t topsapp_img .
   ```
   In a managed cluster/server without root privileges, build the docker with arguments for your user's `UID` and `GID`:
    ```
   docker build -f Dockerfile -t topsapp_img --build-arg UID=$(id -u) --build-arg GID=$(id -g) .
   ```

3. Create a directory to mount the data files so you can inspect them outside of your docker container. Call it `topsapp_data`. Navigate to it. Copy the `sample_run.sh` in this directory, modifying it to add your Earthdata username and password e.g.

    ```
    isce2_topsapp --username <username> \
                  --password <password> \
                  --reference-scenes S1B_IW_SLC__1SDV_20210723T014947_20210723T015014_027915_0354B4_B3A9 \
                  --secondary-scenes S1B_IW_SLC__1SDV_20210711T014922_20210711T014949_027740_034F80_859D \
                                     S1B_IW_SLC__1SDV_20210711T014947_20210711T015013_027740_034F80_D404 \
                                     S1B_IW_SLC__1SDV_20210711T015011_20210711T015038_027740_034F80_376C \
                  > topsapp_img.out 2> topsapp_img.err
   ```

4. Take a look around a docker container, mounting a volume built from the image with:

   ```docker run -ti -v $PWD:/home/ops/topsapp_data --entrypoint /bin/bash topsapp_img```

   You can even run jupyter notebooks within the docker container mirroring ports with `-p 1313:1313`.

5. Run the topsapp process within a docker container:

   ```cd /home/ops/topsapp_data && conda activate topsapp_env && source /home/ops/topsapp_data/sample_run.sh```

## Expedient Docker Test for GUNW Generation

Create a new directory (for all the intermediate files) and navigate to it.

```
docker run -ti -v $PWD:/home/ops/topsapp_data topsapp_img \
               --reference-scenes S1B_IW_SLC__1SDV_20210723T014947_20210723T015014_027915_0354B4_B3A9 \
               --secondary-scenes S1B_IW_SLC__1SDV_20210711T014922_20210711T014949_027740_034F80_859D \
                                    S1B_IW_SLC__1SDV_20210711T014947_20210711T015013_027740_034F80_D404 \
                                    S1B_IW_SLC__1SDV_20210711T015011_20210711T015038_027740_034F80_376C \
               --username <username>
               --password <password>
```
where the `username`/`password` are the Earthdata credentials for accessing NASA data. We note the command line magic of the above is taken care of the `isce2_topsapp/etc/entrypoint.sh` (written by Joe Kennedy) which automatically runs certain bash commands on startup of the container, i.e. the run commands also calls the `isce2_topsapp` command line function as can be seen [here](isce2_topsapp/etc/entrypoint.sh).

# Build Issues

ISCE2, gdal, and xarray are hard to balance. Ideally, we would have a dependabot to increment packages and integration tests to make sure datasets are generated correctly with each update. Unfortunately, this is not currently the case. So, we are including some snippets (credit to Joseph Kennedy) for determining where packages might fail. We have some caps in our environment.yml file. This is how we find them. Sometimes even with our rather minimal integration tests and builds, in 24 hours, a new package can entirely throw something awry with respect to builds.

The easiest way to see what was the *last* working build, check out the docker [images](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/pkgs/container/dockerizedtopsapp) for the last build. `latest` refers to the latest production build on `main`. `test` refers to the last build on `dev`. But each merge to `dev` gets an image that is recorded.

1. Click one of the images and it will tell you how to download an image into docker e.g. `docker pull ghcr.io/access-cloud-based-insar/dockerizedtopsapp:0.2.2.dev148_gab75888`.
2. Load the image and get into interactive mode e.g. `docker run --entrypoint /usr/bin/bash  -it --rm ghcr.io/access-cloud-based-insar/dockerizedtopsapp:0.2.2.dev136_ga2d5389 -l`
3. Check the packages `conda list | grep xarray`

## FAQ

1. The docker build is taking a long time.

    *Answer*: Make sure the time is spent with `conda/mamba` not copying data files. The `.dockerignore` file should ignore ISCE2 data files (if you are running some examples within this repo directory, there will be GBs of intermediate files). It's crucial you don't include unnecessary ISCE2 intermediate files into the Docker image as this will bloat it.

2. Need to install additional packages such as vim?

   *Answer*: Login as root user to the container and install the additional packages.

   Make sure you know the container_id (e.g. ```docker ps -a ```). Then do the following steps:
   ```
   $ docker start <container_id>
   $ docker exec --user root -ti <container_id> /bin/bash
   $ conda activate topsapp_env
   $ conda install <package>
   $ exit
   ```
   Return to the terminal inside the container as non-root user: ```docker exec -ti <container_id> /bin/bash```

