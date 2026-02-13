#!/usr/bin/env python3
"""Add timeout and Retry on Fail to amocrm: Получить links and amocrm: Файл с drive."""
import json

with open("nodes_amocrm.json", "r", encoding="utf-8") as f:
    nodes = json.load(f)

for n in nodes:
    name = n.get("name", "")
    if "Получить links" in name or "Файл с drive" in name:
        params = n.setdefault("parameters", {})
        opts = params.setdefault("options", {})
        opts["timeout"] = 30000  # 30 sec
        opts["retry"] = {"maxTries": 3, "waitBetweenTries": 2000}
        # n8n HTTP Request: settings for Retry on Fail
        if "settings" not in n:
            n["settings"] = {}
        n["settings"]["retryOnFail"] = True
        n["settings"].setdefault("maxTries", 3)
        n["settings"].setdefault("waitBetweenTries", 2000)

print(json.dumps(nodes))
