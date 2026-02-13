#!/bin/bash
# Run openai-gpt-image-mcp with local Node.js
DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$DIR/../nodejs/bin:$PATH"
exec node "$DIR/dist/index.js" "$@"
