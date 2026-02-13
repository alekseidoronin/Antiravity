# Проверка MCP-серверов

Скрипт `check-mcp.sh` проверяет доступность серверов из `~/.cursor/mcp.json` и пишет результат в `scripts/logs/mcp-check.log`.

**Как читать результат:**
- **URL-серверы (context7, supabase):** HTTP 401/406 часто означают «сервер доступен, но ждёт авторизацию или MCP-рукопожатие» — в Cursor при логине это норма.
- **stdio-серверы (playwright, postgres и т.д.):** «exited early» при запуске без MCP-клиента возможно — скрипт только проверяет, что команда запускается. Реальная работа проверяется в Cursor (Settings → Tools & MCP).

## Запуск вручную

```bash
cd /Users/alekseidoronin/Documents/CURSOR/scripts
chmod +x check-mcp.sh
./check-mcp.sh
```

Лог: `scripts/logs/mcp-check.log`

## Запуск по расписанию (macOS)

Чтобы скрипт запускался каждые 15 минут:

1. Создайте файл `~/Library/LaunchAgents/com.cursor.mcp-check.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.cursor.mcp-check</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/alekseidoronin/Documents/CURSOR/scripts/check-mcp.sh</string>
  </array>
  <key>StartInterval</key>
  <integer>900</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/Users/alekseidoronin/Documents/CURSOR/scripts/logs/mcp-check-stdout.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/alekseidoronin/Documents/CURSOR/scripts/logs/mcp-check-stderr.log</string>
</dict>
</plist>
```

2. Загрузите задачу:

```bash
launchctl load ~/Library/LaunchAgents/com.cursor.mcp-check.plist
```

3. Остановить: `launchctl unload ~/Library/LaunchAgents/com.cursor.mcp-check.plist`

**Важно:** скрипт только проверяет доступность и пишет в лог. Он **не перезапускает Cursor** и не перезапускает MCP внутри Cursor — это делается только вручную (перезапуск Cursor или отключение/включение сервера в Settings → Tools & MCP).
