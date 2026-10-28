"""Exercise program patch boundaries and ASAR/PE serialization independently."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import engineering as E


def make_archive(path: Path, files: dict[str, bytes]) -> None:
    root = {"files": {}}
    body = b""
    for name, data in files.items():
        node = root
        parts = name.split("/")
        for part in parts[:-1]:
            node = node["files"].setdefault(part, {"files": {}})
        node["files"][parts[-1]] = {"offset": str(len(body)), "size": len(data),
            "integrity": {"algorithm": "SHA256", "hash": E.digest(data), "blockSize": 16,
                          "blocks": [E.digest(data[i:i + 16]) for i in range(0, len(data), 16)]}}
        body += data
    header = json.dumps(root, separators=(",", ":")).encode()
    payload = struct.pack("<I", len(header)) + header
    payload += b"\0" * (-len(payload) % 4)
    pickle_header = struct.pack("<I", len(payload)) + payload
    path.write_bytes(struct.pack("<II", 4, len(pickle_header)) + pickle_header + body)


class ProgramPatchTest(unittest.TestCase):
    def test_running_app_rejects_build_before_config_or_copy_work(self):
        with patch.object(E, "_running_workbuddy_pids", return_value=[123]), \
             patch.object(E, "_source_dir") as source:
            with self.assertRaisesRegex(ValueError, "PID: 123"):
                E.build()
            source.assert_not_called()

    def test_unknown_or_duplicate_anchors_never_succeed(self):
        for data in (b"unknown vendor code", b"anchor anchor"):
            with self.assertRaises(ValueError):
                E.replace_once(data, b"anchor", b"patched", "fixture")
        with self.assertRaises(ValueError):
            E.patch_server(b"new vendor implementation")

    def test_plugin_skill_override_bypass_is_removed(self):
        source = (b'function resolveSkillOverrideState(t,i){if(isPluginSkill(t))return"on";let n=i?.[t.name];return n}'
                  b'return i||(this.enabledPluginsCache=n),n}getSettingsScopePriority')
        actual = E.patch_cli(source)
        self.assertNotIn(b'isPluginSkill(t))return"on"', actual)
        self.assertIn(b'let n=i?.[t.name];return n', actual)
        if shutil.which("node"):
            # Builtin (plugin) ecosystem skills are forced off; a user's own same-named skill is not.
            probe = b"function isPluginSkill(t){return t.plugin}" + actual.split(b"for(let id of")[0] + (
                b'console.log(resolveSkillOverrideState({name:"library",plugin:1},{library:"on"}),'
                b'resolveSkillOverrideState({name:"skill-creator"},{"skill-creator":"on"}),'
                b'resolveSkillOverrideState({name:"mine",plugin:1},{mine:"on"}))')
            result = subprocess.run([shutil.which("node")], input=probe, capture_output=True, timeout=10)
            self.assertEqual(result.stdout.strip(), b"off on on", result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_coding_profile_wins_account_reenable_and_preserves_custom_plugins(self):
        for engine, variable, condition, scope in (("desktop", "r", "n", "Q.CLI"),
                                                   ("cli", "n", "i", "tv.I7.CLI")):
            with self.subTest(engine=engine):
                source = ("class Manager{async getEnabledPlugins(){let " + condition + "=true," + variable +
                    '= {"ardot@workbuddy-builtin":{enabled:true},"mcp-miora@workbuddy-builtin":{enabled:true},'
                    '"custom@example":{enabled:true},"private@example":{enabled:false}};return ' + condition +
                    "||(this.enabledPluginsCache=" + variable + ")," + variable +
                    "}getSettingsScopePriority(){}}")
                patched = E._enforce_plugin_profile(source.encode(), engine)
                probe = b'''const Q={CLI:'cli'},tv={I7:Q};(async()=>{
const p=await new Manager().getEnabledPlugins();
for(const id of ['ardot@workbuddy-builtin','mcp-miora@workbuddy-builtin'])
if(p[id].enabled!==false||p[id].scope!=='cli')throw Error('preset lost');
if(!p['custom@example'].enabled||p['private@example'].enabled)throw Error('custom preference changed');
console.log('PLUGIN_PROFILE_OK');})().catch(e=>{console.error(e);process.exit(1)});'''
                result = subprocess.run([shutil.which("node")], input=patched + probe, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(b"PLUGIN_PROFILE_OK", result.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_updater_never_restores_downloads_or_runs_installer(self):
        source = b'''class Base {
async checkForceUpgrade(){throw Error('force check ran')}
async checkStartupForceAutoUpdate(){throw Error('startup download ran')}
async quitAndInstallForStartup(){throw Error('startup installer ran')}
}
class Updater extends Base {
async waitForStartupRestore(){await this.startupRestorePromise}
async restoreDownloadedUpdate(){let e;throw Error('cached download restored')}
async checkForUpdates(e=!1){if(this.checkInProgress){throw Error('check ran')}}
async downloadUpdate(e){let t=e.productVersion;throw Error('download ran')}
quitAndInstall(){if(this.fileLogger.info('install'))throw Error('installer ran')}
setState(state){this.state=state}
}'''
        patched = E.patch_windows_updater(source)
        probe = b'''
(async()=>{const u=new Updater();
await u.restoreDownloadedUpdate();await u.checkForUpdates(true);await u.downloadUpdate({});
await u.checkForceUpgrade();await u.checkStartupForceAutoUpdate();
if(u.state!=='idle'||u.quitAndInstall()!==false||await u.quitAndInstallForStartup()!==false)throw Error('wrong update state');
console.log('UPDATER_DISABLED');})().catch(e=>{console.error(e);process.exit(1)});
'''
        result = subprocess.run([shutil.which("node")], input=patched + probe, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"UPDATER_DISABLED", result.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_conversation_launcher_gets_coding_tools(self):
        """Prewarm/daemon path: vendor tools never reach the CLI; read-only modes keep their list."""
        source = b'''function buildConversationAgentCliArgs(e,t){let n=[];e.tools!==void 0&&n.push(`--tools`,e.tools);return n}
function launch(A){let N=A.tools?A.tools.split(`,`).map(e=>e.trim()):void 0;return{N,args:buildConversationAgentCliArgs(A)}}'''
        patched = E.patch_conversation_tools(source)
        probe = b'''
for(const vendor of ['A2ACancelTask,SkillManage,show_widget,Write,Read',undefined]){
const r=launch({tools:vendor});
const tools=r.args[r.args.indexOf('--tools')+1];
if(!tools||tools.includes('A2A')||tools.includes('SkillManage')||!tools.startsWith('Agent,'))throw Error('vendor tools kept: '+tools);
if(r.N.join(',')!==tools)throw Error('product config env diverged');
if(!tools.includes('Defer(PowerShell)')||!tools.includes('Defer(TeamCreate)'))throw Error('deferred tools missing');}
const ask=launch({tools:'Read,Grep,Glob'});
if(ask.args[1]!=='Read,Grep,Glob')throw Error('read-only mode got write tools');
console.log('LAUNCHER_OK');'''
        result = subprocess.run([shutil.which("node")], input=patched + probe, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"LAUNCHER_OK", result.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_session_mcp_source_drops_ecosystem_servers_for_both_transports(self):
        """The server map feeds both --mcp-config and the ACP session/new list; filter it once."""
        source = (b"function resolve(y,c){let d=[],cfg;let applyConfig=e=>{if(!e)return;"
                  b"cfg=JSON.stringify(e.servers);d=Object.keys(e.servers).map(name=>({name}))};applyConfig(y);"
                  b"let E=new Set(d.map(e=>e.name)),D=[...c.filter(n=>!E.has(n.name)||!1),...d];return{cfg,D}}")
        patched = E.patch_session_mcp(source)
        probe = b'''
const r=resolve({servers:{context7:{},weixinpay:{},sheetagent:{},'space-library':{}}},[{name:'proj'},{name:'miora'}]);
if(Object.keys(JSON.parse(r.cfg)).join()!=='context7')throw Error('config '+r.cfg);
if(r.D.map(x=>x.name).join()!=='proj,context7')throw Error('acp '+JSON.stringify(r.D));
console.log('MCP_OK');'''
        result = subprocess.run([shutil.which("node")], input=patched + probe, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"MCP_OK", result.stdout)

    def test_tool_profile_keeps_hot_path_resident_and_defers_the_rest(self):
        specs = E.C.CODE_TOOLS.split(",")
        self.assertEqual(len(specs), len(set(specs)))
        for name in ("Agent", "Bash", "Read", "Edit", "Write", "Grep", "Glob", "ToolSearch", "DeferExecuteTool"):
            self.assertIn(name, specs)
        for name in ("PowerShell", "SendMessage", "TeamCreate", "NotebookEdit", "EnterPlanMode",
                     "EnterWorktree", "LeaveWorktree", "Monitor"):
            self.assertIn(f"Defer({name})", specs)
        self.assertIn("ExitPlanMode", specs)
        # The 5.8.4 engine has no Workflow tool class; listing it only sends the model on failed searches.
        self.assertFalse(any("Workflow" in spec for spec in specs))

    def test_craft_mode_declares_the_same_tool_profile(self):
        """The engine intersects --tools with the work-mode frontmatter list."""
        text = E.C.CRAFT_INTERACTION.decode("utf-8")
        self.assertTrue(text.startswith("---\nname: craft\n") and text.endswith("---\n"))
        declared = [line[4:] for line in text.splitlines() if line.startswith("  - ")]
        self.assertEqual(declared, E.C.CODE_TOOLS.split(","))
        self.assertEqual(E.CRAFT, "resources/plugins/workbuddy-builtin/interactionmode/craft/fragments/interaction.md")
        for vendor in ("A2ASendMessage", "SkillManage", "show_widget", "widget_guidelines", "ImageGen"):
            self.assertFalse(any(vendor in spec for spec in declared), vendor)

    def test_turn_identity_template_carries_profile_not_product_persona(self):
        text = (E.C.PROFILE / "prompt/user-context-identity.tpl").read_text(encoding="utf-8")
        for kept in ("SoulContent", "IdentityContent", "UserContent", "ToneStyleContent", "UserCustomPrompt"):
            self.assertIn(kept, text)
        for dropped in ("product_identity", "BOOTSTRAP", "embody its persona", "powerful AI assistant"):
            self.assertNotIn(dropped, text)
        self.assertEqual(E.IDENTITY, "resources/templates/user-context-identity.tpl")

    def test_connector_status_reminder_is_dropped(self):
        source = (b"function renderConnectorStatusBlock(e){return!e||e.length===0?[]:[`<connector-status>`]}"
                  b"console.log(JSON.stringify(renderConnectorStatusBlock([{configId:1}])))")
        patched = E.patch_turn_context(source)
        if shutil.which("node"):
            result = subprocess.run([shutil.which("node")], input=patched, capture_output=True, timeout=10)
            self.assertEqual(result.stdout.strip(), b"[]", result.stderr)

    def test_archive_growth_preserves_other_entries_and_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.asar"
            make_archive(source, {"main/server.js": b"old", "untouched.txt": b"original bytes"})
            original = source.read_bytes()
            archive = E.Archive(source)
            changed = b"/* a much longer patch */ 42;"
            archive.replace("main/server.js", changed, root)
            target = root / "target.asar"
            new_digest = archive.save(target)
            rebuilt = E.Archive(target)
            self.assertEqual(rebuilt.read("main/server.js"), changed)
            self.assertEqual(rebuilt.read("untouched.txt"), b"original bytes")
            self.assertEqual(rebuilt.entry("main/server.js")["integrity"]["hash"], E.digest(changed))
            self.assertEqual(E.digest(rebuilt.header_bytes), new_digest)
            self.assertEqual(source.read_bytes(), original)

    def test_archive_rejects_corrupt_source_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.asar"
            make_archive(source, {"main/server.js": b"original"})
            archive = E.Archive(source)
            archive.body[0] = 0
            with self.assertRaises(ValueError):
                archive.replace("main/server.js", b"patched", Path(directory))

    def test_pe_patch_changes_only_matching_resource_hashes(self):
        old, new = "a" * 64, "b" * 64
        data = bytearray(2048)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 0x3C, 128)
        data[128:132] = b"PE\0\0"
        struct.pack_into("<H", data, 134, 1)
        struct.pack_into("<H", data, 148, 224)
        at = 128 + 24 + 224
        data[at:at + 8] = b".rsrc\0\0\0"
        struct.pack_into("<II", data, at + 16, 1024, 1024)
        records = b"".join(b'{"file":"resources\\\\app.asar","alg":"' + alg +
                           b'","value":"' + old.encode() + b'"}' for alg in (b"SHA256", b"sha256"))
        data[1024:1024 + len(records)] = records
        original = bytes(data)
        actual = E.patch_executable(original, old, new)
        self.assertEqual(actual[:1024], original[:1024])
        self.assertEqual(actual.replace(new.encode(), old.encode()), original)
        with self.assertRaises(ValueError):
            E.patch_executable(original, "c" * 64, new)


if __name__ == "__main__":
    unittest.main()
