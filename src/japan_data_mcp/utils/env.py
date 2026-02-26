"""環境変数ヘルパー."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file() -> None:
    """プロジェクトルートの .env から環境変数を読み込む（未設定のもののみ）.

    カレントディレクトリから親ディレクトリを遡って .env ファイルを探す。
    見つかった場合、未設定の環境変数のみセットする（既存値は上書きしない）。
    """
    current = Path.cwd()
    for directory in [current, *current.parents]:
        env_path = directory / ".env"
        if env_path.is_file():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                if key not in os.environ:
                    os.environ[key] = value
            break
