# DockerizedTopsApp (aka ISCE2 TopsApp Hyp3-Plugin)

This repository represents a dockerized science processor for generating an ARIA Sentinel-1 [Geocoded Unwrapped Interferogram](https://asf.alaska.edu/data-sets/derived-data-sets/sentinel-1-interferograms/) (ARIA-S1-GUNW) product from a collection of valid Sentinel-1 IW-mode Single Look Complex (SLC) IDs across a date pair using [ISCE2](https://github.com/isce-framework/isce2). The ARIA-S1-GUNW (or simply a GUNW) is an official NASA product. The initial development of the GUNW was done under the Getting Ready for NISAR initiative and a collection of related ARIA-funded projects. This work has continued under the Project Enabling Cloud-Based InSAR Science for an Exploding NASA InSAR Data Archive (ACCESS19-0023) funded under the ACCESS program. A description of the product can be found here: https://aria.jpl.nasa.gov/products/standard-displacement-products.html

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

    machine dataspace.copernicus.eu
        login <username>
        password <password>
    ```
    The first `username`/`password` pair are the appropriate Earthdata Login credentials that are used to access NASA data. The second pair are your credentials for the [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu). This file is necessary for downloading the Sentinel-1 files, and auxiliary data. Additionally, the [`requests`](https://docs.python-requests.org/en/latest/) library automatically uses credentials stored in the `~/.netrc` for authentification when none are supplied.

## Generate an ARIA-S1-GUNW

Make sure you have `~/.netrc` as described above. Run the following command:

```
isce2_topsapp --reference-scenes S1A_IW_SLC__1SDV_20220212T222803_20220212T222830_041886_04FCA3_2B3E \
                                 S1A_IW_SLC__1SDV_20220212T222828_20220212T222855_041886_04FCA3_A3E2  \
              --secondary-scenes S1A_IW_SLC__1SDV_20220131T222803_20220131T222830_041711_04F690_8F5F \
                                 S1A_IW_SLC__1SDV_20220131T222828_20220131T222855_041711_04F690_28D7  \
              --frame-id 25502
```
Add `> topsapp_img.out 2> topsapp_img.err` to avoid unnecessary output to your terminal and record the stdout and stderr as files.
This is reflected in the [`sample_run.sh`](sample_run.sh).

To be even more explicity, you can use [`tee`](https://en.wikipedia.org/wiki/Tee_(command)) to record output to both including `> >(tee -a topsapp_img.out) 2> >(tee -a topsapp_img.err >&2)`.

## What makes an ARIA-S1-GUNW Product *standard*?

Each ARIA-S1-GUNW at the ASF that ensures that down-stream analysis by [ARIA-Tools](https://github.com/aria-tools/ARIA-tools) and [Mintpy](https://github.com/insarlab/MintPy) is done consistently and reproducibly. There are a number of exposed parameters in this plugin that we require to be set in a certain manner for a product to be considered "standard". We now discuss the standard parameters with respect to this plugin.

Since v3+, in addition to reference and secondary scenes, a `frame-id` must be supplied for a *standard* product to be generated. This effectively restricts processing and the resulting product to be within this frame (technically, all bursts within the frame are included in the standard product). The geojson of spatially-fixed frames with their ids can be downloaded [here](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/blob/dev/isce2_topsapp/data/s1_frames_latitude_aligned.geojson.zip). These are derived from ESA's burst [map](https://sar-mpc.eu/test-data-sets/). More information about finding SLC pairs and their corresponding pairs can be found [here](https://github.com/ACCESS-Cloud-Based-InSAR/s1-frame-enumerator) and the generation of our spatially fixed-frames is discussed [here](https://github.com/ACCESS-Cloud-Based-InSAR/s1-frame-generation).

All standard products have the following layers:
+ Data Layers (0.00083333333 deg or ~90 m at the equator)
  + Unwrapped phase
  + Coherence
  + Connected compenents
  + Unfiltered coherence - *new* in version 3❗
  + InSAR amplitude
+ Correction Layers
   + Ionosphere (0.00916 deg or ~1 km at the equator) - *new* in version 3❗
   + Solid earth tide (.1 deg or ~11 km at the equator) - *new* in version 3❗
   + Tropo correction layers if HRRR available (see [RAiDER](https://github.com/dbekaert/RAiDER)) - new in version 3❗
+ Geometry Layers (.1 deg or ~11 km)
   + Incidence angle
   + Azimuth angle
   + Parallel baseline
   + Perpendicular baseline
   + Lat/lon grids

Again, tropo corrections are controlled via a separate step-function so is not included above. The repository is [here](https://github.com/dbekaert/RAiDER). Turning off certain layers or adding available layers using the CLI arguments are permissible but will produce *custom* products (indicated with a prefix `S1-GUNW_CUSTOM...`). The parameters are often simply exposing certain topsApp parameters discussed [here](https://github.com/isce-framework/isce2/blob/main/applications/topsApp.py). Our template for topsapp that is utilized for ISCE is found [here](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/blob/dev/isce2_topsapp/templates/topsapp_template.xml).

The command line string and relevant plugin version used to generate every product is included in the product itself and can be used to reproduce a product. These are attributes in the top level netcdf group.

We note that the ionosphere correction layer is the (hard) work of [Marin Govorcin](https://github.com/mgovorcin) and David Bekaert, which utilizes ISCE2 in a creative fashion. Users should refer to [this file](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/blob/dev/isce2_topsapp/iono_proc.py) for the process. 

Below indicates all available arguments for product generation and parameters required for *standard product* generation (again, for a given pairing and frame, one must use the enumeration of pairs described [here](https://github.com/ACCESS-Cloud-Based-InSAR/s1-frame-enumerator)). Use `isce2_topsapp --help` for more information of available arguments.

```
isce2_topsapp --reference-scenes S1A_IW_SLC__1SDV_20220212T222803_20220212T222830_041886_04FCA3_2B3E \
                                 S1A_IW_SLC__1SDV_20220212T222828_20220212T222855_041886_04FCA3_A3E2  \
              --secondary-scenes S1A_IW_SLC__1SDV_20220131T222803_20220131T222830_041711_04F690_8F5F \
                                 S1A_IW_SLC__1SDV_20220131T222828_20220131T222855_041711_04F690_28D7  \
              --frame-id 25502 # latitude aligned ARIA spatially fixed frame\
              --estimate-ionosphere-delay True # ionosphere correction layers\
              --esd-coherence-threshold -1. # if -1, ESD is not used; else should be a value in (0, 1)\
              --compute_solid_earth_tide True \
              --goldstein-filter-power 0.5 # the power of the patch FFT filter used in the Goldstein filter\
              --output-resolution 90 # either 30 or 90 meters\
              --unfiltered-coherence True # this adds an unfiltered coherence layer\
              --dense-offsets False # adds layers that compute patch wise correlation measurement done in range and azimuth which are helpful after significant surface changes\
```
or as a json:
```
{
  "reference_scenes": [
    "S1A_IW_SLC__1SDV_20220212T222803_20220212T222830_041886_04FCA3_2B3E",
    "S1A_IW_SLC__1SDV_20220212T222828_20220212T222855_041886_04FCA3_A3E2"
  ],
  "secondary_scenes": [
    "S1A_IW_SLC__1SDV_20220131T222803_20220131T222830_041711_04F690_8F5F",
    "S1A_IW_SLC__1SDV_20220131T222828_20220131T222855_041711_04F690_28D7"
  ],
  "frame_id": 25502,
  "estimate_ionosphere_delay": true,
  "compute_solid_earth_tide": true,
  "output_resolution": 90,
  "unfiltered_coherence": true,
  "goldstein_filter_power": 0.5,
  "dense_offsets": false,
  "wrapped_phase_layer": false,
  "esd_coherence_threshold": -1.0
}
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
    isce2_topsapp --reference-scenes S1A_IW_SLC__1SDV_20220212T222803_20220212T222830_041886_04FCA3_2B3E \
                                 S1A_IW_SLC__1SDV_20220212T222828_20220212T222855_041886_04FCA3_A3E2  \
                  --secondary-scenes S1A_IW_SLC__1SDV_20220131T222803_20220131T222830_041711_04F690_8F5F \
                                 S1A_IW_SLC__1SDV_20220131T222828_20220131T222855_041711_04F690_28D7  \
                  --frame-id 25502 \
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
               --reference-scenes S1A_IW_SLC__1SDV_20220212T222803_20220212T222830_041886_04FCA3_2B3E \
                                 S1A_IW_SLC__1SDV_20220212T222828_20220212T222855_041886_04FCA3_A3E2  \
               --secondary-scenes S1A_IW_SLC__1SDV_20220131T222803_20220131T222830_041711_04F690_8F5F \
                                 S1A_IW_SLC__1SDV_20220131T222828_20220131T222855_041711_04F690_28D7  \
               --frame-id 25502 \
               --username <username>
               --password <password>
               --esa-username <esa-username> \
               --esa-password <esa-password> \
```
where the `username`/`password` are the Earthdata credentials for accessing NASA data. We note the command line magic of the above is taken care of the `isce2_topsapp/etc/entrypoint.sh` (written by Joe Kennedy) which automatically runs certain bash commands on startup of the container, i.e. the run commands also calls the `isce2_topsapp` command line function as can be seen [here](isce2_topsapp/etc/entrypoint.sh).

# Build Issues

ISCE2, gdal, and xarray are hard to balance. Ideally, we would have a dependabot to increment packages and integration tests to make sure datasets are generated correctly with each update. Unfortunately, this is not currently the case. So, we are including some snippets (credit to Joseph Kennedy) for determining where packages might fail. We have some caps in our environment.yml file. This is how we find them. Sometimes even with our rather minimal integration tests and builds, in 24 hours, a new package can entirely throw something awry with respect to builds.

The easiest way to see what was the *last* working build, check out the docker [images](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/pkgs/container/dockerizedtopsapp) for the last build. `latest` refers to the latest production build on `main`. `test` refers to the last build on `dev`. But each merge to `dev` gets an image that is recorded.

1. Click one of the images and it will tell you how to download an image into docker e.g. `docker pull ghcr.io/access-cloud-based-insar/dockerizedtopsapp:0.2.2.dev148_gab75888`.
2. Load the image and get into interactive mode e.g. `docker run --entrypoint /usr/bin/bash  -it --rm ghcr.io/access-cloud-based-insar/dockerizedtopsapp:0.2.2.dev136_ga2d5389 -l`
3. Check the packages `conda list | grep xarray`

# Contribution Instructions

This is an open-source plugin and we welcome contributions. Because we use this plugin for producing publicly available datasets, there is some additional tests and requirements for any new features to be integrated.

## Installation for Development


1. Clone or fork this repo. If you are a member of ACCESS or working on new features of this plugin, ask to become a member of this Github organization. The integration tests will be easier to run if you are pushing to branches of this repository as opposed to a fork (require organization secrets). This will ensure new features are more quickly integrated particularly into hyp3. Otherwise, please add secrets to your repository as indicate below.
2. Navigate with your terminal to the repo.
3. Create a new environment and install requirements using `conda env update --file environment.yml`
4. Activate the environment: `conda activate topsapp_env`
5. Install the package from cloned repo using `python -m pip install -e .`
6. Create a new branch with your feature.

**Note**: because forked repositories do not have access to the repositories secrets, you will have to add secrets to your repository. You will need to add your Earthdata username and password to the secrets as:

```
EARTHDATA_USERNAME=...
EARTHDATA_PASSWORD=...
```

## Tests

There are some integration tests. They are to make sure the wrapping part of the plugin, e.g. downloading metadata, a simulated CMR handshake, and packaging, occur as expected. However, the plugin takes about 1.5 to 3 hours (depending on the number of corrections requested) to generate a final GUNW. Therefore, these integration are *not* sufficient to permit merging into main. Until we have a complete end-to-end test of the workflow, any new feature cannot be integrated. As a first step, it is imperative to share the output of a new feature (i.e. the GUNW netcdf file). This is important because the integration tests do not check that ISCE2 successfully ran nor did the complex processing scripts. There are a lot of large libraries that need to be built and run successfully before this can be integrated. The CI/CD below ensures correct building of the python enviroment and Docker image. However, there can be subsequent errors in say ISCE2 even if the environment was built correctly.

## Hyp3 and Cloud Submission

There are two branches: `dev` and `main`. The former is the "test" branch and the later is the "production" branch. When submitting jobs to Hyp3 there are two job types related to `INSAR_ISCE_TEST` and `INSAR_ISCE`. The former corresponds to the `dev` branch and the latter to `main`. This allows us to test the plugin *in the cloud* incrementally before transitioning new features to production. This is a design feature of Hyp3 (thanks, Joseph Kennedy!). Since end-to-end tests are required as noted above, this ensures that our production branch is always well tested.

## Versions

There are several versions to keep track of:

1. *Dataset Version*: this is the GUNW version and incremented manually only when the GUNW has changed with relation to the end-user. This is in the GUNW name, i.e. `S1-GUNW-D-R-042-tops-20220429_20210528-140902-00123W_00034N-PP-e677-v2_0_5` has version 2.0.5. It is manually set [here](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/blob/0b219faac0c4e8c11ef610d3b35e7a8cb9a30511/isce2_topsapp/packaging.py#L17)
2. *Software Version*: Automatically tracked and incremented in CI/CD on merges to the production branch (`main`)
3. *Container Version*: Automatically tracked and incremented in CI/D on merges to `dev` (with `test` tag) and to `main` (with `latest` tag). The various images can be downloaded fromt he Packages sidebar ([link](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/pkgs/container/dockerizedtopsapp)).


## Releases (Docker containers and software)

The release workflows within the (ASF) CI/CD allows us to be more efficient both in terms of tracking the releases and pushing container images for cloud processing. Each merge to `main` or `dev` creates a new docker image that is published through the github registry. The `test` tag is the latest image built to `dev`. The `latest` tag is the most up-to-date `main` release for production. We can view various containers [here](https://github.com/ACCESS-Cloud-Based-InSAR/DockerizedTopsApp/pkgs/container/dockerizedtopsapp/versions).

The plugin's *software* version is governed by git tags and semantic versioning. The software version is incremented by merges to `main` (according to `major`/`minor`/`patch` labels). Any merge into `dev` is a (patch) test release so until `dev` is merged into `main`, the release number will correctly not increment. Software version can be seen via `import isce2_topsapp; isce2_topsapp.__version__`. 

When releasing a new version i.e. merging `dev` into `main`, ASF CI/CD requires an update the changelog with correct version that will be captured by the `major`/`minor`/`patch` bump. If you use the label `bumpless` and only CI/CD workflows or documentation has been changed, the software version remains the same. Otherwise, use `major`, `minor`, or `patch`. For many more details see these [notes](https://github.com/ACCESS-Cloud-Based-InSAR/CICD-notes).


## PR Requirements

All new features will first be merged into `dev` before being released (and merged into `main`).

1. If the software changes, please use: `major`, `minor`, or `patch` labels on a PR for maintainers to track the type of changes you are making
2. Update the changelog so that the bump (depending on `major`/`minor`/`patch`) is consistent with what the next release will hold (you may be including your changes in a larger release)
3. Please share a sample GUNW (and the command to generate it) so that the team can understand how the final product has been changed - unfortunately the test suite does not ensure the workflow will complete end-to-end.

Here are more detailed [notes](https://github.com/ACCESS-Cloud-Based-InSAR/CICD-notes).

### Additional (manual) checks

Even though there are some integration tests and unit tests in our test suites, this CPU intensive workflow cannot be tested end-to-end using github actions (there is simply not enough memory and CPU on a github runner).
Therefore, even if all the tests pass, there is still a nontrivial chance a GUNW is not successfully generated (e.g. the `topo` step of topsapp fizzles out because `numpy` API was not successfully tracked in the latest ISCE2 release).
We request a sample GUNW be shared in a PR.
Even if we go through careful accounting, once a PR is merged into `dev`, we will use `hyp3` to further inspect the new plugin e.g. through this [notebook](https://github.com/ACCESS-Cloud-Based-InSAR/s1_frame_enumerator/blob/dev/notebooks/Submitting_to_Hyp3.ipynb) using a few sites.
It is important to use `INSAR_ISCE_TEST` job to ensure the features from the `dev` branch are used.
Only after these **manual** checks, will we continue with a release of the plugin.

# FAQ

1. The docker build is taking a long time.

    *Answer*: Make sure the time is spent with `conda/mamba` not copying data files. The `.dockerignore` file should ignore ISCE2 data files (if you are running some examples within this repo directory, there will be GBs of intermediate files). It's crucial you don't include unnecessary ISCE2 intermediate files into the Docker image as this will bloat it.

2. Need to install additional packages such as vim in your container?

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

