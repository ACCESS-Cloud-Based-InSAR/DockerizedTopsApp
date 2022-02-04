import os

import pytest
from isce2_topsapp.__main__ import ensure_earthdata_credentials


def test_main_check_earthdata_credentials(tmp_path):
    netrc = tmp_path / '.netrc'
    netrc.write_text('machine foobar.nasa.gov login foo password bar')

    ensure_earthdata_credentials(None, None, host='foobar.nasa.gov', netrc_file=netrc)
    assert netrc.read_text() == 'machine foobar.nasa.gov login foo password bar'

    ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov', netrc_file=netrc)
    assert netrc.read_text() == 'machine foobar.nasa.gov login foo password bar'

    os.environ['EARTHDATA_USERNAME'] = 'fizz'
    os.environ['EARTHDATA_PASSWORD'] = 'buzz'
    ensure_earthdata_credentials(None, None, host='foobar.nasa.gov', netrc_file=netrc)
    assert netrc.read_text() == 'machine foobar.nasa.gov login foo password bar'

    ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov', netrc_file=netrc)
    assert netrc.read_text() == 'machine foobar.nasa.gov login foo password bar'

    with pytest.raises(ValueError):
        ensure_earthdata_credentials(None, None, host='another.nasa.gov', netrc_file=netrc)

    with pytest.raises(ValueError):
        ensure_earthdata_credentials('biz', 'baz', host='another.nasa.gov', netrc_file=netrc)

    netrc.unlink()
    del os.environ['EARTHDATA_USERNAME']
    del os.environ['EARTHDATA_PASSWORD']
    with pytest.raises(ValueError):
        ensure_earthdata_credentials(None, None, host='foobar.nasa.gov', netrc_file=netrc)

    with pytest.raises(ValueError):
        _ = ensure_earthdata_credentials('biz', None, host='foobar.nasa.gov', netrc_file=netrc)

    with pytest.raises(ValueError):
        _ = ensure_earthdata_credentials(None, 'baz', host='foobar.nasa.gov', netrc_file=netrc)

    ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov', netrc_file=netrc)
    assert netrc.read_text() == 'machine foobar.nasa.gov login biz password baz'

    netrc.unlink()
    os.environ['EARTHDATA_USERNAME'] = 'fizz'
    os.environ['EARTHDATA_PASSWORD'] = 'buzz'
    ensure_earthdata_credentials(None, None, host='foobar.nasa.gov', netrc_file=netrc)
    assert netrc.read_text() == 'machine foobar.nasa.gov login fizz password buzz'

    netrc.unlink()
    ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov', netrc_file=netrc)
    assert netrc.read_text() == 'machine foobar.nasa.gov login biz password baz'

    netrc.unlink()
    del os.environ['EARTHDATA_PASSWORD']
    with pytest.raises(ValueError):
        ensure_earthdata_credentials(None, None, host='foobar.nasa.gov', netrc_file=netrc)

    ensure_earthdata_credentials('biz', 'baz', host='foobar.nasa.gov', netrc_file=netrc)
    assert netrc.read_text() == 'machine foobar.nasa.gov login biz password baz'

    netrc.unlink()
    ensure_earthdata_credentials(None, 'baz', host='foobar.nasa.gov', netrc_file=netrc)
    assert netrc.read_text() == 'machine foobar.nasa.gov login fizz password baz'
