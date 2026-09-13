"""Version failures must not prevent runtime imports; builds remain strict."""

import io
import os
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

from ixspy_ai_api.version import get_build_version, get_version

VERSION_MODULE = Path(__file__).resolve().parents[1] / "ixspy_ai_api" / "version.py"


@pytest.mark.parametrize("content", ["Name: ixspy-ai-api\n", "Name: ixspy-ai-api\nVersion:\n"])
def test_missing_sdist_version_rejected_at_build(content):
    """构建期不得采用构建机上安装的发行版版本，否则会打出错误版本号的包。"""
    with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.read_text", return_value=content), \
            patch("importlib.metadata.version", return_value="1.1.2") as installed:
        with pytest.raises(ValueError, match="构建期无法确定版本"):
            get_build_version()
        installed.assert_not_called()


def test_missing_sdist_version_still_falls_back_at_runtime():
    with patch.dict(os.environ, {}, clear=True), \
            patch("pathlib.Path.read_text", return_value="Name: ixspy-ai-api\n"), \
            patch("importlib.metadata.version", return_value="1.1.2"):
        assert get_version() == "1.1.2"


@pytest.mark.parametrize("failure", [PermissionError("denied"), OSError("read failed")])
def test_unreadable_sdist_warns_and_falls_back(failure):
    with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.read_text", side_effect=failure), \
            patch("importlib.metadata.version", return_value="1.1.2"):
        with pytest.warns(RuntimeWarning, match="PKG-INFO"):
            assert get_version() == "1.1.2"
        with pytest.raises(ValueError, match="PKG-INFO"):
            get_build_version()


def test_invalid_utf8_is_replaced_when_reading_metadata():
    content = b"Name: ixspy-ai-api\nVersion: 1.2.3rc1\nSummary: \xff\n"

    def open_metadata(*args, **kwargs):
        return io.TextIOWrapper(io.BytesIO(content), encoding=kwargs.get("encoding"), errors=kwargs.get("errors"))

    with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.open", side_effect=open_metadata):
        assert get_version() == "1.2.3rc1"


@pytest.mark.parametrize("environment", [
    {"IXSPY_AI_API_VERSION": "broken"},
    {"IXSPY_AI_API_VERSION": ""},
    {"GITHUB_REF": "refs/tags/broken"},
    {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "broken"},
    {"GITHUB_REF_TYPE": "tag"},
    {"GITHUB_REF_NAME": "broken"},
])
def test_invalid_environment_is_tolerated_at_import_but_rejected_at_build(environment):
    with patch.dict(os.environ, environment, clear=True), \
            patch("pathlib.Path.read_text", side_effect=FileNotFoundError), \
            patch("importlib.metadata.version", return_value="1.1.2"):
        with pytest.warns(RuntimeWarning):
            module = runpy.run_path(str(VERSION_MODULE))
        assert module["__version__"] == "1.1.2"
        assert module["VERSION"] == (1, 1, 2)
        with pytest.raises(ValueError):
            module["get_build_version"]()


def test_invalid_sdist_version_is_tolerated_at_import_but_rejected_at_build():
    with patch.dict(os.environ, {}, clear=True), \
            patch("pathlib.Path.read_text", return_value="Name: ixspy-ai-api\nVersion: broken\n"), \
            patch("importlib.metadata.version", return_value="1.1.2"):
        with pytest.warns(RuntimeWarning):
            assert get_version() == "1.1.2"
        with pytest.raises(ValueError):
            get_build_version()


@pytest.mark.parametrize("version", [None, "", "broken"])
def test_missing_or_invalid_installed_version_has_safe_fallback(version):
    with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.read_text", side_effect=FileNotFoundError), \
            patch("importlib.metadata.version", return_value=version):
        if version == "broken":
            with pytest.warns(RuntimeWarning):
                assert get_version() == "0.0.0"
            with pytest.raises(ValueError):
                get_build_version()
        else:
            assert get_version() == "0.0.0"


def test_corrupt_installed_metadata_warns_and_does_not_block_import():
    with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.read_text", side_effect=FileNotFoundError), \
            patch("importlib.metadata.version", side_effect=ValueError("corrupt metadata")), \
            pytest.warns(RuntimeWarning):
        module = runpy.run_path(str(VERSION_MODULE))
    assert module["__version__"] == "0.0.0"
    assert module["VERSION"] == (0, 0, 0)
