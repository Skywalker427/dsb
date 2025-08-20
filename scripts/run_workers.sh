#!/bin/bash
set -e

# Load environment variables
if [ -f .env.local ]; then
    export $(cat .env.local | grep -v '^#' | xargs)
elif [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "⚠️  No environment file found. Please create .env.local or .env"
    exit 1
fi

# Activate virtual environment if not active
if [[ "$VIRTUAL_ENV" == "" ]]; then
    source .venv/bin/activate
fi

echo "🔄 Starting DSB Background Workers..."
echo "📍 Workers will process jobs from the database queue"
echo "⚠️  Make sure the database is running and migrations are applied"

# Run the worker runner
export PYTHONPATH="/home/junaid/Documents/code/innovation village/dsb"
python -m app.workers.worker_runner