"""
API routes for persona instance management
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body
from pydantic import BaseModel, Field

from backend.models.persona_instance import (
    PersonaInstance,
    PersonaInstanceCreate,
    PersonaInstanceUpdate,
    PersonaInstanceResponse,
    LLMModel
)
from backend.services.persona_instance_service import PersonaInstanceService
from backend.services.spend_tracking_service import SpendTrackingService
from backend.services.database import DatabaseManager
from backend.factories.persona_instance_factory import PersonaInstanceFactory


router = APIRouter(prefix="/api/v1/persona-instances", tags=["persona-instances"])


# Dependency to get database
async def get_db() -> DatabaseManager:
    """Get database manager instance"""
    db = DatabaseManager()
    await db.initialize()
    try:
        yield db
    finally:
        await db.close()


# Response models
class PersonaInstanceListResponse(BaseModel):
    """Response for listing persona instances"""
    instances: List[PersonaInstanceResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SpendStatusResponse(BaseModel):
    """Response for spend status"""
    instance_id: UUID
    daily_spent: Decimal
    daily_limit: Decimal
    daily_remaining: Decimal
    daily_percentage: float
    monthly_spent: Decimal
    monthly_limit: Decimal
    monthly_remaining: Decimal
    monthly_percentage: float
    daily_exceeded: bool
    monthly_exceeded: bool
    last_updated: datetime


class SpendHistoryResponse(BaseModel):
    """Response for spend history"""
    instance_id: UUID
    history: List[Dict[str, Any]]
    total_spend: Decimal
    start_date: datetime
    end_date: datetime


class TeamCreationRequest(BaseModel):
    """Request to create a development team"""
    project_name: str
    azure_devops_org: str
    azure_devops_project: str
    team_size: str = Field(default="medium", pattern="^(small|medium|large)$")
    custom_settings: Optional[Dict[str, Any]] = None


class CloneInstanceRequest(BaseModel):
    """Request to clone an instance"""
    new_instance_name: str
    new_project: Optional[str] = None
    new_repository: Optional[str] = None


# API Endpoints

@router.post("/", response_model=PersonaInstanceResponse)
async def create_persona_instance(
    instance_data: PersonaInstanceCreate,
    db: DatabaseManager = Depends(get_db)
) -> PersonaInstanceResponse:
    """Create a new persona instance"""
    service = PersonaInstanceService(db)
    
    try:
        instance = await service.create_instance(instance_data)
        return PersonaInstanceResponse.from_orm(instance)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create instance: {str(e)}")


@router.get("/", response_model=PersonaInstanceListResponse)
async def list_persona_instances(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    persona_type_id: Optional[UUID] = Query(None, description="Filter by persona type"),
    project: Optional[str] = Query(None, description="Filter by Azure DevOps project"),
    db: DatabaseManager = Depends(get_db)
) -> PersonaInstanceListResponse:
    """List persona instances with pagination and filters"""
    service = PersonaInstanceService(db)
    
    # Get filtered instances
    all_instances = await service.list_instances()
    
    # Apply filters
    filtered = all_instances
    if is_active is not None:
        filtered = [i for i in filtered if i.is_active == is_active]
    if persona_type_id:
        filtered = [i for i in filtered if i.persona_type_id == persona_type_id]
    if project:
        filtered = [i for i in filtered if i.azure_devops_project == project]
    
    # Calculate pagination
    total = len(filtered)
    total_pages = (total + page_size - 1) // page_size
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    # Get page of results
    page_instances = filtered[start_idx:end_idx]
    
    return PersonaInstanceListResponse(
        instances=[PersonaInstanceResponse.from_orm(i) for i in page_instances],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{instance_id}", response_model=PersonaInstanceResponse)
async def get_persona_instance(
    instance_id: UUID = Path(..., description="Instance ID"),
    db: DatabaseManager = Depends(get_db)
) -> PersonaInstanceResponse:
    """Get a specific persona instance"""
    service = PersonaInstanceService(db)
    
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    
    return PersonaInstanceResponse.from_orm(instance)


@router.patch("/{instance_id}", response_model=PersonaInstanceResponse)
async def update_persona_instance(
    instance_id: UUID = Path(..., description="Instance ID"),
    update_data: PersonaInstanceUpdate = Body(...),
    db: DatabaseManager = Depends(get_db)
) -> PersonaInstanceResponse:
    """Update a persona instance"""
    service = PersonaInstanceService(db)
    
    try:
        instance = await service.update_instance(instance_id, update_data)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        return PersonaInstanceResponse.from_orm(instance)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update instance: {str(e)}")


@router.delete("/{instance_id}")
async def delete_persona_instance(
    instance_id: UUID = Path(..., description="Instance ID"),
    db: DatabaseManager = Depends(get_db)
) -> Dict[str, str]:
    """Delete a persona instance"""
    service = PersonaInstanceService(db)
    
    try:
        deleted = await service.delete_instance(instance_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Instance not found")
        return {"message": "Instance deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete instance: {str(e)}")


@router.post("/{instance_id}/activate", response_model=PersonaInstanceResponse)
async def activate_persona_instance(
    instance_id: UUID = Path(..., description="Instance ID"),
    db: DatabaseManager = Depends(get_db)
) -> PersonaInstanceResponse:
    """Activate a persona instance"""
    service = PersonaInstanceService(db)
    
    try:
        instance = await service.activate_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        return PersonaInstanceResponse.from_orm(instance)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to activate instance: {str(e)}")


@router.post("/{instance_id}/deactivate", response_model=PersonaInstanceResponse)
async def deactivate_persona_instance(
    instance_id: UUID = Path(..., description="Instance ID"),
    db: DatabaseManager = Depends(get_db)
) -> PersonaInstanceResponse:
    """Deactivate a persona instance"""
    service = PersonaInstanceService(db)
    
    try:
        instance = await service.deactivate_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        return PersonaInstanceResponse.from_orm(instance)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deactivate instance: {str(e)}")


# Spend tracking endpoints

@router.get("/{instance_id}/spend/status", response_model=SpendStatusResponse)
async def get_spend_status(
    instance_id: UUID = Path(..., description="Instance ID"),
    db: DatabaseManager = Depends(get_db)
) -> SpendStatusResponse:
    """Get current spend status for an instance"""
    spend_service = SpendTrackingService(db)
    await spend_service.initialize()
    
    try:
        status = await spend_service.get_spend_status(instance_id)
        return SpendStatusResponse(
            instance_id=instance_id,
            last_updated=datetime.utcnow(),
            **status
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        await spend_service.close()


@router.get("/{instance_id}/spend/history", response_model=SpendHistoryResponse)
async def get_spend_history(
    instance_id: UUID = Path(..., description="Instance ID"),
    start_date: Optional[datetime] = Query(None, description="Start date for history"),
    end_date: Optional[datetime] = Query(None, description="End date for history"),
    category: Optional[str] = Query(None, description="Filter by spend category"),
    db: DatabaseManager = Depends(get_db)
) -> SpendHistoryResponse:
    """Get spend history for an instance"""
    spend_service = SpendTrackingService(db)
    await spend_service.initialize()
    
    try:
        history = await spend_service.get_spend_history(
            instance_id=instance_id,
            start_date=start_date,
            end_date=end_date,
            category=category
        )
        
        total_spend = sum(Decimal(str(h["amount"])) for h in history)
        
        return SpendHistoryResponse(
            instance_id=instance_id,
            history=history,
            total_spend=total_spend,
            start_date=start_date or (history[0]["created_at"] if history else datetime.utcnow()),
            end_date=end_date or datetime.utcnow()
        )
    finally:
        await spend_service.close()


@router.post("/{instance_id}/spend/record")
async def record_spend(
    instance_id: UUID = Path(..., description="Instance ID"),
    amount: Decimal = Body(..., description="Spend amount"),
    description: str = Body(..., description="Spend description"),
    db: DatabaseManager = Depends(get_db)
) -> Dict[str, Any]:
    """Manually record spend for an instance"""
    service = PersonaInstanceService(db)
    
    try:
        await service.record_spend(instance_id, amount, description)
        
        # Get updated status
        spend_service = SpendTrackingService(db)
        await spend_service.initialize()
        try:
            status = await spend_service.get_spend_status(instance_id)
            return {
                "message": "Spend recorded successfully",
                "amount": float(amount),
                "daily_remaining": float(status["daily_remaining"]),
                "monthly_remaining": float(status["monthly_remaining"])
            }
        finally:
            await spend_service.close()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record spend: {str(e)}")


# Factory endpoints

@router.post("/factory/team", response_model=Dict[str, PersonaInstanceResponse])
async def create_team(
    team_request: TeamCreationRequest,
    db: DatabaseManager = Depends(get_db)
) -> Dict[str, PersonaInstanceResponse]:
    """Create a standard development team"""
    factory = PersonaInstanceFactory(db)
    
    try:
        team = await factory.create_standard_development_team(
            project_name=team_request.project_name,
            azure_devops_org=team_request.azure_devops_org,
            azure_devops_project=team_request.azure_devops_project,
            team_size=team_request.team_size
        )
        
        return {
            role: PersonaInstanceResponse.from_orm(instance)
            for role, instance in team.items()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create team: {str(e)}")


@router.post("/{instance_id}/clone", response_model=PersonaInstanceResponse)
async def clone_instance(
    instance_id: UUID = Path(..., description="Source instance ID"),
    clone_request: CloneInstanceRequest = Body(...),
    db: DatabaseManager = Depends(get_db)
) -> PersonaInstanceResponse:
    """Clone an existing persona instance"""
    factory = PersonaInstanceFactory(db)
    
    try:
        clone = await factory.clone_instance(
            source_instance_id=instance_id,
            new_instance_name=clone_request.new_instance_name,
            new_project=clone_request.new_project,
            new_repository=clone_request.new_repository
        )
        
        return PersonaInstanceResponse.from_orm(clone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clone instance: {str(e)}")


# Analytics endpoints

@router.get("/analytics/summary")
async def get_instance_analytics(
    project: Optional[str] = Query(None, description="Filter by project"),
    persona_type_id: Optional[UUID] = Query(None, description="Filter by persona type"),
    db: DatabaseManager = Depends(get_db)
) -> Dict[str, Any]:
    """Get analytics summary for persona instances"""
    spend_service = SpendTrackingService(db)
    await spend_service.initialize()
    
    try:
        analytics = await spend_service.get_spend_analytics(
            project=project,
            persona_type_id=persona_type_id
        )
        
        # Get instance statistics
        service = PersonaInstanceService(db)
        stats = await service.get_instance_statistics()
        
        return {
            "instance_stats": stats,
            "spend_analytics": analytics
        }
    finally:
        await spend_service.close()


@router.post("/maintenance/reset-daily-spend")
async def reset_daily_spend(
    db: DatabaseManager = Depends(get_db)
) -> Dict[str, Any]:
    """Reset daily spend for all instances (maintenance endpoint)"""
    service = PersonaInstanceService(db)
    
    try:
        count = await service.reset_daily_spend_all()
        return {
            "message": "Daily spend reset successfully",
            "instances_affected": count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset daily spend: {str(e)}")