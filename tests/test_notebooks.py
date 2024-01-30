from pathlib import Path

import papermill as pm
import pytest

notebooks = ['localize-data.ipynb',
             'prepare-for-delivery.ipynb',
             'solid_earth_tides.ipynb']


@pytest.mark.parametrize('notebook_name', notebooks)
def test_notebooks(notebook_name, monkeypatch):

    test_dir = Path(__file__).parents[0].absolute()

    out_dir = test_dir / 'out'
    out_dir.mkdir(exist_ok=True)

    out_notebook = out_dir / f'{notebook_name}'

    monkeypatch.setenv('ESA_USERNAME', 'foo')
    monkeypatch.setenv('ESA_PASSWORD', 'bar')
    pm.execute_notebook(test_dir / f'{notebook_name}',
                        output_path=out_notebook
                        )
