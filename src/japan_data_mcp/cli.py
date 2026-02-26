"""japan-data-mcp CLI エントリーポイント.

サーバー起動と対話的セットアップを提供する。
"""

from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _ensure_utf8_stdout() -> None:
    """Windows で stdout を UTF-8 に設定する.

    pytest 等のテスト環境ではキャプチャ用の stdout が使われるため、
    buffer 属性を持つ実ストリームのみ対象にする。
    """
    if sys.platform != "win32":
        return
    for attr in ("stdout", "stderr"):
        stream = getattr(sys, attr)
        if (
            hasattr(stream, "buffer")
            and hasattr(stream, "encoding")
            and stream.encoding
            and stream.encoding.lower().replace("-", "") != "utf8"
        ):
            setattr(
                sys,
                attr,
                io.TextIOWrapper(
                    stream.buffer, encoding="utf-8", errors="replace"
                ),
            )


# ------------------------------------------------------------------
# APIキー定義
# ------------------------------------------------------------------


@dataclass
class ApiKeyConfig:
    """APIキー設定の定義."""

    env_var: str
    label: str
    description: str
    url: str
    required: bool
    steps: list[str]  # 具体的な取得手順
    note: str = ""


API_KEYS: list[ApiKeyConfig] = [
    ApiKeyConfig(
        env_var="ESTAT_APP_ID",
        label="e-Stat API",
        description="統計データの取得に必要です。",
        url="https://www.e-stat.go.jp/api/api-info/api-guide",
        required=True,
        steps=[
            "上記URLにアクセス",
            "「ユーザ登録」からメールアドレスで登録（即時発行）",
            "マイページの「API機能(アプリケーションID)」からIDを取得",
        ],
    ),
    ApiKeyConfig(
        env_var="CORP_APP_ID",
        label="法人番号 Web-API",
        description="企業の法人番号・所在地を検索できます。",
        url="https://www.houjin-bangou.nta.go.jp/webapi/",
        required=False,
        steps=[
            "上記URLにアクセス",
            "「Web-API利用届出」から申請",
            "メールでアプリケーションIDが届く",
        ],
        note="申請から発行まで2〜4週間かかります。後から設定できます。",
    ),
    ApiKeyConfig(
        env_var="REALESTATE_API_KEY",
        label="不動産情報ライブラリ API",
        description="不動産取引価格情報を取得できます。",
        url="https://www.reinfolib.mlit.go.jp/api/request/",
        required=False,
        steps=[
            "上記URLにアクセス",
            "「API利用申請」から利用規約に同意して申請",
            "承認後、APIキーがメールで届く",
        ],
    ),
]


# ------------------------------------------------------------------
# .env ファイル操作
# ------------------------------------------------------------------


def _find_project_root() -> Path:
    """pyproject.toml のある最も近い親ディレクトリを返す."""
    current = Path.cwd()
    for directory in [current, *current.parents]:
        if (directory / "pyproject.toml").is_file():
            return directory
    return current


def _read_env_file(env_path: Path) -> dict[str, str]:
    """既存の .env ファイルを読み込む."""
    values: dict[str, str] = {}
    if not env_path.is_file():
        return values

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        values[key] = value
    return values


def _write_env_file(env_path: Path, values: dict[str, str]) -> None:
    """APIキーを .env ファイルに書き出す.

    既存のファイルがある場合は、既存の内容を保持しつつ
    APIキーのみ更新・追加する。
    """
    # 既存の行を読み込み
    existing_lines: list[str] = []
    existing_keys: set[str] = set()
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.partition("=")[0].strip()
                if key in values:
                    existing_keys.add(key)
                    existing_lines.append(f"{key}={values[key]}")
                    continue
            existing_lines.append(line)

    # 新規キーを追加
    for key, value in values.items():
        if key not in existing_keys and value:
            existing_lines.append(f"{key}={value}")

    env_path.write_text(
        "\n".join(existing_lines) + "\n", encoding="utf-8"
    )


