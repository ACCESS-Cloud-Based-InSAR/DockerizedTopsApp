import papermill as pm
from pathlib import Path


def test_download_dem():

    test_dir = Path(__file__).parents[0].absolute()

    out_dir = test_dir/'out'
    out_dir.mkdir(exist_ok=True)

    out_notebook = out_dir/'localize-data.ipynb'

    pm.execute_notebook(test_dir/'localize-data.ipynb',
                        output_path=out_notebook
                        )
