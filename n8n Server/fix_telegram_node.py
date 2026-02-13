#!/usr/bin/env python3
"""Fix Telegram node to use _safe fields (escaped for Markdown) so Telegram does not fail."""
import json
import sys

with open("nodes_export.json", "r", encoding="utf-8") as f:
    nodes = json.load(f)

NEW_TEXT = """=📞 *Разбор звонка* Файл:  {{ $('Webhook').item.json.body['leads[note][0][note][text]'] }}

📝 *Кратко:* {{ $json.summary_safe }}

📊 Оценка: {{ $json.manager_score }}/10

*Вердикт*: {{ $json.outcome_safe }}

👍 *Что сделано круто:* {{ $json.good_points_safe }}

⚠️ *Зоны роста:* {{ $json.next_step_safe }}

✅ *Совет:* {{ $json.advice_safe }}

🔗 *Ссылка на запись* {{ $('AssemblyAI: Получаем транскрибацию').item.json.audio_url }}"""

for n in nodes:
    if n.get("name") == "Send a text message":
        n["parameters"]["text"] = NEW_TEXT
        break

print(json.dumps(nodes))
