#!/usr/bin/env python3
"""List tables in the DB that the app would connect to. Run from project root with env loaded."""
import asyncio
import os
import sys

# Ensure project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine


async def main():
    url = os.environ.get("DATABASE_URL", "")
    print(f"DATABASE_URL (masked): {url.split('@')[-1] if '@' in url else '(not set)'}")
    async with engine.connect() as conn:
        r = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")
        )
        tables = [row[0] for row in r.fetchall()]
    print(f"Tables in public: {tables or '(none)'}")
    return 0 if tables else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
