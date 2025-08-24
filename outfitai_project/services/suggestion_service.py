from sqlalchemy.orm import Session
from sqlalchemy.future import select
from datetime import datetime, timedelta, timezone
import uuid
from typing import Dict, Any , List
from fastapi import HTTPException, status 
from ..models.outfit_models import ItemPairingResponse, OutfitSuggestion
from ..models.outfit_models import WeeklyPlanRequest, WeeklyPlanResponse, DailyPlan, OutfitSuggestion
from ..db import orm_models as models
from ..models.outfit_models import SuggestionContext
from . import llm_service, external_api_service, embedding_service, vector_db_service
from sqlalchemy.ext.asyncio import AsyncSession
import random

def get_todays_suggestion_contexts(user_id: uuid.UUID) -> list[SuggestionContext]:
    """Determines the events for today from calendar or a default schedule."""
    events = external_api_service.get_calendar_events(user_id)
    contexts = []
    
    if events:
        for event in events:
            summary = event.get("summary", "").lower()
            if any(term in summary for term in ["meeting", "work", "office"]):
                contexts.append(SuggestionContext(occasion="Office / Formal"))
            elif any(term in summary for term in ["gym", "workout", "sports"]):
                contexts.append(SuggestionContext(occasion="Gym / Sports"))
            else:
                contexts.append(SuggestionContext(occasion=f"Event: {event.get('summary')}"))
    
    # Ensure default contexts are present if not found in calendar
    if not any("Office" in c.occasion for c in contexts):
        contexts.append(SuggestionContext(occasion="Work / College"))
    if not any("Home" in c.occasion for c in contexts):
        contexts.append(SuggestionContext(occasion="Home / Relaxing"))
        
    return contexts

async def generate_daily_outfits(db: Session, user: models.User) -> Dict[str, Any]:
    """
    Generates a set of outfits for the day's events using RAG (Vector Search).
    """
    repetition_days = getattr(user, 'repetition_preference', 3)
    user_city = getattr(user, 'city', 'New York')
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=repetition_days)

    # Fetch weather and daily contexts as before
    weather_data = await external_api_service.get_weather_data(user_city)
    contexts = get_todays_suggestion_contexts(user.id)
    
    final_suggestions = {}
    purchase_recommendation = None
    
    # Get the full user wardrobe once to use as a lookup map
    all_items_stmt = select(models.WardrobeItem).where(models.WardrobeItem.user_id == user.id)
    all_items_orm = (await db.execute(all_items_stmt)).scalars().all()
    if not all_items_orm:
        return {"suggestions": {}, "purchase_recommendation": "Your wardrobe is empty!"}
    items_map = {item.id: item for item in all_items_orm}

    for context in contexts:
        # 1. CREATE A SEMANTIC QUERY
        query_text = f"An outfit for {context.occasion} on a day with {weather_data.get('description')}"
        
        # 2. EMBED THE QUERY
        query_embedding = embedding_service.get_query_embedding(query_text)
        if not query_embedding:
            continue # Skip if embedding fails

        # 3. SEARCH THE VECTOR DATABASE
        # Search for a larger number of items to allow for filtering
        search_results = vector_db_service.search_similar_items(
            user_id=user.id,
            query_embedding=query_embedding,
            n_results=30 # Fetch 30 most relevant items
        )
        
        if not search_results:
            continue # No relevant items found in vector search

        # 4. RETRIEVE & FILTER THE RELEVANT ITEMS FROM POSTGRESQL
        retrieved_ids = [uuid.UUID(res['id']) for res in search_results]
        
        # Filter these relevant items against the anti-repetition rule
        relevant_items = [
            items_map[item_id] for item_id in retrieved_ids 
            if item_id in items_map and (items_map[item_id].last_worn is None or items_map[item_id].last_worn <= cutoff_date)
        ]
        
        # If filtering leaves too few items, relax the rule for this context
        if len(relevant_items) < 5:
            relevant_items = [items_map[item_id] for item_id in retrieved_ids if item_id in items_map]

        if not relevant_items:
            continue

        # 5. AUGMENT THE LLM PROMPT WITH THE RETRIEVED ITEMS
        wardrobe_list_for_llm = [
            {"id": str(item.id), "name": item.name, "category": item.category.value, "color": item.color, "style": item.style}
            for item in relevant_items
        ]
        
        llm_context = {
            "occasion": context.occasion,
            "weather": f"{weather_data.get('temperature')}°C, {weather_data.get('description')}",
            "mood": context.mood,
        }
        
        # 6. GENERATE THE OUTFIT
        llm_response = llm_service.generate_outfit_from_wardrobe(llm_context, wardrobe_list_for_llm)

        if "purchase_recommendation" in llm_response and not purchase_recommendation:
            purchase_recommendation = llm_response["purchase_recommendation"]

        if "error" not in llm_response and "purchase_recommendation" not in llm_response:
            outfit = {}
            for category, item_id_str in llm_response.items():
                try:
                    item_id = uuid.UUID(item_id_str)
                    if item_id in items_map:
                        outfit[category.lower()] = items_map[item_id]
                except (ValueError, TypeError):
                    continue
            
            occasion_key = context.occasion.replace(" / ", "_").replace(" ", "_").lower()
            final_suggestions[occasion_key] = OutfitSuggestion(**outfit)

    return {
        "suggestions": final_suggestions,
        "purchase_recommendation": purchase_recommendation
    }

