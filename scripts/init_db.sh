#!/bin/bash
set -e

# Load environment variables
if [ -f .env.local ]; then
    export $(cat .env.local | grep -v '^#' | xargs)
fi

echo "🗄️  Initializing database..."

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL is not set. Please check your .env.local file."
    exit 1
fi

# Extract database connection details
DB_HOST=$(echo $DATABASE_URL | sed -n 's/.*@\([^:]*\):.*/\1/p')
DB_NAME=$(echo $DATABASE_URL | sed -n 's/.*\/\([^?]*\).*/\1/p')

echo "Database host: $DB_HOST"
echo "Database name: $DB_NAME"

# Enable pgvector extension
echo "Enabling pgvector extension..."
psql $DATABASE_URL -c "CREATE EXTENSION IF NOT EXISTS vector;" || {
    echo "❌ Failed to enable pgvector extension. Make sure PostgreSQL is running and pgvector is installed."
    exit 1
}

# Run migrations
echo "Running migrations..."
alembic upgrade head || {
    echo "❌ Migration failed. Check your database configuration."
    exit 1
}

echo "✅ Database initialized successfully!"