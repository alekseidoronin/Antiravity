#!/usr/bin/env python3
"""Fix Code node: return single object instead of array for Run Once for Each Item."""
import json
import sys

with open("nodes_export.json", "r", encoding="utf-8") as f:
    nodes = json.load(f)

NEW_CODE = """const esc = (s) => (s || '')
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
        n["parameters"]["jsCode"] = NEW_CODE
        break

print(json.dumps(nodes))
