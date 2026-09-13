"""版本号解析测试。

对应 review 发现：``setup.py`` 直接 ``int(ref.split('.')[0])``，在
``GITHUB_REF_NAME='refs/tags/v1.2.3'`` 时抛 ``ValueError``，导致 release 发布
流水线构建失败。
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ixspy_ai_api import version as version_module  # noqa: E402
from ixspy_ai_api.version import VERSION, __version__, get_version, normalize_version  # noqa: E402


class TestNormalizeVersion(unittest.TestCase):
    def test_plain_semver(self):
        self.assertEqual(normalize_version("1.2.3"), "1.2.3")

    def test_tag_with_v_prefix(self):
        self.assertEqual(normalize_version("v1.2.3"), "1.2.3")

    def test_github_ref_name_full_tag_ref(self):
        """真实 GitHub Actions 场景：GITHUB_REF_NAME 是完整 ref。"""
        self.assertEqual(normalize_version("refs/tags/v1.2.3"), "1.2.3")
        self.assertEqual(normalize_version("refs/tags/1.2.3"), "1.2.3")

    def test_prerelease_and_development_versions_are_preserved(self):
        for raw, expected in (
            ("v1.2.3rc1", "1.2.3rc1"), ("1.0.0-rc1", "1.0.0rc1"),
            ("1.2.3.dev4", "1.2.3.dev4"), ("1.2.3.post2", "1.2.3.post2"),
            ("1.2.3+build.5", "1.2.3+build.5"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_version(raw), expected)

    def test_invalid_versions_cannot_silently_become_releases(self):
        for value in ("", "   ", "garbage", "v", "refs/heads/main", "1.2.3-garbage", "x.y.z"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_version(value)


class TestVersionResolution(unittest.TestCase):
    def test_module_version_is_pep440_shaped(self):
        parts = __version__.split(".")
        self.assertTrue(parts, "版本号不能为空")
        self.assertTrue(parts[0].isdigit(), f"主版本号必须是数字: {__version__!r}")

    def test_version_tuple_matches_string(self):
        from packaging.version import Version

        self.assertEqual(VERSION, Version(__version__).release)

    def test_explicit_env_var_wins(self):
        original = os.environ.get("IXSPY_AI_API_VERSION")
        os.environ["IXSPY_AI_API_VERSION"] = "9.8.7"
        try:
            self.assertEqual(get_version(), "9.8.7")
        finally:
            if original is None:
                os.environ.pop("IXSPY_AI_API_VERSION", None)
            else:
                os.environ["IXSPY_AI_API_VERSION"] = original

    def test_ci_env_takes_priority_over_installed_metadata(self):
        """核心回归：构建机上装有旧版本时，不能把旧版本号打进新发行包。"""
        env_backup = {key: os.environ.get(key) for key in
                      ("GITHUB_REF_NAME", "GITHUB_REF", "GITHUB_REF_TYPE", "IXSPY_AI_API_VERSION")}
        for key in env_backup:
            os.environ.pop(key, None)
        os.environ["GITHUB_REF_NAME"] = "refs/tags/v7.7.7"
        try:
            self.assertEqual(get_version(), "7.7.7")
        finally:
            for key, value in env_backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_explicit_override_beats_ci_env(self):
        env_backup = {key: os.environ.get(key) for key in ("GITHUB_REF_NAME", "IXSPY_AI_API_VERSION")}
        os.environ["GITHUB_REF_NAME"] = "refs/tags/v7.7.7"
        os.environ["IXSPY_AI_API_VERSION"] = "3.2.1"
        try:
            self.assertEqual(get_version(), "3.2.1")
        finally:
            for key, value in env_backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_branch_ref_falls_through_to_metadata(self):
        """分支构建（GITHUB_REF_NAME=main）不应把 'main' 当版本号。"""
        env_backup = {key: os.environ.get(key) for key in
                      ("GITHUB_REF_NAME", "GITHUB_REF", "GITHUB_REF_TYPE", "IXSPY_AI_API_VERSION")}
        for key in env_backup:
            os.environ.pop(key, None)
        os.environ["GITHUB_REF_NAME"] = "main"
        os.environ["GITHUB_REF"] = "refs/heads/main"
        try:
            self.assertEqual(get_version(), version_module._version_from_metadata())
        finally:
            for key, value in env_backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_version_module_does_not_import_http_or_build_backend(self):
        """构建时仅依赖声明的 packaging，不应导入 HTTP 客户端或 setuptools。"""
        source = Path(version_module.__file__).read_text(encoding="utf-8")
        for forbidden in ("import requests", "from requests", "import setuptools"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
