from fastapi import APIRouter, HTTPException, status, Query, Depends
from typing import Optional, Dict, Any
from datetime import datetime
from ..core.security import get_current_user
from ..core import context_engine

router = APIRouter()

@router.get("/context/", response_model=Dict[str, Any], tags=["Context Engine"])
async def get_location_context(
    location: str = Query(..., description="The name of the location (e.g., 'Udaipur, India')."),
    event_date: Optional[str] = Query(
        None,
        description="The future date of the event in YYYY-MM-DD format (for forecast). Optional."
    ),
    current_user: dict = Depends(get_current_user)
):
    """
    Provides geo-coordinates and weather data (current or forecast) for a specified location.
    Requires user authentication.

    - If `event_date` is not provided, returns current weather.
    - If `event_date` is in the future, returns forecast for that date.
    """

    # Validate location
    if not location.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid location must be provided."
        )

    # Validate optional date format
    if event_date:
        try:
            datetime.strptime(event_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid event_date format. Use YYYY-MM-DD."
            )

    try:
        # Fetch context: geocoding + weather
        context_data = await context_engine.get_context_for_location_name(location, event_date)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context engine error: {str(e)}"
        )

    if not context_data or "error" in context_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=context_data.get("error", "Unable to retrieve context for the specified location.")
        )

    return context_data
