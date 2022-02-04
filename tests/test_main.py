import os

import pytest
from isce2_topsapp.__main__ import ensure_earthdata_credentials


def test_main_check_earthdata_credentials(tmp_path):
    netrc = tmp_path / '.netrc'
    netrc.write_text(f'machine foobar.nasa.gov login foo password bar')

    username, password = ensure_earthdata_credentials(None, None, host='foobar.nasa.gov', netrc_file=netrc)
    assert username == 'foo'
    assert password == 'bar'

    username, password = ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov', netrc_file=netrc)
    assert username == 'foo'
    assert password == 'bar'

    os.environ['EARTHDATA_USERNAME'] = 'fizz'
    os.environ['EARTHDATA_PASSWORD'] = 'buzz'

    username, password = ensure_earthdata_credentials(None, None, host='foobar.nasa.gov', netrc_file=netrc)
    assert username == 'foo'
    assert password == 'bar'

    username, password = ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov', netrc_file=netrc)
    assert username == 'foo'
    assert password == 'bar'

    with pytest.raises(ValueError):
        _ = ensure_earthdata_credentials(None, None, host='another.nasa.gov', netrc_file=netrc)

    with pytest.raises(ValueError):
        _ = ensure_earthdata_credentials('biz', 'baz', host='another.nasa.gov', netrc_file=netrc)


    netrc.unlink()
    del os.environ['EARTHDATA_USERNAME']
    del os.environ['EARTHDATA_PASSWORD']
    with pytest.raises(ValueError):
        _ = ensure_earthdata_credentials(None, None, host='foobar.nasa.gov', netrc_file=netrc)

    netrc.unlink()
    with pytest.raises(ValueError):
        _ = ensure_earthdata_credentials('biz', None, host='foobar.nasa.gov', netrc_file=netrc)

    netrc.unlink()
    with pytest.raises(ValueError):
        _ = ensure_earthdata_credentials(None, 'baz', host='foobar.nasa.gov', netrc_file=netrc)

    netrc.unlink()
    username, password = ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov', netrc_file=netrc)
    assert username == 'biz'
    assert password == 'baz'

    netrc.unlink()
    os.environ['EARTHDATA_USERNAME'] = 'fizz'
    os.environ['EARTHDATA_PASSWORD'] = 'buzz'
    username, password = ensure_earthdata_credentials(None, None, host='foobar.nasa.gov', netrc_file=netrc)
    assert username == 'fizz'
    assert password == 'buzz'

    netrc.unlink()
    username, password = ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov', netrc_file=netrc)
    assert username == 'biz'
    assert password == 'baz'

    netrc.unlink()
    del os.environ['EARTHDATA_PASSWORD']
    with pytest.raises(ValueError):
        _ = ensure_earthdata_credentials(None, None, host='foobar.nasa.gov', netrc_file=netrc)

    netrc.unlink()
    username, password = ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov', netrc_file=netrc)
    assert username == 'biz'
    assert password == 'baz'

    netrc.unlink()
    username, password = ensure_earthdata_credentials(None, 'baz', host='foobar.nasa.gov', netrc_file=netrc)
    assert username == 'fizz'
    assert password == 'baz'
