# outfitai_project/apis/product_routes.py
from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..services import product_service
from ..db.database import get_db
from ..core.security import get_current_user
from ..models.outfit_models import ScrapedProduct # Re-using this as our response model

router = APIRouter()

@router.get("/products/search", response_model=List[ScrapedProduct], tags=["Products"])
async def search_products_endpoint(
    category: Optional[str] = Query(None, description="e.g., 'kurta', 'jeans'"),
    color: Optional[str] = Query(None, description="e.g., 'blue', 'white'"),
    brand: Optional[str] = Query(None, description="e.g., 'FabIndia'"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user) # Protect the endpoint
):
    """
    Search the master product catalog using structured filters.
    """
    products_orm = await product_service.search_products(
        db=db, category=category, color=color, brand=brand, skip=skip, limit=limit
    )
    # Convert ORM objects to Pydantic models for the response
    return [ScrapedProduct.model_validate(p) for p in products_orm]