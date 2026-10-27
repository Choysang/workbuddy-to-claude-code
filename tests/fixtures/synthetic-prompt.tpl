{# Synthetic template contract; no vendor prompt text. #}
{% if workMode == "ask" %}
{% include "interactionmode-ask/fragments/interaction.md" %}
{% elif workMode == "plan" %}
{% include "interactionmode-plan/fragments/interaction.md" %}
{% elif workMode == "expert" %}
{% include "interactionmode-expert/fragments/interaction.md" %}
{% elif workMode == "quick" %}
{% include "interactionmode-quick/fragments/interaction.md" %}
{% else %}{% include "interactionmode-craft/fragments/current-mode.md" %}{% endif %}
<content_policy>
Synthetic policy retained by the transformation.
</content_policy>
{% if not IsOversea and workMode != "quick" %}
Synthetic regional content.
{% endif %}
{% if workMode != "quick" %}
<working_modes>
{% include "interactionmode-craft/fragments/interaction.md" %}
{% include "interactionmode-craft/fragments/agent-loop.md" %}
{% include "interactionmode-craft/fragments/result-presentation.md" %}
{% include "interactionmode-craft/fragments/tool-use.md" %}
</working_modes>
{% endif %}
{% if workMode != "ask" and workMode != "quick" %}
<automations>
Synthetic removed content.
</automations>
{% endif %}
{% if workMode == "craft" %}
<instructions_for_visualizer>
Synthetic removed content.
</instructions_for_visualizer>
<visualizer_examples>
</visualizer_examples>{% endif %}
{% if workMode != "quick" %}
<agent_skills>
Synthetic removed content.
</agent_skills>
<office_skill_routing>
</office_skill_routing>{% endif %}
{% if workMode == "craft" %}{% include "interactionmode-craft/fragments/browser-computer-use.md" %}{% endif %}
{% if workMode != "quick" %}{% if enabled %}
<expert_management>
Synthetic plugin-recommendation content.
</expert_management>{% endif %}{% endif %}
<runtime_context>Retained synthetic context.</runtime_context>