async def generate_pairings_for_item(db: AsyncSession, user: models.User, item_id: uuid.UUID) -> ItemPairingResponse:
    """
    Generates multiple outfit suggestions featuring a specific wardrobe item using RAG,
    with a fallback to a random selection if vector search finds no matches.
    """
    focal_item = await db.get(models.WardrobeItem, item_id)
    if not focal_item or focal_item.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found or does not belong to the user.")

    # --- START: MODIFIED LOGIC ---

    complementary_items = []
    
    # 1. Primary Method: Vector Search for Complementary Items
    query_text = f"Clothes that go well with a {focal_item.color} {focal_item.name} for a {focal_item.style or 'versatile'} look"
    query_embedding = embedding_service.get_query_embedding(query_text)
    
    if query_embedding:
        search_results = vector_db_service.search_similar_items(
            user_id=user.id, query_embedding=query_embedding, n_results=30
        )
        retrieved_ids = [uuid.UUID(res['id']) for res in search_results if uuid.UUID(res['id']) != focal_item.id]
        if retrieved_ids:
            complementary_items_stmt = select(models.WardrobeItem).where(models.WardrobeItem.id.in_(retrieved_ids))
            complementary_items = (await db.execute(complementary_items_stmt)).scalars().all()

    # 2. Fallback Method: If Vector Search fails, get a random sample
    if not complementary_items:
        print("INFO: Vector search for pairings was empty. Using random fallback.")
        all_other_items_stmt = select(models.WardrobeItem).where(
            models.WardrobeItem.user_id == user.id,
            models.WardrobeItem.id != focal_item.id
        )
        all_other_items = (await db.execute(all_other_items_stmt)).scalars().all()
        
        # Shuffle and pick up to 30 random items
        random.shuffle(all_other_items)
        complementary_items = all_other_items[:30]

    if not complementary_items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="There are no other items in the wardrobe to create a pairing.")

    # --- END: MODIFIED LOGIC ---

    # 3. Augment & Generate (This part remains the same)
    wardrobe_map = {item.id: item for item in complementary_items}
    wardrobe_map[focal_item.id] = focal_item
    
    user_city = getattr(user, 'city', 'New York')
    weather_data = await external_api_service.get_weather_data(user_city)
    llm_context = {"weather": f"{weather_data.get('temperature')}°C, {weather_data.get('description')}"}
    
    focal_item_dict = {"id": str(focal_item.id), "name": focal_item.name, "category": focal_item.category.value, "color": focal_item.color, "style": focal_item.style}
    wardrobe_list_for_llm = [
        {"id": str(item.id), "name": item.name, "category": item.category.value, "color": item.color, "style": item.style}
        for item in complementary_items
    ]
    
    llm_response = llm_service.generate_outfit_pairings(focal_item_dict, wardrobe_list_for_llm, llm_context)

    if "error" in llm_response or "outfits" not in llm_response:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI failed to generate outfit pairings.")

    # 4. Reconstruct the response (This part remains the same)
    final_suggestions = []
    for outfit_dict in llm_response["outfits"]:
        reconstructed_outfit = {}
        focal_category_key = focal_item.category.value.lower()
        reconstructed_outfit[focal_category_key] = focal_item
        for category, returned_id_str in outfit_dict.items():
            try:
                item_uuid = uuid.UUID(returned_id_str)
                if item_uuid in wardrobe_map:
                    reconstructed_outfit[category.lower()] = wardrobe_map[item_uuid]
            except (ValueError, TypeError):
                continue
        final_suggestions.append(OutfitSuggestion(**reconstructed_outfit))

    return ItemPairingResponse(focal_item=focal_item, outfit_suggestions=final_suggestions)