def _mask_key(key: str) -> str:
    """APIキーをマスクして表示用にする."""
    if len(key) <= 4:
        return "****"
    return "****" + key[-4:]


# ------------------------------------------------------------------
# 対話的セットアップ
# ------------------------------------------------------------------


def setup() -> None:
    """対話的にAPIキーを設定する."""
    _ensure_utf8_stdout()

    print()
    print("japan-data-mcp セットアップ")
    print("=" * 30)
    print()

    root = _find_project_root()
    env_path = root / ".env"
    existing = _read_env_file(env_path)

    new_values: dict[str, str] = {}
    total = len(API_KEYS)

    for i, config in enumerate(API_KEYS, 1):
        required_label = "必須" if config.required else "任意 - スキップ可"
        print(f"[{i}/{total}] {config.label}（{required_label}）")
        print(f"  {config.description}")
        print(f"  取得先: {config.url}")
        if config.note:
            print(f"  ※ {config.note}")

        current = existing.get(config.env_var, "")

        # 未設定の場合は取得手順を表示
        if not current and config.steps:
            print("  取得手順:")
            for step_num, step in enumerate(config.steps, 1):
                print(f"    {step_num}. {step}")

        if current:
            print(f"  現在の値: {_mask_key(current)}")
            answer = input("  変更しますか？ (y/N): ").strip().lower()
            if answer != "y":
                new_values[config.env_var] = current
                print(f"  → 既存の設定を維持します")
                print()
                continue

        if config.required:
            prompt = f"  {config.env_var} を入力: "
        else:
            prompt = f"  {config.env_var} を入力（スキップ: Enter）: "

        value = input(prompt).strip()

        if not value and config.required:
            # 必須キーが空の場合は再入力を求める
            while not value:
                print("  ⚠ このAPIキーは必須です。")
                value = input(prompt).strip()

        if value:
            new_values[config.env_var] = value
            print(f"  ✓ 設定しました")
        else:
            print(f"  → スキップしました（後から再設定可）")
        print()

    # .env に書き出し
    _write_env_file(env_path, new_values)
    print(f".env ファイルを保存しました: {env_path}")
    print()

    # 設定状況サマリー
    saved = _read_env_file(env_path)
    print("設定済みAPI:")
    for config in API_KEYS:
        if saved.get(config.env_var):
            print(f"  ✓ {config.label}")
        else:
            print(f"  ✗ {config.label}（未設定）")
    print()
    print("サーバー起動: japan-data-mcp")
    print()
    print("ヒント: Claude Desktop で使う場合は claude_desktop_config.json の")
    print('  "env" セクションにも同じキーを設定してください。')
    print("  詳細は README.md を参照してください。")


# ------------------------------------------------------------------
# メインエントリーポイント
# ------------------------------------------------------------------


def _check_api_keys() -> bool:
    """必須APIキーが設定されているか確認し、未設定なら案内を表示する.

    Returns:
        True: 起動可能、False: 設定が必要
    """
    from japan_data_mcp.utils.env import load_env_file

    load_env_file()

    estat_id = os.environ.get("ESTAT_APP_ID", "")
    if estat_id:
        return True

    _ensure_utf8_stdout()
    print()
    print("=" * 50)
    print("  japan-data-mcp を使うには API キーの設定が必要です")
    print("=" * 50)
    print()
    print("  以下のコマンドで対話的に設定できます:")
    print()
    print("    japan-data-mcp setup")
    print()
    print("  または .env ファイルに直接記載:")
    print()
    print("    ESTAT_APP_ID=あなたのアプリケーションID")
    print()
    print("  e-Stat API キーの取得（無料・即時発行）:")
    print("    https://www.e-stat.go.jp/api/api-info/api-guide")
    print()
    return False


def main() -> None:
    """CLI エントリーポイント."""
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        setup()
    else:
        if not _check_api_keys():
            sys.exit(1)
        from japan_data_mcp.server import main as server_main

        server_main()
