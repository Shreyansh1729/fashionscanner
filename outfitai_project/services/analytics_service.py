# In outfitai_project/services/analytics_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, distinct, text
from collections import Counter
from datetime import datetime, timedelta, timezone
import uuid
from ..models.analytics_models import ColorPaletteResponse, ColorPaletteSuggestion, PaletteItem
from ..db import orm_models as models
from ..models import analytics_models as schemas
from . import llm_service

async def get_overview_analytics(db: AsyncSession, user: models.User) -> schemas.OverviewAnalytics:
    """Calculates and returns the overview analytics for a user."""
    
    # Total items
    total_items_stmt = select(func.count(models.WardrobeItem.id)).where(models.WardrobeItem.user_id == user.id)
    total_items = (await db.execute(total_items_stmt)).scalar_one()

    if total_items == 0:
        return schemas.OverviewAnalytics(
            total_items=0, weekly_items_worn=0, monthly_items_worn=0,
            repeat_rate_percent=0.0, items_worn_count=0, items_unworn_count=0
        )

    # Worn items counts
    now = datetime.now(timezone.utc)
    weekly_stmt = select(func.count(distinct(text("item_ids")))).where(models.WornOutfitHistory.user_id == user.id, models.WornOutfitHistory.worn_at >= now - timedelta(days=7))
    monthly_stmt = select(func.count(distinct(text("item_ids")))).where(models.WornOutfitHistory.user_id == user.id, models.WornOutfitHistory.worn_at >= now - timedelta(days=30))
    
    weekly_worn = (await db.execute(weekly_stmt)).scalar_one()
    monthly_worn = (await db.execute(monthly_stmt)).scalar_one()

    # Repeat Rate
    monthly_history_stmt = select(models.WornOutfitHistory.item_ids).where(models.WornOutfitHistory.user_id == user.id, models.WornOutfitHistory.worn_at >= now - timedelta(days=30))
    monthly_history_results = (await db.execute(monthly_history_stmt)).scalars().all()
    
    all_worn_items = [item_id for wear in monthly_history_results for item_id in wear.split(',')]
    total_wears_monthly = len(all_worn_items)
    unique_wears_monthly = len(set(all_worn_items))
    repeat_rate = 0.0
    if total_wears_monthly > 0:
        repeat_wears = total_wears_monthly - unique_wears_monthly
        repeat_rate = (repeat_wears / total_wears_monthly) * 100 if total_wears_monthly > unique_wears_monthly else 0.0

    # Worn vs Unworn
    worn_items_stmt = select(func.count(models.WardrobeItem.id)).where(models.WardrobeItem.user_id == user.id, models.WardrobeItem.last_worn != None)
    items_worn_count = (await db.execute(worn_items_stmt)).scalar_one()
    items_unworn_count = total_items - items_worn_count

    return schemas.OverviewAnalytics(
        total_items=total_items, weekly_items_worn=weekly_worn, monthly_items_worn=monthly_worn,
        repeat_rate_percent=round(repeat_rate, 2), items_worn_count=items_worn_count, items_unworn_count=items_unworn_count
    )


async def get_category_analytics(db: AsyncSession, user: models.User) -> schemas.CategoryAnalytics:
    """Calculates and returns the category and style analytics."""
    
    # By Category
    cat_stmt = select(models.WardrobeItem.category, func.count(models.WardrobeItem.id)).where(
        models.WardrobeItem.user_id == user.id
    ).group_by(models.WardrobeItem.category)
    cat_results = (await db.execute(cat_stmt)).all()
    by_category = [schemas.CategoryCount(category=cat, count=count) for cat, count in cat_results]

    # By Style
    style_stmt = select(models.WardrobeItem.style, func.count(models.WardrobeItem.id)).where(
        models.WardrobeItem.user_id == user.id, models.WardrobeItem.style != None
    ).group_by(models.WardrobeItem.style)
    style_results = (await db.execute(style_stmt)).all()
    by_style = [schemas.StyleCount(style=style, count=count) for style, count in style_results]

    return schemas.CategoryAnalytics(by_category=by_category, by_style=by_style)