async def generate_weekly_plan(db: AsyncSession, user: models.User, plan_request: WeeklyPlanRequest) -> WeeklyPlanResponse:
    """
    Generates a multi-day outfit plan using a RAG-based approach.
    """
    # 1. Fetch the weather forecast for the requested number of days
    user_city = getattr(user, 'city', 'New York')
    forecast = await external_api_service.get_weather_forecast(city=user_city, days=plan_request.days)
    if not forecast or "error" in forecast[0]:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Weather service is currently unavailable for weekly planning.")

    # 2. CREATE A BROAD SEMANTIC QUERY for the entire week
    # This query is designed to retrieve a versatile pool of clothing for the week's general occasion.
    query_text = f"A versatile set of clothes for a week of '{plan_request.occasion}'"

    # 3. EMBED THE QUERY & SEARCH THE VECTOR DATABASE
    query_embedding = embedding_service.get_query_embedding(query_text)
    if not query_embedding:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create a search query for the weekly plan.")

    # Fetch a larger pool of items for weekly planning. The number should be generous.
    # e.g., 7 days * 5 items/day = 35. Let's fetch 50 to give the AI plenty of options.
    search_results = vector_db_service.search_similar_items(
        user_id=user.id, query_embedding=query_embedding, n_results=50
    )
    
    if not search_results:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Could not find enough relevant items in the wardrobe to generate a weekly plan.")

    # 4. RETRIEVE THE FULL ITEMS FROM POSTGRESQL
    retrieved_ids = [uuid.UUID(res['id']) for res in search_results]
    retrieved_items_stmt = select(models.WardrobeItem).where(models.WardrobeItem.id.in_(retrieved_ids))
    relevant_items = (await db.execute(retrieved_items_stmt)).scalars().all()

    if len(relevant_items) < plan_request.days * 2: # Heuristic: need at least 2 items per day to plan
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enough variety in the relevant wardrobe items to generate a weekly plan.")

    # 5. AUGMENT & GENERATE with the retrieved items
    wardrobe_list_for_llm = [
        {"id": str(item.id), "name": item.name, "category": item.category.value, "color": item.color, "style": item.style}
        for item in relevant_items
    ]
    
    llm_response = llm_service.generate_weekly_outfit_plan(wardrobe_list_for_llm, forecast, plan_request.occasion)

    if "error" in llm_response or "weekly_plan" not in llm_response:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI failed to generate a valid weekly plan.")
        
    # 6. Reconstruct the response (this logic remains the same)
    wardrobe_map = {str(item.id): item for item in relevant_items}
    reconstructed_plan = []
    for daily_plan_dict in llm_response["weekly_plan"]:
        reconstructed_outfit = {}
        for category, item_id_str in daily_plan_dict.get("outfit", {}).items():
            if item_id_str in wardrobe_map:
                reconstructed_outfit[category.lower()] = wardrobe_map[item_id_str]
        
        reconstructed_plan.append(
            DailyPlan(
                date=daily_plan_dict["date"],
                weather_summary=daily_plan_dict["weather_summary"],
                outfit=OutfitSuggestion(**reconstructed_outfit)
            )
        )
        
    return WeeklyPlanResponse(weekly_plan=reconstructed_plan)