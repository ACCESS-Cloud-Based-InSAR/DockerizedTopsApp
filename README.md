# ISCE2 TopsApp Hyp3-Plugin

This is a dockerized TopsApp Science processing that performs the necessary localization of input datasets.

## Setup

1. `conda env update -n topsapp_env --file environment.yaml`
2. `pip install .`
3. Make an `.env` file with:

   ```
   earthdata_username=<earthdata_username>
   earthdata_password=<earthdata_password>
   ```
4. Make a `~/.netrc` file (or within the working directory) with:
    ```
    machine urs.earthdata.nasa.gov
        login <username>
        password <password>
    ```
    The ISCE library (I believe) obtains the [SRTM water body data](https://en.wikipedia.org/wiki/SRTM_Water_Body_Data) using the python [`requests`](https://docs.python-requests.org/en/latest/) library. `requests` automatically uses credentials stored in the `.netrc`.

## Run Locally

Run `isce2_topsapp sample_dataset.json`, where `json` file has the following form:

```
{
    "reference_scenes": ["S1B_IW_SLC__1SDV_20210723T014947_20210723T015014_027915_0354B4_B3A9"],
    "secondary_scenes": ["S1B_IW_SLC__1SDV_20210711T014922_20210711T014949_027740_034F80_859D",
                         "S1B_IW_SLC__1SDV_20210711T014947_20210711T015013_027740_034F80_D404",
                         "S1B_IW_SLC__1SDV_20210711T015011_20210711T015038_027740_034F80_376C"]
}
```

Because there are *lots* of intermediate processing files, good to this in its own directory:

1. Make a new directory (e.g. `mkdir ~/topsapp_example`) and navigate to it.
2. Create a `dataset.json` file in the format above with desired IDs.
3. Run `isce2_topsapp dataset.json`

## Run in docker

Build the docker image with `build -f Dockerfile -t topsapp_img .`.

1. To be continued

# FAQ

1. I get the following error when running `isce2_topsapp dataset.json`.

   ```
   ...
   env_path = dotenv.find_dotenv(usecwd=True,
   File ".../miniconda3/envs/topsapp_env/lib/python3.8/site-packages/dotenv/main.py", line 291, in find_dotenv
       raise IOError('File not found')
   ```
    *Answer*: There is no `.env` file as described above. This error is design. At some point, we may improve the error message and remove this FAQ.

