#!/bin/bash
set -e

# Load environment variables
if [ -f .env.local ]; then
    export $(cat .env.local | grep -v '^#' | xargs)
else
    echo "⚠️  .env.local not found. Please run './scripts/setup_dev.sh' first."
    exit 1
fi

# Activate virtual environment if not active
if [[ "$VIRTUAL_ENV" == "" ]]; then
    source .venv/bin/activate
fi

echo "🚀 Starting DSB Backend in development mode..."
echo "📍 API will be available at http://localhost:9000"
echo "📚 Documentation at http://localhost:9000/docs"

# Run with auto-reload for development
uv run uvicorn app.main:app \
    --reload \
    --host 0.0.0.0 \
    --port 9000 \
    --log-level debug \
    --env-file .env.local