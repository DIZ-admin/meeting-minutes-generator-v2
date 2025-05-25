# {{ title }}

**Datum:** {{ date }}
**Ort:** {{ location }}
**Sitzungsleiter:** {{ organizer }}

## Teilnehmer
{% for participant in participants %}
- {{ participant.name }}{% if participant.role %} ({{ participant.role }}){% endif %}
{% else %}
- Keine angegeben
{% endfor %}

## Zusammenfassung
{{ summary }}

## Traktanden
{% for item in agenda_items %}
### {{ item.topic }}
**Diskussion:** {{ item.discussion_summary }}

{% if item.decisions_made %}
**Entscheidungen:**
{% for decision in item.decisions_made %}
- {{ decision }}
{% endfor %}
{% endif %}

{% if item.action_items_assigned %}
**Pendenzen:**
{% for action in item.action_items_assigned %}
- {{ action.what }} (Verantwortlich: {{ action.who }}{% if action.due %}, Frist: {{ action.due }}{% endif %})
{% endfor %}
{% endif %}

{% else %}
Keine Traktanden angegeben
{% endfor %}

## Entscheidungen
{% for decision in decisions %}
- {{ decision.description }}{% if decision.id %} (ID: {{ decision.id }}){% endif %}
{% else %}
- Keine erfasst
{% endfor %}

## Pendenzen
{% for action in action_items %}
- {{ action.description }} (Verantwortlich: {{ action.assigned_to }}{% if action.due_date %}, Frist: {{ action.due_date }}{% endif %}{% if action.status %}, Status: {{ action.status }}{% endif %}{% if action.action_id %}, ID: {{ action.action_id }}{% endif %})
{% else %}
- Keine erfasst
{% endfor %}

{% if error %}
## Fehler
- {{ error }}
{% endif %}
