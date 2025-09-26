"""Add embedding columns and HNSW indexes conditionally

Revision ID: 11ebc65f12e8
Revises: e559d894bf79
Create Date: 2025-09-26 14:09:22.316248

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '11ebc65f12e8'
down_revision = 'e559d894bf79'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension if it doesn't exist
    conn = op.get_bind()
    
    # Check if pgvector extension exists
    result = conn.execute(sa.text("""
        SELECT extname 
        FROM pg_extension 
        WHERE extname = 'vector'
    """)).fetchone()
    
    if not result:
        print("Creating pgvector extension...")
        op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    else:
        print("pgvector extension already exists, skipping...")
    
    # Check and add embedding column to suggestions table if it doesn't exist
    
    # Check if embedding column exists in suggestions table
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'suggestions' 
        AND column_name = 'embedding'
        AND table_schema = 'public'
    """)).fetchone()
    
    if not result:
        print("Adding embedding column to suggestions table...")
        op.execute('ALTER TABLE suggestions ADD COLUMN embedding vector(1536)')
        
        # Create HNSW index for suggestions
        print("Creating HNSW index for suggestions...")
        op.execute("""
            CREATE INDEX suggestions_embedding_hnsw_idx 
            ON suggestions USING hnsw (embedding vector_cosine_ops) 
            WITH (m = 16, ef_construction = 128)
        """)
    else:
        print("Embedding column already exists in suggestions table, skipping...")
    
    # Check and add embedding column to topics table if it doesn't exist
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'topics' 
        AND column_name = 'embedding'
        AND table_schema = 'public'
    """)).fetchone()
    
    if not result:
        print("Adding embedding column to topics table...")
        op.execute('ALTER TABLE topics ADD COLUMN embedding vector(1536)')
        
        # Create HNSW index for topics
        print("Creating HNSW index for topics...")
        op.execute("""
            CREATE INDEX topics_embedding_hnsw_idx 
            ON topics USING hnsw (embedding vector_cosine_ops) 
            WITH (m = 16, ef_construction = 128)
        """)
    else:
        print("Embedding column already exists in topics table, skipping...")


def downgrade() -> None:
    # Remove HNSW indexes if they exist
    conn = op.get_bind()
    
    # Check and remove suggestions index
    result = conn.execute(sa.text("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'suggestions' 
        AND indexname = 'suggestions_embedding_hnsw_idx'
        AND schemaname = 'public'
    """)).fetchone()
    
    if result:
        print("Dropping HNSW index for suggestions...")
        op.execute('DROP INDEX IF EXISTS suggestions_embedding_hnsw_idx')
    
    # Check and remove topics index
    result = conn.execute(sa.text("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'topics' 
        AND indexname = 'topics_embedding_hnsw_idx'
        AND schemaname = 'public'
    """)).fetchone()
    
    if result:
        print("Dropping HNSW index for topics...")
        op.execute('DROP INDEX IF EXISTS topics_embedding_hnsw_idx')
    
    # Remove embedding columns if they exist
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'suggestions' 
        AND column_name = 'embedding'
        AND table_schema = 'public'
    """)).fetchone()
    
    if result:
        print("Removing embedding column from suggestions table...")
        op.execute('ALTER TABLE suggestions DROP COLUMN embedding')
    
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'topics' 
        AND column_name = 'embedding'
        AND table_schema = 'public'
    """)).fetchone()
    
    if result:
        print("Removing embedding column from topics table...")
        op.execute('ALTER TABLE topics DROP COLUMN embedding')