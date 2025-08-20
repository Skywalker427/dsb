#!/bin/bash
set -e

echo "🚀 Setting up DSB Backend development environment..."

# Check prerequisites
command -v python3 >/dev/null 2>&1 || { echo "Python 3 is required but not installed."; exit 1; }
command -v psql >/dev/null 2>&1 || { echo "PostgreSQL client is required but not installed."; exit 1; }

# Install uv if not present
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    pip install uv
fi

# Setup virtual environment
echo "Creating virtual environment..."
uv venv
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
uv sync

# Copy env file if not exists
if [ ! -f .env.local ]; then
    echo "Creating .env.local from template..."
    cp .env.example .env.local
    echo "⚠️  Please edit .env.local with your database and Redis URLs"
fi

echo "✅ Setup complete! Run './scripts/run_dev.sh' to start the application."