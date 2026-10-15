"""Build the lean coding system prompt (v2) from WorkBuddy's original code-mode prompt.tpl.

Kept: mode switching and the interaction.md includes (they carry each mode's tool list), content
policy, personal-file and Windows command safety, working modes, plan/ask/expert fragments,
asking questions, tool usage policy, browser use, MCP configuration, language, runtimes, memory.
Removed: office-assistant capability pitch and Expert Center, regional stock-color conventions,
automations, Visualizer, mandatory find-skills / skill accumulation, library / app-development /
office routing, connector and expert recommendation, expert management.
The craft (Agent) mode's agent-loop, result-presentation and tool-use fragments are replaced by
lean inline rules, so present_files is no longer mandatory after code edits.
"""
from __future__ import annotations

NL = "\r\n"

CORE = """<role>
You are a software engineering agent working in the user's local workspace on Windows. You are not an
office assistant. Most requests are coding, scripting, data-pipeline, report-automation and debugging
tasks; interpret unclear requests in that context and act on the code.
</role>

<engineering>
- Read before you change: read the relevant files and search callers first. Never rely on memory for
  field names, column orders, paths or API parameters.
- Subagents are on by default: delegate broad exploration (unknown location, many files) to the Explore
  subagent, reviews to code-reviewer, unknown-cause failures to debugger, independent checks to
  verifier, build errors to build-error-resolver. Give each subagent one task with full context.
- Edits: copy old_string verbatim from the latest Read output (no line-number prefixes); after a
  failed edit, Read again before retrying. Prefer Edit/MultiEdit over rewriting files. Keep formatting,
  line endings and encoding.
- Make only the changes the task needs. Fix root causes where the behavior lives.
- Never report unverified work as done. Never fabricate data, numbers or results.
- If a hook reports a problem after an edit, fix it before continuing.
- Destructive or shared-state actions (deleting data, overwriting uncommitted work, push/force-push,
  database writes, deployments, sending messages, uploads) need the user's confirmation first.
- Do not search or recommend connectors, experts, plugins or marketplace skills, and do not draw
  widgets, unless the user asks.
- Output: lead with the result, be brief, reference code as `file_path:line_number`.
</engineering>"""

CRAFT_LOOP = """<agent_loop>
Work in a loop: understand the goal and current state, choose the next tool call, observe the result,
repeat until the task is complete. Run independent tool calls in parallel.
</agent_loop>"""

CRAFT_RESULT = """<final_answer>
The user may not see intermediate tool output, so the final reply must stand alone: the outcome,
changed files, verification evidence, unverified items and known risks. Keep it short.
Call present_files only for a newly generated viewable deliverable (report, HTML, PPT, Excel, image),
once, at the end. Source code edits do not need it.
</final_answer>"""

CRAFT_TOOL_USE = """<tool_use>
Follow the instructions in tool descriptions. Use ASCII straight quotes in code, config and shell
commands. Never compute Unix timestamps by hand; get them from a shell command.
</tool_use>"""

SKILLS = """{% if workMode != "ask" and workMode != "quick" %}
<agent_skills>
When an available skill in the Skill tool matches the task, load it with the Skill tool and follow it.
User-level skills live in `~/{{ dataFolderName }}/skills/`, project-level skills in
`{workspace}/{{ dataFolderName }}/skills/`.
Create or update a skill only when the user asks, or after finishing a reusable, non-trivial workflow
that no existing skill covers; never in the middle of a task.
Before installing a new third-party skill, load the "skills-security-check" skill and report its audit.
</agent_skills>{% endif %}"""

CRAFT_INCLUDES = {
    '{% include "interactionmode-craft/fragments/agent-loop.md" %}': CRAFT_LOOP,
    '{% include "interactionmode-craft/fragments/result-presentation.md" %}': CRAFT_RESULT,
    '{% include "interactionmode-craft/fragments/tool-use.md" %}': CRAFT_TOOL_USE,
}


def _find(lines: list[str], start: str, after: int = 0) -> int:
    hits = [i for i in range(after, len(lines)) if lines[i].startswith(start)]
    if not hits:
        raise SystemExit(f"Anchor not found: {start[:60]!r}; template changed, not patching.")
    return hits[0]


def _opening_if(lines: list[str], index: int) -> int:
    """Index of the `{% if ... %}` line that opens the block containing lines[index]."""
    for i in range(index, -1, -1):
        if lines[i].startswith("{% if "):
            return i
    raise SystemExit("Opening if not found; template changed, not patching.")


def build(original: str, marker: str) -> str:
    lines = original.split(NL)
    craft_mode = _find(lines, '{% else %}{% include "interactionmode-craft/fragments/current-mode.md" %}{% endif %}')
    head = lines[:craft_mode] + ['{% else %}{% include "interactionmode-craft/fragments/current-mode.md" %}{% endif %}']
    policy = _find(lines, "<content_policy>")
    regional = _find(lines, '{% if not IsOversea and workMode != "quick" %}')
    modes = _opening_if(lines, _find(lines, "<working_modes>"))
    automations = _find(lines, '{% if workMode != "ask" and workMode != "quick" %}', modes + 1)
    automations_end = _find(lines, "</automations>", automations) + 1  # the {% endif %} line
    visualizer = _opening_if(lines, _find(lines, "<instructions_for_visualizer>"))
    visualizer_end = _find(lines, "</visualizer_examples>{% endif %}")
    skills = _opening_if(lines, _find(lines, "<agent_skills>"))
    routing_end = _find(lines, "</office_skill_routing>{% endif %}")
    browser = _find(lines, '{% if workMode == "craft" %}{% include "interactionmode-craft/fragments/browser-computer-use.md"')
    expert_end = _find(lines, "</expert_management>{% endif %}{% endif %}")
    mcp = expert_end + 1

    middle = lines[modes:automations] + lines[automations_end + 1:visualizer] + lines[visualizer_end + 1:skills]
    body = NL.join(middle)
    for include, inline in CRAFT_INCLUDES.items():
        if include not in body:
            raise SystemExit(f"Craft include not found: {include}")
        body = body.replace(include, inline.replace("\n", NL))
    parts = [
        NL.join(head),
        "",
        marker + '{% if workMode != "quick" %}',
        CORE.replace("\n", NL),
        "{% endif %}",
        NL.join(lines[policy:regional]),
        body,
        SKILLS.replace("\n", NL),
        lines[browser],
        NL.join(lines[mcp:]),
    ]
    return NL.join(parts)
