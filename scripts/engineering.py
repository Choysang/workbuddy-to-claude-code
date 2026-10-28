"""Build a persistent coding edition from the user's installed WorkBuddy files.

Run once after a vendor update. No vendor files are shipped by this repository.
Unknown source layouts fail before publishing an edition or changing shortcuts.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

import common as C
import install

EXE = "WorkBuddyAI.exe"
SERVER = "main/server.js"
CLI = "cli/dist/codebuddy-lite-wb.mjs"
PROMPT = "resources/plugins/workbuddy-builtin/welcomemode/code/prompt.tpl"
TAR = "main/tar.js"
IDENTITY = "resources/templates/user-context-identity.tpl"
NODE = "main/node.js"
CRAFT = "resources/plugins/workbuddy-builtin/interactionmode/craft/fragments/interaction.md"
PATCH_REVISION = 2


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_once(source: bytes, old: bytes, new: bytes, label: str) -> bytes:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one source match, found {count}; vendor update needs adaptation")
    return source.replace(old, new, 1)


def _enforce_plugin_profile(source: bytes, engine: str) -> bytes:
    """The coding edition owns this deny list even if desktop/account state drifts."""
    disabled = C.read_json(C.PROFILE / "plugins.json")["disable"]
    names = json.dumps(disabled, separators=(",", ":")).encode("ascii")
    if engine == "desktop":
        old = b"return n||(this.enabledPluginsCache=r),r}getSettingsScopePriority"
        policy = b"for(let id of " + names + b")r[id]={enabled:!1,scope:Q.CLI};"
    else:
        old = b"return i||(this.enabledPluginsCache=n),n}getSettingsScopePriority"
        policy = b"for(let id of " + names + b")n[id]={enabled:!1,scope:tv.I7.CLI};"
    return replace_once(source, old, policy + old, "coding plugin profile: " + engine)


def patch_server(source: bytes) -> bytes:
    start = source.find(b"async function restoreBuiltinExtensionOverrides(e){")
    end = source.find(b"function registerPluginRecommendationHandlers", start)
    if start < 0 or end < 0 or source.count(b"async function restoreBuiltinExtensionOverrides(e){") != 1:
        raise ValueError("Builtin preference migration layout changed; needs adaptation")
    original = source[start:end]
    if b"shouldRemoveBuiltinPluginOverride" not in original or b"skillOverrides" not in original:
        raise ValueError("Builtin preference migration body is not the supported implementation")
    replacement = b"async function restoreBuiltinExtensionOverrides(e){return 0}"
    source = source[:start] + replacement + source[end:]
    source = replace_once(source,
        b"enabledPlugins:{...asRecord$3(i.enabledPlugins),...r}",
        b"enabledPlugins:{...r,...asRecord$3(i.enabledPlugins)}", "account plugin precedence")
    old = (b"function withSessionEnabledPluginSetting(e,n,r){let i=e?.enabledPlugins,"
           b"a=i&&typeof i==`object`&&!Array.isArray(i)?{...i}:{};"
           b"return a[n]=r,{...e??{},enabledPlugins:a}}")
    new = (b"function withSessionEnabledPluginSetting(e,n,r){let i=e?.enabledPlugins,"
           b"a=i&&typeof i==`object`&&!Array.isArray(i)?{...i}:{};"
           b"return a[n]=a[n]===!1?!1:r,{...e??{},enabledPlugins:a}}")
    source = replace_once(source, old, new, "session explicit disable")
    source = replace_once(source,
        b"async start(){try{await this.clawService.startSavedChannels()",
        b"async start(){return;try{await this.clawService.startSavedChannels()",
        "disable unused Claw channel lifecycle")
    source = replace_once(source,
        b"!f&&e.tools!==void 0&&u.push(`--tools`,normalizeWorkBuddyToolSpecs(e.tools))",
        b"u.push(`--tools`," + _coding_tools(b"e.tools", b"normalizeWorkBuddyToolSpecs(e.tools)") + b")",
        "coding tools")
    source = patch_session_mcp(source)
    # The vendor pre-approves its ecosystem tools on every launch; keep only what still exists.
    source = replace_once(source,
        b"FM=[`present_files`,`widget_guidelines`,`show_widget`,`connect_cloud_service`,`connect_open_platform`,"
        b"`WebFetch`,`Bash(mcporter:*)`,`A2AGetAgentCard`,`A2ASendMessage`,`A2AGetTask`,`A2ACancelTask`]",
        b"FM=[`present_files`,`WebFetch`]", "pre-approved tools")
    source = replace_once(source,
        b"function resolveSessionBuiltinToolNames(e,n){if(!n)",
        b"function resolveSessionBuiltinToolNames(e,n){e=e.filter(t=>t.name===`present_files`);if(!n)",
        "coding builtin MCP surface")
    return _enforce_plugin_profile(source, "desktop")


def patch_cli(source: bytes) -> bytes:
    # Builtin ecosystem skills stay off even after the desktop rewrites settings.skillOverrides.
    off = json.dumps(C.read_json(C.PROFILE / "builtin-skills-off.json"), ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    source = replace_once(source,
        b'function resolveSkillOverrideState(t,i){if(isPluginSkill(t))return"on";',
        b'function resolveSkillOverrideState(t,i){if(isPluginSkill(t)&&' + off + b'.includes(t.name))return"off";',
        "plugin skill preference")
    source = patch_compaction(source)
    return _enforce_plugin_profile(source, "cli")


# Fraction of the context budget under which auto-compaction keeps the vendor's "engineering
# compact" (every message and tool-call argument verbatim, results dropped) instead of asking
# the model for a summary. Vendor default .15 = 150K on a 1M window, estimated as chars/4,
# which undercounts CJK text: a 67K "estimate" restarted the session at 121K real tokens.
COMPACT_SUFFICIENCY_RATIO = b".02"


def patch_compaction(source: bytes) -> bytes:
    """Make auto-compaction produce a real LLM summary, as Claude Code does."""
    return replace_once(source,
        b"CODEBUDDY_ENGINEERING_COMPACT_SUFFICIENCY_PCT;if(!t)return .15;",
        b"CODEBUDDY_ENGINEERING_COMPACT_SUFFICIENCY_PCT;if(!t)return " + COMPACT_SUFFICIENCY_RATIO + b";",
        "compaction summary threshold")


def _mcp_deny() -> bytes:
    """Ecosystem MCP server ids the profile disables, as a JS array literal."""
    return json.dumps(C.read_json(C.PROFILE / "tool-control.json")["disabledMcpServerIds"],
                      separators=(",", ":")).encode("ascii")


def patch_session_mcp(source: bytes) -> bytes:
    """Filter at the source: the same server map feeds --mcp-config and the ACP session/new list,
    and the CLI prefers the ACP list. Disabled ecosystem servers are then never spawned."""
    deny = _mcp_deny()
    source = replace_once(source,
        b"let applyConfig=e=>{if(!e)return;",
        b"let applyConfig=e=>{if(!e)return;e={...e,servers:Object.fromEntries(Object.entries(e.servers??{})"
        b".filter(([k])=>!" + deny + b".includes(k)))};",
        "session MCP servers")
    return replace_once(source,
        b"D=[...c.filter(n=>!E.has(n.name)||",
        b"D=[...c.filter(n=>!" + deny + b".includes(n.name)).filter(n=>!E.has(n.name)||",
        "project MCP servers")


def _coding_tools(current: bytes, fallback: bytes) -> bytes:
    """JS expression: the coding tool profile, except for a read-only mode (a vendor list without
    Write, e.g. ask) which keeps its own list."""
    literal = json.dumps(C.CODE_TOOLS).encode("ascii")
    return (b"(!" + current + b"||" + current + b".split(`,`).map(t=>t.trim()).includes(`Write`)?"
            + literal + b":" + fallback + b")")


def patch_conversation_tools(source: bytes) -> bytes:
    """The daemon's conversation launcher (prewarm path) forwards the vendor work-mode tool list
    to both the CLI args and the product-config env; replace it before either is built."""
    return replace_once(source,
        b"N=A.tools?A.tools.split(`,`)",
        b"N=(A.tools=" + _coding_tools(b"A.tools", b"A.tools") + b",A.tools)?A.tools.split(`,`)",
        "conversation coding tools")


def patch_turn_context(source: bytes) -> bytes:
    """Drop the per-turn connector status block; it lists ecosystem connectors and tells the
    model to call disabled plugin tools."""
    return replace_once(source,
        b"function renderConnectorStatusBlock(e){return!e||e.length===0?[]:",
        b"function renderConnectorStatusBlock(e){return[];return!e||e.length===0?[]:",
        "connector status reminder")


def patch_startup_update(source: bytes) -> bytes:
    return replace_once(source,
        b"async function tryEarlySilentStartupUpdate(e){let n=UpdateFileLogger.getInstance();",
        b"async function tryEarlySilentStartupUpdate(e){return!1;let n=UpdateFileLogger.getInstance();",
        "disable edition startup installer")


def patch_windows_updater(source: bytes) -> bytes:
    patches = (
        (b"async waitForStartupRestore(){await this.startupRestorePromise}",
         b"async waitForStartupRestore(){await this.startupRestorePromise}"
         b"async checkForceUpgrade(){}async checkStartupForceAutoUpdate(){}"
         b"async quitAndInstallForStartup(){return!1}"),
        (b"async restoreDownloadedUpdate(){let e;", b"async restoreDownloadedUpdate(){return;let e;"),
        (b"async checkForUpdates(e=!1){if(this.checkInProgress){",
         b"async checkForUpdates(e=!1){this.setState(`idle`);return;if(this.checkInProgress){"),
        (b"async downloadUpdate(e){let t=e.productVersion;",
         b"async downloadUpdate(e){return;let t=e.productVersion;"),
        (b"quitAndInstall(){if(this.fileLogger.info(",
         b"quitAndInstall(){return!1;if(this.fileLogger.info("),
    )
    for old, new in patches:
        source = replace_once(source, old, new, "disable edition self-update")
    return source


def patch_navigation(source: bytes) -> bytes:
    source = replace_once(source,
        b"r=n.key;if(e.has(r))return;",
        b"r=n.key;if(![`new_task`,`project`].includes(r)||e.has(r))return;", "coding navigation")
    source = replace_once(source,
        b"function getVisibleSceneTabOptions(e){return ws()?e.filter(e=>e.id!==`design`):e}",
        b"function getVisibleSceneTabOptions(e){return e.filter(e=>e.id===`code`)}", "coding mode selector")
    return replace_once(source, b"modes:{defaultSelected:`work`}",
                        b"modes:{defaultSelected:`code`}", "coding default")


def patch_home_memory(source: bytes) -> bytes:
    old = (b"function getRememberedHomeSceneMode(){let e=readSceneModePreference();"
           b"return e&&e!==C&&(C=e),C}")
    return replace_once(source, old, b"function getRememberedHomeSceneMode(){return `code`}",
                        "home coding preference")


class Archive:
    """Keep packed offsets stable and regenerate the ASAR Pickle header."""

    def __init__(self, path: Path):
        self.path = path
        self.raw = path.read_bytes()
        size, header_size, _, json_size = struct.unpack_from("<4I", self.raw)
        if size != 4 or 16 + json_size > len(self.raw):
            raise ValueError("Invalid ASAR header")
        self.header_bytes = self.raw[16:16 + json_size]
        self.header = json.loads(self.header_bytes)
        self.body = bytearray(self.raw[8 + header_size:])

    def entry(self, name: str) -> dict:
        node = self.header
        for part in name.split("/"):
            node = node["files"][part]
        if "link" in node:
            raise ValueError(f"Linked ASAR entry is unsupported: {name}")
        return node

    def read(self, name: str) -> bytes:
        node = self.entry(name)
        if node.get("unpacked"):
            return (Path(str(self.path) + ".unpacked") / name).read_bytes()
        offset = int(node["offset"])
        return bytes(self.body[offset:offset + node["size"]])

    def replace(self, name: str, data: bytes, app_root: Path) -> str:
        node = self.entry(name)
        original = self.read(name)
        integrity = node.get("integrity")
        if not integrity or integrity.get("algorithm") != "SHA256" or integrity.get("hash") != digest(original):
            raise ValueError(f"Original ASAR integrity mismatch: {name}")
        if node.get("unpacked"):
            C.write_bytes(app_root / "resources/app.asar.unpacked" / name, data)
            node["size"] = len(data)
        else:
            if len(data) > node["size"]:
                node["offset"] = str(len(self.body))
                node["size"] = len(data)
                self.body.extend(data)
            else:
                data = data.ljust(node["size"], b" ")
                offset = int(node["offset"])
                self.body[offset:offset + node["size"]] = data
        block = integrity["blockSize"]
        integrity["hash"] = digest(data)
        integrity["blocks"] = [digest(data[i:i + block]) for i in range(0, len(data), block)]
        return digest(data)

    def save(self, path: Path) -> str:
        header = json.dumps(self.header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        payload = struct.pack("<I", len(header)) + header
        payload += b"\0" * (-len(payload) % 4)
        pickle_header = struct.pack("<I", len(payload)) + payload
        result = struct.pack("<II", 4, len(pickle_header)) + pickle_header + self.body
        C.write_bytes(path, result)
        return digest(header)


def patch_executable(source: bytes, before: str, after: str) -> bytes:
    """Update ASAR resource hashes; keep executable code and integrity fuses."""
    if source[:2] != b"MZ":
        raise ValueError("Not a PE executable")
    pe = struct.unpack_from("<I", source, 0x3C)[0]
    if source[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Invalid PE signature")
    count = struct.unpack_from("<H", source, pe + 6)[0]
    optional_size = struct.unpack_from("<H", source, pe + 20)[0]
    resources = []
    for i in range(count):
        at = pe + 24 + optional_size + 40 * i
        if source[at:at + 8].rstrip(b"\0") == b".rsrc":
            size, start = struct.unpack_from("<II", source, at + 16)
            resources.append((start, start + size))
    if len(resources) != 1:
        raise ValueError("Unexpected PE resource layout")
    start, end = resources[0]
    old, new = before.encode("ascii"), after.encode("ascii")
    region = source[start:end]
    if before == after or source.count(old) != 2 or region.count(old) != 2:
        raise ValueError("ASAR resource hash layout changed; needs adaptation")
    for algorithm in (b"SHA256", b"sha256"):
        prefix = b'"file":"resources\\\\app.asar","alg":"' + algorithm + b'","value":"'
        if region.count(prefix + old + b'"') != 1:
            raise ValueError("ASAR resource hash record changed; needs adaptation")
    return source[:start] + region.replace(old, new) + source[end:]


def _unique_asset(archive: Archive, pattern: str) -> str:
    names = archive.header["files"]["renderer"]["files"]["assets"]["files"]
    matches = [name for name in names if re.fullmatch(pattern, name)]
    if len(matches) != 1:
        raise ValueError(f"Expected one renderer asset {pattern}, found {len(matches)}")
    return "renderer/assets/" + matches[0]


def _check_javascript(source: bytes, module: bool) -> None:
    node = shutil.which("node")
    if not node:
        raise ValueError("Node.js is required to validate program patches")
    result = subprocess.run([node, "--check", "--input-type=" + ("module" if module else "commonjs")],
                            input=source, capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError("Patched JavaScript failed syntax validation: " + result.stderr.decode("utf-8", "replace")[:1000])


def _source_dir(explicit: Path | None, cfg: Path) -> Path:
    state = C.read_json(C.state_dir(cfg) / "engineering.json", default={}) or {}
    candidates = [explicit] if explicit else [Path(state["source"]) if state.get("source") else None,
        Path(os.environ.get("LOCALAPPDATA", "C:/missing")) / "Programs/WorkBuddyAI",
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "WorkBuddyAI",
        Path("D:/Program Files/WorkBuddyAI")]
    for path in candidates:
        if path and (path / EXE).is_file() and (path / "resources/app.asar").is_file():
            return path.resolve()
    raise ValueError("WorkBuddy installation not found; pass --app-dir with its installation directory")


def _running_workbuddy_pids() -> list[int]:
    if os.name != "nt":
        return []
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
        "Get-Process -Name WorkBuddyAI -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }; exit 0"],
        capture_output=True, timeout=15)
    if result.returncode:
        raise ValueError("Cannot inspect running WorkBuddy processes; configuration was not changed")
    return [int(line) for line in result.stdout.decode("ascii", "replace").splitlines() if line.strip().isdigit()]


def install_shortcuts(executable: Path, cfg: Path) -> None:
    if os.name != "nt":
        return
    # COM writes .lnk files; all dynamic paths travel in the environment, not code.
    script = r'''
$ErrorActionPreference = 'Stop'
$harnessShell = New-Object -ComObject WScript.Shell
$harnessRoots = @([Environment]::GetFolderPath('DesktopDirectory'), [Environment]::GetFolderPath('Programs'))
foreach ($harnessRoot in $harnessRoots) {
  $harnessLink = Join-Path $harnessRoot 'WorkBuddy AI 工程版.lnk'
  $harnessShortcut = $harnessShell.CreateShortcut($harnessLink)
  if ($harnessShortcut.TargetPath -eq $env:HARNESS_EDITION_EXE) { continue }
  if (Test-Path -LiteralPath $harnessLink) {
    $harnessBackup = Join-Path $env:HARNESS_SHORTCUT_BACKUP ([Guid]::NewGuid().ToString() + '.lnk')
    New-Item -ItemType Directory -Force -Path $env:HARNESS_SHORTCUT_BACKUP | Out-Null
    Copy-Item -LiteralPath $harnessLink -Destination $harnessBackup
  }
  $harnessShortcut.TargetPath = $env:HARNESS_EDITION_EXE
  $harnessShortcut.WorkingDirectory = Split-Path -LiteralPath $env:HARNESS_EDITION_EXE
  $harnessShortcut.IconLocation = $env:HARNESS_EDITION_EXE + ',0'
  $harnessShortcut.Description = 'WorkBuddy coding edition; rebuild after vendor updates.'
  $harnessShortcut.Save()
}
'''
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   env={**os.environ, "HARNESS_EDITION_EXE": str(executable),
                        "HARNESS_SHORTCUT_BACKUP": str(C.state_dir(cfg) / "shortcut-backups")},
                   check=True, capture_output=True, timeout=30)


def build(app_dir: Path | None = None, output: Path | None = None,
          shortcuts: bool = True, workspaces: list[Path] | None = None) -> dict:
    running = _running_workbuddy_pids()
    if running:
        raise ValueError("请先退出原厂和工程版 WorkBuddy，再生成工程版，避免旧进程回写配置。PID: "
                         + ",".join(map(str, running)))
    cfg = C.config_dir()
    source = _source_dir(app_dir, cfg)
    archive = Archive(source / "resources/app.asar")
    package = json.loads(archive.read("package.json"))
    version = package["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}(?:[-+][A-Za-z0-9.-]+)?", version):
        raise ValueError("Invalid application version")
    profile_hash = digest(b"".join(p.relative_to(C.PROFILE).as_posix().encode() + p.read_bytes()
                          for p in sorted(C.PROFILE.rglob("*")) if p.is_file() and "__pycache__" not in p.parts))
    source_hash = digest(archive.raw + (source / EXE).read_bytes() + archive.read(CLI))
    key = digest(f"{source_hash}:{profile_hash}:{C.sha256(Path(__file__))}:{PATCH_REVISION}".encode())[:16]
    parent = Path(output or C.state_dir(cfg) / "engineering/versions").resolve()
    if parent == source or source in parent.parents or parent in source.parents:
        raise ValueError("Engineering output must be separate from the vendor installation")
    target = parent / f"{version}-{key}"
    manifest_path = target / "engineering-manifest.json"
    if target.exists():
        manifest = C.read_json(manifest_path, strict=True)
        for name, expected in manifest["files"].items():
            if C.sha256(target / name) != expected:
                raise ValueError(f"Existing edition was modified: {target / name}; use a new output directory")
        install.apply(workspaces=workspaces)
        if shortcuts:
            install_shortcuts(target / EXE, cfg)
        C.write_json(C.state_dir(cfg) / "engineering.json", {**manifest, "edition": str(target)})
        return {"edition": str(target), "version": version, "reused": True}

    # Resolve every source anchor and syntax check before copying or writing config.
    modifications = {SERVER: patch_server(archive.read(SERVER)), CLI: patch_cli(archive.read(CLI)),
                     PROMPT: (C.PROFILE / "prompt/prompt.tpl").read_bytes(),
                     # Per-turn identity block: profile text only, no persona/onboarding/product pitch.
                     IDENTITY: (C.PROFILE / "prompt/user-context-identity.tpl").read_bytes(),
                     TAR: patch_turn_context(archive.read(TAR)),
                     CRAFT: C.CRAFT_INTERACTION,
                     NODE: patch_conversation_tools(archive.read(NODE)),
                     "main/index.js": patch_startup_update(archive.read("main/index.js")),
                     "main/update-service.win32.js": patch_windows_updater(archive.read("main/update-service.win32.js"))}
    nav = _unique_asset(archive, r"contexts-[A-Za-z0-9_-]+\.js")
    memory = _unique_asset(archive, r"home-scene-mode-memory-[A-Za-z0-9_-]+\.js")
    modifications[nav] = patch_navigation(archive.read(nav))
    modifications[memory] = patch_home_memory(archive.read(memory))
    # Renderer HTML is a known local artifact; hide promotional components only.
    html = "renderer/index.html"
    css = (b"<style data-harness=\"coding\">.conversation-list-invite-friends,"
           b".miniprogram-qr-trigger,.user-menu-trigger-miniprogram,.quick-actions{display:none!important}</style>")
    modifications[html] = replace_once(archive.read(html), b"</head>", css + b"</head>", "coding shell style")
    for name, data in modifications.items():
        if name.endswith(('.js', '.mjs')):
            _check_javascript(data, not name.startswith("main/"))
    # This also validates config without writing it.
    install.apply(dry_run=True, workspaces=workspaces)
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".building-", dir=parent)).resolve()
    try:
        shutil.copytree(source, staging, dirs_exist_ok=True)
        files = {}
        for name, data in modifications.items():
            archive.replace(name, data, staging)
            if archive.entry(name).get("unpacked"):
                rel = "resources/app.asar.unpacked/" + name
                files[rel] = C.sha256(staging / rel)
        after = archive.save(staging / "resources/app.asar")
        executable = patch_executable((source / EXE).read_bytes(), digest(archive.header_bytes), after)
        C.write_bytes(staging / EXE, executable)
        files[EXE] = digest(executable)
        files["resources/app.asar"] = C.sha256(staging / "resources/app.asar")
        manifest = {"version": version, "source": str(source), "source_sha256": source_hash,
                    "profile_sha256": profile_hash, "patch_revision": PATCH_REVISION, "files": files,
                    "integrity_fuses_changed": False, "vendor_installation_modified": False}
        C.write_json(staging / "engineering-manifest.json", manifest)
        staging.rename(target)
    except BaseException:
        # Only remove this invocation's freshly created staging directory.
        if staging.parent == parent and staging.name.startswith(".building-") and staging.exists():
            shutil.rmtree(staging)
        raise
    result = install.apply(workspaces=workspaces)
    if shortcuts:
        install_shortcuts(target / EXE, cfg)
    C.write_json(C.state_dir(cfg) / "engineering.json", {**manifest, "edition": str(target)})
    return {"edition": str(target), "version": version, "reused": False,
            "config_actions": len(result["actions"])}
