# outfitai_project/services/event_logger_service.py
import uuid
from typing import Dict, Any
from ..db.database import AsyncSessionLocal
from ..db import orm_models as models
import logging

logger = logging.getLogger(__name__)

async def log_event(user_id: uuid.UUID, event_type: str, metadata: Dict[str, Any]):
    """
    Logs a user event to the database in an independent session.
    """
    logger.info(f"Logging event '{event_type}' for user {user_id}.")
    async with AsyncSessionLocal() as db:
        try:
            new_event = models.UserEvent(
                user_id=user_id,
                event_type=event_type,
                # --- USE THE NEW COLUMN NAME ---
                event_data=metadata
            )
            db.add(new_event)
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to log event: {e}", exc_info=True)
            await db.rollback() # Ensure transaction is rolled back on error