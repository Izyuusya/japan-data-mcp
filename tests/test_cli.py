"""CLI セットアップのユニットテスト."""

from pathlib import Path

import pytest

from japan_data_mcp.cli import (
    _check_api_keys,
    _find_project_root,
    _mask_key,
    _read_env_file,
    _write_env_file,
)


class TestMaskKey:
    def test_long_key(self):
        assert _mask_key("abcdefgh1234") == "****1234"

    def test_short_key(self):
        assert _mask_key("ab") == "****"

    def test_exact_four(self):
        assert _mask_key("abcd") == "****"

    def test_five_chars(self):
        assert _mask_key("abcde") == "****bcde"


class TestReadEnvFile:
    def test_read_existing(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ESTAT_APP_ID=test123\n"
            "CORP_APP_ID=corp456\n",
            encoding="utf-8",
        )
        result = _read_env_file(env_file)
        assert result == {
            "ESTAT_APP_ID": "test123",
            "CORP_APP_ID": "corp456",
        }

    def test_read_with_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# コメント\n"
            "ESTAT_APP_ID=test123\n"
            "\n"
            "# もう1つのコメント\n"
            "CORP_APP_ID=corp456\n",
            encoding="utf-8",
        )
        result = _read_env_file(env_file)
        assert result == {
            "ESTAT_APP_ID": "test123",
            "CORP_APP_ID": "corp456",
        }

    def test_read_with_quotes(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            'ESTAT_APP_ID="test123"\n'
            "CORP_APP_ID='corp456'\n",
            encoding="utf-8",
        )
        result = _read_env_file(env_file)
        assert result["ESTAT_APP_ID"] == "test123"
        assert result["CORP_APP_ID"] == "corp456"

    def test_read_nonexistent(self, tmp_path):
        env_file = tmp_path / ".env"
        result = _read_env_file(env_file)
        assert result == {}


class TestWriteEnvFile:
    def test_write_new_file(self, tmp_path):
        env_file = tmp_path / ".env"
        _write_env_file(env_file, {
            "ESTAT_APP_ID": "test123",
            "CORP_APP_ID": "corp456",
        })
        content = env_file.read_text(encoding="utf-8")
        assert "ESTAT_APP_ID=test123" in content
        assert "CORP_APP_ID=corp456" in content

    def test_update_existing(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# 設定ファイル\n"
            "ESTAT_APP_ID=old_value\n"
            "OTHER_KEY=keep_me\n",
            encoding="utf-8",
        )
        _write_env_file(env_file, {"ESTAT_APP_ID": "new_value"})

        content = env_file.read_text(encoding="utf-8")
        assert "ESTAT_APP_ID=new_value" in content
        assert "old_value" not in content
        assert "OTHER_KEY=keep_me" in content
        assert "# 設定ファイル" in content

    def test_add_new_key_to_existing(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ESTAT_APP_ID=existing\n",
            encoding="utf-8",
        )
        _write_env_file(env_file, {
            "ESTAT_APP_ID": "existing",
            "CORP_APP_ID": "new_key",
        })

        content = env_file.read_text(encoding="utf-8")
        assert "ESTAT_APP_ID=existing" in content
        assert "CORP_APP_ID=new_key" in content

    def test_skip_empty_values(self, tmp_path):
        env_file = tmp_path / ".env"
        _write_env_file(env_file, {
            "ESTAT_APP_ID": "test123",
            "CORP_APP_ID": "",
        })
        content = env_file.read_text(encoding="utf-8")
        assert "ESTAT_APP_ID=test123" in content
        assert "CORP_APP_ID" not in content


class TestFindProjectRoot:
    def test_finds_root(self, tmp_path, monkeypatch):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        monkeypatch.chdir(tmp_path)
        assert _find_project_root() == tmp_path

    def test_finds_root_from_subdir(self, tmp_path, monkeypatch):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        subdir = tmp_path / "src" / "pkg"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)
        assert _find_project_root() == tmp_path


class TestCheckApiKeys:
    def test_returns_true_when_set(self, monkeypatch):
        monkeypatch.setenv("ESTAT_APP_ID", "test123")
        assert _check_api_keys() is True

    def test_returns_false_when_missing(self, monkeypatch, tmp_path, capsys):
        monkeypatch.delenv("ESTAT_APP_ID", raising=False)
        # .env からの読み込みを防ぐため、空ディレクトリに移動
        monkeypatch.chdir(tmp_path)
        assert _check_api_keys() is False
        captured = capsys.readouterr()
        assert "setup" in captured.out
