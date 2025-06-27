# outfitai_project/models/log_models.py
import uuid
from pydantic import BaseModel, Field
from typing import Dict, Any

class EventLog(BaseModel):
    # This model defines the data needed to log an event.
    # The 'event_type' could be an Enum in a larger application for stricter validation.
    event_type: str = Field(..., example="VIEWED_PRODUCT")
    
    # 'metadata' will contain the details of the event
    metadata: Dict[str, Any] = Field(..., example={"product_id": "some-uuid-here"})