# ISCE2 TopsApp Hyp3-Plugin

This is a dockerized TopsApp Science processing that performs the necessary localization of input datasets.

## Setup

1. `conda env update -n topsapp_env --file environment.yml`
2. `pip install .`

### Setup for local runs

1. Ensure that your `~/.netrc` file has:
    ```
    machine urs.earthdata.nasa.gov
        login <username>
        password <password>
    ```
    This file is necessary for downloading the Sentinel-1 orbit files and the ISCE library requires them for the [SRTM water body data](https://en.wikipedia.org/wiki/SRTM_Water_Body_Data). The [`requests`](https://docs.python-requests.org/en/latest/) library automatically uses credentials stored in the `~/.netrc` for authentification when none are supplied.


## Run Locally

Make sure you have `~/.netrc`. Run the following command:

```
isce2_topsapp --reference-scenes S1B_IW_SLC__1SDV_20210723T014947_20210723T015014_027915_0354B4_B3A9 \
              --secondary-scenes S1B_IW_SLC__1SDV_20210711T014922_20210711T014949_027740_034F80_859D \
                                 S1B_IW_SLC__1SDV_20210711T014947_20210711T015013_027740_034F80_D404 \
                                 S1B_IW_SLC__1SDV_20210711T015011_20210711T015038_027740_034F80_376C
```

## Run in a (local) docker container in interactive mode

1. Build the docker image from this repository with

    ```docker build -f Dockerfile -t topsapp_img .```

2. Create a directory to mount the data files so you can inspect them outside of your docker container. Call it `topsapp_data`. Navigate to it. Copy the `sample_run.sh` in this directory, modifying it to add your username and password e.g.

    ```
   isce2_topsapp --reference-scenes S1B_IW_SLC__1SDV_20210723T014947_20210723T015014_027915_0354B4_B3A9 \
                 --secondary-scenes S1B_IW_SLC__1SDV_20210711T014922_20210711T014949_027740_034F80_859D \
                                    S1B_IW_SLC__1SDV_20210711T014947_20210711T015013_027740_034F80_D404 \
                                    S1B_IW_SLC__1SDV_20210711T015011_20210711T015038_027740_034F80_376C
                --username <username>
                --password <password>
   ```

3. Take a look around a docker container, mounting a volume built from the image with:

   ```docker run -ti -v $PWD:/home/ops/topsapp_data topsapp_img```

   You can even run jupyter notebooks within the docker container mirroring ports with `-p 1313:1313`.

4. Run the topsapp process within a docker container:

   ```cd /home/ops/topsapp_data && /home/ops/topsapp_data/sample_run.sh```

We can combine steps 3 and 4 above as:

```docker run -ti -v $PWD:/home/ops/topsapp_data topsapp_img bash -c "cd /home/ops/topsapp_data && /home/ops/topsapp_data/sample_run.sh```


## FAQ

1. The docker build is taking a long time.

    *Answer*: Make sure the time is spent with `conda/mamba` not copying data files. The `.dockerignore` file should ignore ISCE2 data files (if you are running some examples within this repo directory, there will be GBs of intermediate files). It's crucial you don't include unnecessary ISCE2 intermediate files into the Docker image as this will bloat it.
