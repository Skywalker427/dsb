"""fix cluster_members primary key constraint

Revision ID: 0b4702574083
Revises: 11ebc65f12e8
Create Date: 2025-09-26 14:44:53.434672

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0b4702574083'
down_revision = '11ebc65f12e8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fix cluster_members primary key constraint
    # Current: PRIMARY KEY (cluster_id) - only allows one member per cluster  
    # Fixed: PRIMARY KEY (cluster_id, suggestion_id, document_id) - allows multiple members
    
    conn = op.get_bind()
    
    # Check if the problematic constraint exists
    result = conn.execute(sa.text("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'cluster_members' 
        AND constraint_type = 'PRIMARY KEY'
        AND constraint_name = 'cluster_members_pkey'
        AND table_schema = 'public'
    """)).fetchone()
    
    if result:
        print("Fixing cluster_members primary key constraint...")
        
        # Drop the existing primary key constraint
        op.execute('ALTER TABLE cluster_members DROP CONSTRAINT cluster_members_pkey')
        
        # Add new composite primary key that allows multiple members per cluster
        # Only using non-null columns since document_id can be NULL
        op.execute('''
            ALTER TABLE cluster_members 
            ADD CONSTRAINT cluster_members_pkey 
            PRIMARY KEY (cluster_id, suggestion_id, added_at)
        ''')
        
        print("✅ Fixed cluster_members primary key constraint")
    else:
        print("Primary key constraint not found or already fixed")


def downgrade() -> None:
    # Revert back to the original (problematic) constraint
    conn = op.get_bind()
    
    result = conn.execute(sa.text("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'cluster_members' 
        AND constraint_type = 'PRIMARY KEY'
        AND table_schema = 'public'
    """)).fetchone()
    
    if result:
        print("Reverting cluster_members primary key constraint...")
        
        # Drop the fixed constraint  
        op.execute('ALTER TABLE cluster_members DROP CONSTRAINT cluster_members_pkey')
        
        # Add back the original (problematic) constraint
        op.execute('''
            ALTER TABLE cluster_members 
            ADD CONSTRAINT cluster_members_pkey 
            PRIMARY KEY (cluster_id)
        ''')
        
        print("⚠️ Reverted to original (problematic) constraint")
    else:
        print("No primary key constraint found to revert")