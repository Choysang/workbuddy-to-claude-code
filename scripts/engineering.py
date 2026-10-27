"""Default engineering settings; no model credentials or machine-specific paths."""
from copy import deepcopy
import re
from common import HOOK_SCRIPT

TEAM_TOOLS = {"TeamCreate", "TeamDelete", "DelegateTool"}
ABSENT = object()


def owned_hook(command: str) -> bool:
    normalized = command.replace("\\", "/").casefold()
    path = HOOK_SCRIPT.as_posix().casefold()
    return bool(re.search(r"(?<![\w/.-])" + re.escape(path) + r"(?=[\s\"';]|$)", normalized)
                or command.startswith("# harness-extra\n"))


def restore_value(current, before, installed):
    """Undo only values still equal to our installation; retain later user edits."""
    if current == installed:
        return before
    if isinstance(current, dict) and isinstance(installed, dict):
        old = before if isinstance(before, dict) else {}
        result = deepcopy(current)
        for key in old.keys() | installed.keys():
            value = restore_value(current.get(key, ABSENT), old.get(key, ABSENT),
                                  installed.get(key, ABSENT))
            if value is ABSENT:
                result.pop(key, None)
            else:
                result[key] = value
        return result if result or before is not ABSENT else ABSENT
    # Lists and scalar conflicts belong to the user's later edit.
    return current


def configured(settings: dict) -> dict:
    result = deepcopy(settings)
    result.pop("autoCompactWindow", None)
    for key in ("autoCompactEnabled", "fileCheckpointingEnabled", "deferToolLoading"):
        result[key] = True
    memory = result.setdefault("memory", {})
    memory.update(autoMemoryEnabled=True, typedMemory=True)
    if "disabledTools" in result:
        result["disabledTools"] = [tool for tool in result["disabledTools"] if tool not in TEAM_TOOLS]
    # Remove this toolkit's obsolete hooks, preserving user-owned commands.
    for event, groups in list(result.get("hooks", {}).items()):
        kept = []
        for group in groups:
            hooks = [hook for hook in group.get("hooks", [])
                     if not owned_hook(hook.get("command", ""))]
            if hooks:
                kept.append({**group, "hooks": hooks})
        if kept:
            result["hooks"][event] = kept
        else:
            del result["hooks"][event]
    return result


def changes(settings: dict) -> dict:
    desired = configured(settings)
    return {key: {"had": key in settings, "old": settings.get(key),
                  "present": key in desired, "new": desired.get(key)}
            for key in settings.keys() | desired.keys()
            if (key in settings) != (key in desired) or settings.get(key) != desired.get(key)}
