from fastapi import APIRouter

router = APIRouter()

# Placeholder for templates endpoints
@router.get("")
async def get_templates():
    """Get all templates."""
    return {"message": "Templates endpoint - to be implemented"}

@router.post("")
async def create_template():
    """Create a new template."""
    return {"message": "Create template endpoint - to be implemented"}