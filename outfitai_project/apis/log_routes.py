# outfitai_project/apis/log_routes.py
from fastapi import APIRouter, Depends, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from ..core.security import get_current_user
from ..services import event_logger_service
from ..models.log_models import EventLog
from ..db import orm_models as models

router = APIRouter()

@router.post("/log-event", status_code=status.HTTP_202_ACCEPTED, tags=["Logging"])
async def log_user_event(
    event_in: EventLog,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user)
):
    """
    A fire-and-forget endpoint to log user interactions.
    
    Example Event Types:
    - VIEWED_RECOMMENDATION
    - VIEWED_PRODUCT
    - CLICKED_PRODUCT_LINK
    - SAVED_OUTFIT
    """
    # We use add_task to run our logging service in the background.
    # This makes the API response immediate for the user, as they don't have to wait
    # for the database write to complete.
    background_tasks.add_task(
        event_logger_service.log_event,
        user_id=current_user.id,
        event_type=event_in.event_type,
        metadata=event_in.metadata
    )
    
    return {"message": "Event received"}