import pytest
from isce2_topsapp.__main__ import ensure_earthdata_credentials


def test_main_check_earthdata_credentials_prefer_netrc(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    netrc = tmp_path / '.netrc'
    netrc.write_text('machine foobar.nasa.gov login foo password bar')

    ensure_earthdata_credentials(None, None, host='foobar.nasa.gov')
    assert netrc.read_text() == 'machine foobar.nasa.gov login foo password bar'

    ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov')
    assert netrc.read_text() == 'machine foobar.nasa.gov login foo password bar'

    monkeypatch.setenv('EARTHDATA_USERNAME', 'fizz')
    monkeypatch.setenv('EARTHDATA_PASSWORD', 'buzz')
    ensure_earthdata_credentials(None, None, host='foobar.nasa.gov')
    assert netrc.read_text() == 'machine foobar.nasa.gov login foo password bar'

    ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov')
    assert netrc.read_text() == 'machine foobar.nasa.gov login foo password bar'

    with pytest.raises(ValueError):
        ensure_earthdata_credentials(None, None)

    with pytest.raises(ValueError):
        ensure_earthdata_credentials('biz', 'baz')

    netrc.write_text('machine urs.earthdata.nasa.gov login foo password bar')
    ensure_earthdata_credentials(None, None)
    assert netrc.read_text() == 'machine urs.earthdata.nasa.gov login foo password bar'


def test_main_check_earthdata_credentials_fn_variables(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    netrc = tmp_path / '.netrc'

    with pytest.raises(ValueError):
        ensure_earthdata_credentials(None, None, host='foobar.nasa.gov')

    with pytest.raises(ValueError):
        ensure_earthdata_credentials('biz', None, host='foobar.nasa.gov')

    with pytest.raises(ValueError):
        ensure_earthdata_credentials(None, 'baz', host='foobar.nasa.gov')

    ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov')
    assert netrc.read_text() == 'machine foobar.nasa.gov login biz password baz'
    netrc.unlink()

    monkeypatch.setenv('EARTHDATA_USERNAME', 'fizz')
    monkeypatch.setenv('EARTHDATA_PASSWORD', 'buzz')
    ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov')
    assert netrc.read_text() == 'machine foobar.nasa.gov login biz password baz'


def test_main_check_earthdata_credentials_env_variables(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    netrc = tmp_path / '.netrc'

    monkeypatch.setenv('EARTHDATA_USERNAME', 'fizz')
    with pytest.raises(ValueError):
        ensure_earthdata_credentials(None, None, host='foobar.nasa.gov')

    monkeypatch.setenv('EARTHDATA_PASSWORD', 'buzz')
    ensure_earthdata_credentials(None, None, host='foobar.nasa.gov')
    assert netrc.read_text() == 'machine foobar.nasa.gov login fizz password buzz'
    netrc.unlink()

    ensure_earthdata_credentials(None, 'baz', host='foobar.nasa.gov')
    assert netrc.read_text() == 'machine foobar.nasa.gov login fizz password baz'
