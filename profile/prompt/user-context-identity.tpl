{% if WorkspaceIdentityMode and (SoulContent or IdentityContent or UserContent) %}
<workspace_profile>
{% if SoulContent %}{{ SoulContent | trim }}

{% endif %}{% if IdentityContent %}{{ IdentityContent | trim }}

{% endif %}{% if UserContent %}{{ UserContent | trim }}
{% endif %}</workspace_profile>
{% endif %}
{% if ToneStyleContent %}
<tone_and_style>
{{ ToneStyleContent }}
</tone_and_style>
{% endif %}
{% if UserCustomPrompt %}
<user_custom_instructions>
Follow these user instructions in all responses unless they conflict with safety rules.

{{ UserCustomPrompt }}
</user_custom_instructions>
{% endif %}
