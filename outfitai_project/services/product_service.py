# outfitai_project/services/product_service.py
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..db import orm_models as models
from ..models.outfit_models import ScrapedProduct
from ..db.database import AsyncSessionLocal
import logging

logger = logging.getLogger(__name__)

async def bulk_create_or_update_products(products_data: List[ScrapedProduct]):
    """
    Efficiently inserts or updates a list of products in the database,
    ensuring all data types are compatible with the database driver.
    """
    if not products_data:
        return

    product_dicts = []
    # --- THIS IS THE FIX ---
    # Convert Pydantic models to dictionaries with primitive types
    for p in products_data:
        p_dict = p.model_dump()
        # Explicitly convert HttpUrl objects to simple strings
        p_dict['product_url'] = str(p_dict['product_url'])
        if p_dict.get('image_url'):
            p_dict['image_url'] = str(p_dict['image_url'])
        
        # Filter out keys that are not in the ORM model to prevent errors
        orm_keys = {c.name for c in models.Product.__table__.columns}
        filtered_dict = {k: v for k, v in p_dict.items() if k in orm_keys}
        product_dicts.append(filtered_dict)
    
    # Remove duplicates based on product_url within the same batch
    unique_products = list({p['product_url']: p for p in product_dicts}.values())
    
    if not unique_products:
        return

    logger.info(f"Attempting to bulk insert/update {len(unique_products)} products.")

    async with AsyncSessionLocal() as db:
        try:
            # SQLAlchemy's insert().on_conflict_do_update() is dialect-specific.
            if db.bind.dialect.name == 'postgresql':
                stmt = pg_insert(models.Product).values(unique_products)
                update_dict = {col.name: getattr(stmt.excluded, col.name) for col in stmt.excluded if col.name not in ['id', 'created_at']}
                stmt = stmt.on_conflict_do_update(index_elements=['product_url'], set_=update_dict)
            else: # SQLite
                stmt = sqlite_insert(models.Product).values(unique_products)
                update_dict = {col.name: getattr(stmt.excluded, col.name) for col in stmt.excluded if col.name not in ['id', 'created_at']}
                stmt = stmt.on_conflict_do_update(index_elements=['product_url'], set_=update_dict)
            
            await db.execute(stmt)
            await db.commit()
            logger.info(f"Successfully saved {len(unique_products)} products to the database.")
        except Exception as e:
            logger.error(f"Database error during bulk product save: {e}", exc_info=True)
            await db.rollback()

async def search_products(
    db: AsyncSession,
    category: Optional[str] = None,
    color: Optional[str] = None,
    brand: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
) -> List[models.Product]:
    """Searches for products in the database based on structured attributes."""
    query = select(models.Product)
    if category: query = query.where(models.Product.category.ilike(f"%{category}%"))
    if color: query = query.where(models.Product.color.ilike(f"%{color}%"))
    if brand: query = query.where(models.Product.brand.ilike(f"%{brand}%"))
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()