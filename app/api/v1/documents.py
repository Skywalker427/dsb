from fastapi import APIRouter

router = APIRouter()

# Placeholder for documents endpoints
@router.get("")
async def get_documents():
    """Get all documents."""
    return {"message": "Documents endpoint - to be implemented"}

@router.post("")
async def create_document():
    """Create a new document."""
    return {"message": "Create document endpoint - to be implemented"}