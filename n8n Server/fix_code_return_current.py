#!/usr/bin/env python3
"""Fix Code in JavaScript: return single object instead of array."""
import json

with open("nodes_current.json", "r", encoding="utf-8") as f:
    nodes = json.load(f)

# New code: return single object (no array) for "Run Once for Each Item" mode
NEW_JS = """const esc = (s) => (s || '')
  .replace(/_/g, '\\\\_')
  .replace(/\\*/g, '\\\\*')
  .replace(/\\[/g, '\\\\[')
  .replace(/]/g, '\\\\]')
  .replace(/\\(/g, '\\\\(')
  .replace(/\\)/g, '\\\\)')
  .replace(/`/g, '\\\\`');

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
        break

print(json.dumps(nodes))
