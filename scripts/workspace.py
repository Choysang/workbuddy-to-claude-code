"""Project-local plugin preferences, above the desktop-rewritten user settings.

The bundled 5.8.4 CLI's PathUtils defaults project settings to .codebuddy,
independently of the WorkBuddy user data directory (.workbuddy-ai).
"""
from pathlib import Path

import common as C

PROJECT_CONFIG_DIR = ".codebuddy"


def settings_path(root: Path) -> Path:
    return Path(root).resolve() / PROJECT_CONFIG_DIR / "settings.local.json"


def merged(current: dict) -> dict:
    if not isinstance(current, dict):
        raise ValueError("工作区设置必须为 JSON 对象")
    plugins = C.read_json(C.PROFILE / "plugins.json", strict=True)
    enabled = current.get("enabledPlugins", {})
    if not isinstance(enabled, dict):
        raise ValueError("工作区 enabledPlugins 必须为 JSON 对象")
    result = dict(current)
    flags = dict(enabled)
    flags.update({key: False for key in plugins["disable"]})
    flags.update({key: True for key in plugins["keep"]})
    result["enabledPlugins"] = flags
    return result