async def get_usage_analytics(db: AsyncSession, user: models.User) -> schemas.UsageAnalytics:
    """Calculates and returns item usage analytics."""
    
    history_stmt = select(models.WornOutfitHistory.item_ids).where(models.WornOutfitHistory.user_id == user.id)
    history_results = (await db.execute(history_stmt)).scalars().all()

    if not history_results:
        return schemas.UsageAnalytics(most_worn_item=None, least_worn_item=None, total_wears=0, average_wear_per_item=0.0)

    # Calculate wear counts for each item
    all_worn_item_ids_str = [item_id for wear in history_results for item_id in wear.split(',')]
    wear_counts = Counter(all_worn_item_ids_str)
    
    total_wears = len(all_worn_item_ids_str)
    total_items_stmt = select(func.count(models.WardrobeItem.id)).where(models.WardrobeItem.user_id == user.id)
    total_items = (await db.execute(total_items_stmt)).scalar_one()
    average_wear = total_wears / total_items if total_items > 0 else 0.0

    # Find most and least worn items
    most_worn_id_str, most_worn_count = wear_counts.most_common(1)[0]
    least_worn_id_str, least_worn_count = wear_counts.most_common()[-1]
    
    most_worn_item_orm = await db.get(models.WardrobeItem, uuid.UUID(most_worn_id_str))
    least_worn_item_orm = await db.get(models.WardrobeItem, uuid.UUID(least_worn_id_str))
    
    most_worn_item = schemas.ItemUsage(item=most_worn_item_orm, wear_count=most_worn_count) if most_worn_item_orm else None
    least_worn_item = schemas.ItemUsage(item=least_worn_item_orm, wear_count=least_worn_count) if least_worn_item_orm else None

    return schemas.UsageAnalytics(
        most_worn_item=most_worn_item,
        least_worn_item=least_worn_item,
        total_wears=total_wears,
        average_wear_per_item=round(average_wear, 2)
    )

async def get_color_palette_suggestions(db: AsyncSession, user: models.User) -> schemas.ColorPaletteResponse:
    """
    Analyzes the user's wardrobe to generate color palette suggestions.
    """
    # 1. Fetch the user's entire wardrobe. This is an analysis of all items.
    stmt = select(models.WardrobeItem).where(models.WardrobeItem.user_id == user.id)
    wardrobe_items = (await db.execute(stmt)).scalars().all()

    if not wardrobe_items or len(wardrobe_items) < 5: # Need a minimum number of items for meaningful palettes
        return schemas.ColorPaletteResponse(palettes=[])

    # 2. Prepare data for the LLM
    item_list_for_llm = [{"name": item.name, "color": item.color} for item in wardrobe_items]
    
    # 3. Call the LLM to get palette suggestions
    llm_response = llm_service.generate_color_palettes(item_list_for_llm)

    if "error" in llm_response or "palettes" not in llm_response:
        # Return empty list gracefully if AI fails
        return schemas.ColorPaletteResponse(palettes=[])

    # 4. Reconstruct the full response, mapping item names back to full item objects
    # Create a lookup map for efficient access: { "item name": ItemObject }
    # Handle potential duplicate names by storing a list of items for each name
    item_name_map = {}
    for item in wardrobe_items:
        if item.name not in item_name_map:
            item_name_map[item.name] = []
        item_name_map[item.name].append(item)

    reconstructed_palettes = []
    for llm_palette in llm_response["palettes"]:
        palette_items = []
        # Use a set to avoid adding the same item UUID twice to a single palette
        added_item_ids = set() 
        
        for item_name in llm_palette.get("item_names", []):
            if item_name in item_name_map:
                # Add all items that match the name, if not already added
                for item_obj in item_name_map[item_name]:
                    if item_obj.id not in added_item_ids:
                        palette_items.append(PaletteItem.model_validate(item_obj))
                        added_item_ids.add(item_obj.id)
        
        if palette_items: # Only add palettes that have matching items
            reconstructed_palettes.append(
                ColorPaletteSuggestion(
                    palette_name=llm_palette.get("palette_name", "Unnamed Palette"),
                    description=llm_palette.get("description", ""),
                    items=palette_items
                )
            )

    return schemas.ColorPaletteResponse(palettes=reconstructed_palettes)

