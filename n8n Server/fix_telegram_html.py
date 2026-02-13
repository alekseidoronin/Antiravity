#!/usr/bin/env python3
"""Use HTML in Telegram: <b> for bold, HTML-escape content. Fixes bold for all headers."""
import json

with open("nodes_now.json", "r", encoding="utf-8") as f:
    nodes = json.load(f)

# HTML escape only: & < >
# Also get filename and audio_url from other nodes and add _safe versions
NEW_JS = """const htmlEsc = (s) => (s || '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;');

const item = $input.item.json;
let filename = '';
let audioUrl = '';
try {
  filename = $('Webhook').item.json.body['leads[note][0][note][text]'] || '';
} catch (e) {}
try {
  audioUrl = $('AssemblyAI: Получаем транскрибацию').item.json.audio_url || '';
} catch (e) {}

return {
  json: {
    ...item,
    summary_safe: htmlEsc(item.summary),
    outcome_safe: htmlEsc(item.outcome),
    good_points_safe: htmlEsc(item.good_points),
    next_step_safe: htmlEsc(item.next_step),
    advice_safe: htmlEsc(item.advice),
    filename_safe: htmlEsc(filename),
    audio_url_safe: htmlEsc(audioUrl),
  },
};
"""

# Telegram: HTML tags for bold, use _safe fields, parse_mode HTML
NEW_TELEGRAM_TEXT = """=📞 <b>Разбор звонка</b> Файл: {{ $json.filename_safe }}

📝 <b>Кратко:</b> {{ $json.summary_safe }}

📊 Оценка: {{ $json.manager_score }}/10

<b>Вердикт</b>: {{ $json.outcome_safe }}

👍 <b>Что сделано круто:</b> {{ $json.good_points_safe }}

⚠️ <b>Зоны роста:</b> {{ $json.next_step_safe }}

✅ <b>Совет:</b> {{ $json.advice_safe }}

🔗 <b>Ссылка на запись</b> {{ $json.audio_url_safe }}"""

for n in nodes:
    if n.get("name") == "Code in JavaScript":
        n["parameters"]["jsCode"] = NEW_JS
    if n.get("name") == "Send a text message":
        n["parameters"]["text"] = NEW_TELEGRAM_TEXT
        n["parameters"]["additionalFields"] = {
            "appendAttribution": False,
            "parse_mode": "HTML",
        }

print(json.dumps(nodes))
