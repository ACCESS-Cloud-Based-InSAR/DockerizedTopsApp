import os

import pytest

from isce2_topsapp.__main__ import (
    check_esa_credentials,
    ensure_earthdata_credentials,
    esd_threshold_argument,
    true_false_string_argument,
)


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


@pytest.mark.parametrize('username, password', [('foo', 'bar'), (None, 'bar'), ('foo', None)])
def test_check_esa_credentials(monkeypatch, username, password):
    with monkeypatch.context() as m:
        m.setenv('ESA_USERNAME', 'env_username')
        m.setenv('ESA_PASSWORD', 'env_password')

        check_esa_credentials(username, password)

        expected_username = username if username is not None else 'env_username'
        expected_password = password if password is not None else 'env_password'

        assert os.environ['ESA_USERNAME'] == expected_username
        assert os.environ['ESA_PASSWORD'] == expected_password


def test_check_esa_credentials_missing(monkeypatch):
    with monkeypatch.context() as m:
        m.delenv('ESA_USERNAME', raising=False)
        m.setenv('ESA_PASSWORD', 'env_password')
        msg = 'Please provide.* --esa-username .*'
        with pytest.raises(ValueError, match=msg):
            check_esa_credentials(None, None)

    with monkeypatch.context() as m:
        m.setenv('ESA_USERNAME', 'env_username')
        m.delenv('ESA_PASSWORD', raising=False)
        msg = 'Please provide.* --esa-password .*'
        with pytest.raises(ValueError, match=msg):
            check_esa_credentials(None, None)


def test_true_false_string_argument():
    assert true_false_string_argument('true') is True
    assert true_false_string_argument('TRUE') is True
    assert true_false_string_argument('True') is True
    assert true_false_string_argument('false') is False
    assert true_false_string_argument('False') is False
    assert true_false_string_argument('FALSE') is False

    with pytest.raises(ValueError):
        true_false_string_argument('foo')
    with pytest.raises(ValueError):
        true_false_string_argument('bar')
    with pytest.raises(ValueError):
        true_false_string_argument('')


def test_esd_threshold_argument():
    assert esd_threshold_argument('-1') == -1.0
    assert esd_threshold_argument('0') == 0.0
    assert esd_threshold_argument('.25') == 0.25
    assert esd_threshold_argument('0.5') == 0.5
    assert esd_threshold_argument('1') == 1.0

    with pytest.raises(ValueError):
        esd_threshold_argument('-1.1')
    with pytest.raises(ValueError):
        esd_threshold_argument('-0.9')
    with pytest.raises(ValueError):
        esd_threshold_argument('-0.1')
    with pytest.raises(ValueError):
        esd_threshold_argument('1.1')
