# Installation (this project)

This MCP server is installed and built. Node.js is in `../nodejs/` (portable).

## Run manually

```bash
# From this folder, using the run script (uses local Node.js):
./run.sh

# Or with Node in PATH:
node /Users/alekseidoronin/Documents/CURSOR/openai-gpt-image-mcp/dist/index.js
```

## Add to Cursor MCP

1. Open Cursor Settings → **Cursor Settings** → **MCP** (or edit the config file).
2. Add this server (replace `sk-...` with your OpenAI API key):

```json
{
  "mcpServers": {
    "openai-gpt-image-mcp": {
      "command": "/Users/alekseidoronin/Documents/CURSOR/nodejs/bin/node",
      "args": ["/Users/alekseidoronin/Documents/CURSOR/openai-gpt-image-mcp/dist/index.js"],
      "env": { "OPENAI_API_KEY": "sk-..." }
    }
  }
}
```

3. Restart Cursor so MCP picks up the new server.

Your OpenAI key must have **image API** access (verified organization may be required).
