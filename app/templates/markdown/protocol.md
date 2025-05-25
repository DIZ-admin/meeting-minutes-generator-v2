# {{ title }}

**Date:** {{ date }}
**Location:** {{ location }}
**Organizer:** {{ organizer }}

## Participants
{% for participant in participants %}
- {{ participant.name }}{% if participant.role %} ({{ participant.role }}){% endif %}
{% else %}
- None listed
{% endfor %}

## Summary
{{ summary }}

## Agenda Items
{% for item in agenda_items %}
### {{ item.topic }}
**Discussion Summary:** {{ item.discussion_summary }}

{% if item.decisions_made %}
**Decisions:**
{% for decision in item.decisions_made %}
- {{ decision }}
{% endfor %}
{% endif %}

{% if item.action_items_assigned %}
**Action Items:**
{% for action in item.action_items_assigned %}
- {{ action.what }} (Assigned to: {{ action.who }}{% if action.due %}, Due: {{ action.due }}{% endif %})
{% endfor %}
{% endif %}

{% else %}
No agenda items listed
{% endfor %}

## Decisions
{% for decision in decisions %}
- {{ decision.description }}{% if decision.id %} (ID: {{ decision.id }}){% endif %}
{% else %}
- None recorded
{% endfor %}

## Action Items
{% for action in action_items %}
- {{ action.description }} (Assigned to: {{ action.assigned_to }}{% if action.due_date %}, Due: {{ action.due_date }}{% endif %}{% if action.status %}, Status: {{ action.status }}{% endif %}{% if action.action_id %}, ID: {{ action.action_id }}{% endif %})
{% else %}
- None recorded
{% endfor %}

{% if error %}
## Errors
- {{ error }}
{% endif %}
