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

1. `mkdir tmp` and navigate to it.
2. Create a `dataset.json` file as above in the `tmp`.
3. Run `isce2_topsapp dataset.json`

## Run in docker

Build the docker image with `build -f Dockerfile -t topsapp_img .`.

1. To be continued
