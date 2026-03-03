from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.templates_repo import TemplateRepository
from app.services.template_processor import template_processor
from app.core.errors import NotFoundError, ValidationError
from app.domain.schemas import (
    ApiResponse,
    TemplateCreate,
    TemplateUpdate,
    TemplateResponse,
    PaginationMeta,
)
from app.core.database import get_db

router = APIRouter()


@router.post("", response_model=ApiResponse, status_code=201)
async def create_template(
    template_data: TemplateCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new template."""
    templates_repo = TemplateRepository(db)
    
    # Check if template name already exists
    existing = await templates_repo.get_by_name(template_data.name)
    if existing:
        raise ValidationError(f"Template with name '{template_data.name}' already exists", "name")
    
    try:
        template = await templates_repo.create(template_data)
        return ApiResponse(
            ok=True,
            data=TemplateResponse.model_validate(template),
        )
    except Exception as e:
        raise ValidationError(f"Failed to create template: {str(e)}")


@router.get("", response_model=ApiResponse)
async def get_templates(
    kind: Optional[str] = Query(None, description="Filter by template kind"),
    active_only: bool = Query(True, description="Show only active templates"),
    search: Optional[str] = Query(None, description="Search in name and description"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """Get all templates with optional filters and pagination."""
    templates_repo = TemplateRepository(db)
    
    # Calculate offset
    offset = (page - 1) * page_size
    
    # Get templates and total count
    templates = await templates_repo.get_all(
        kind=kind,
        active_only=active_only,
        search=search,
        offset=offset,
        limit=page_size,
    )
    total = await templates_repo.count(
        kind=kind,
        active_only=active_only,
        search=search,
    )
    
    # Convert to response models
    template_responses = [TemplateResponse.model_validate(t) for t in templates]
    
    return ApiResponse(
        ok=True,
        data=template_responses,
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ).model_dump(),
    )


@router.get("/kinds", response_model=ApiResponse)
async def get_template_kinds(
    db: AsyncSession = Depends(get_db),
):
    """Get all unique template kinds."""
    templates_repo = TemplateRepository(db)
    kinds = await templates_repo.get_kinds()
    
    return ApiResponse(
        ok=True,
        data=kinds,
    )


@router.get("/{template_id}", response_model=ApiResponse)
async def get_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a template by ID."""
    templates_repo = TemplateRepository(db)
    
    template = await templates_repo.get_by_id(template_id)
    if not template:
        raise NotFoundError(f"Template {template_id} not found", "Template")
    
    return ApiResponse(
        ok=True,
        data=TemplateResponse.model_validate(template),
    )


@router.patch("/{template_id}", response_model=ApiResponse)
async def update_template(
    template_id: UUID,
    updates: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a template."""
    templates_repo = TemplateRepository(db)
    
    # Check if template exists
    existing = await templates_repo.get_by_id(template_id)
    if not existing:
        raise NotFoundError(f"Template {template_id} not found", "Template")
    
    # Check if new name conflicts (if name is being updated)
    if updates.name and updates.name != existing.name:
        name_conflict = await templates_repo.get_by_name(updates.name)
        if name_conflict:
            raise ValidationError(f"Template with name '{updates.name}' already exists", "name")
    
    try:
        # Filter out None values
        update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
        
        template = await templates_repo.update(template_id, **update_data)
        return ApiResponse(
            ok=True,
            data=TemplateResponse.model_validate(template),
        )
    except Exception as e:
        raise ValidationError(f"Failed to update template: {str(e)}")


@router.delete("/{template_id}", response_model=ApiResponse)
async def delete_template(
    template_id: UUID,
    hard_delete: bool = Query(False, description="Permanently delete instead of soft delete"),
    db: AsyncSession = Depends(get_db),
):
    """Delete a template (soft delete by default, hard delete if specified)."""
    templates_repo = TemplateRepository(db)
    
    if hard_delete:
        success = await templates_repo.hard_delete(template_id)
    else:
        success = await templates_repo.delete(template_id)
    
    if not success:
        raise NotFoundError(f"Template {template_id} not found", "Template")
    
    delete_type = "permanently deleted" if hard_delete else "deactivated"
    return ApiResponse(
        ok=True,
        data={"message": f"Template {template_id} {delete_type} successfully"},
    )


@router.post("/upload", response_model=ApiResponse, status_code=201)
async def create_template_from_sample(
    file: UploadFile = File(..., description="Sample document (PDF, Word, or text file)"),
    template_name: str = Form(..., description="Name for the new template"),
    template_description: Optional[str] = Form(None, description="Description of the template"),
    version: str = Form("1.0", description="Template version"),
    kind: str = Form("document", description="Template kind/type"),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a template by uploading a sample document.
    
    The uploaded document is treated as an example that will be converted into a reusable 
    template using AI. The system will identify what parts should become variables for 
    generating documents from suggestion clusters.
    
    Supported formats: PDF (.pdf), Word (.docx, .doc), Text (.txt), Markdown (.md)
    """
    templates_repo = TemplateRepository(db)
    
    # Check if template name already exists
    existing = await templates_repo.get_by_name(template_name)
    if existing:
        raise ValidationError(f"Template with name '{template_name}' already exists", "template_name")
    
    # Validate file type
    if not file.filename:
        raise ValidationError("File must have a filename", "file")
    
    try:
        # Read file content
        file_content = await file.read()
        if not file_content:
            raise ValidationError("Uploaded file is empty", "file")
        
        # Process the sample document into a template
        template_data = await template_processor.convert_sample_to_template(
            file_content=file_content,
            filename=file.filename,
            template_name=template_name,
            version=version,
            kind=kind,
            template_description=template_description,
        )
        
        # Create template in database
        template_create = TemplateCreate(**template_data)
        template = await templates_repo.create(template_create)
        
        return ApiResponse(
            ok=True,
            data={
                **TemplateResponse.model_validate(template).model_dump(),
                "processing_info": {
                    "source_file": file.filename,
                    "placeholders_found": len(template_data.get("placeholders", [])),
                    "outline_sections": len(template_data.get("outline", [])),
                }
            },
        )
        
    except ValidationError:
        raise
    except ValueError as e:
        raise ValidationError(str(e), "file_processing")
    except Exception as e:
        raise ValidationError(f"Failed to process uploaded file: {str(e)}", "file_processing")
    finally:
        # Close the file
        await file.close()