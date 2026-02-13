#!/usr/bin/env python3
"""1) Code: full MarkdownV2 escaping so bold works. 2) Telegram: remove footer (appendAttribution=false)."""
import json

with open("nodes_latest.json", "r", encoding="utf-8") as f:
    nodes = json.load(f)

# Full Telegram MarkdownV2 escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
NEW_JS = """const esc = (s) => (s || '')
  .replace(/_/g, '\\\\_')
  .replace(/\\*/g, '\\\\*')
  .replace(/\\[/g, '\\\\[')
  .replace(/]/g, '\\\\]')
  .replace(/\\(/g, '\\\\(')
  .replace(/\\)/g, '\\\)')
  .replace(/~/g, '\\\\~')
  .replace(/`/g, '\\\\`')
  .replace(/>/g, '\\\\>')
  .replace(/#/g, '\\\\#')
  .replace(/\\+/g, '\\\\+')
  .replace(/-/g, '\\\\-')
  .replace(/=/g, '\\\\=')
  .replace(/\\|/g, '\\\\|')
  .replace(/\\{/g, '\\\\{')
  .replace(/}/g, '\\\\}')
  .replace(/\\./g, '\\\\\.')
  .replace(/!/g, '\\\\!');

const item = $input.item.json;

return {
  json: {
    ...item,
    summary_safe: esc(item.summary),
    outcome_safe: esc(item.outcome),
    good_points_safe: esc(item.good_points),
    next_step_safe: esc(item.next_step),
    advice_safe: esc(item.advice),
  },
};
"""

for n in nodes:
    if n.get("name") == "Code in JavaScript":
        n["parameters"]["jsCode"] = NEW_JS
    if n.get("name") == "Send a text message":
        n["parameters"]["additionalFields"] = {"appendAttribution": False}

print(json.dumps(nodes))
