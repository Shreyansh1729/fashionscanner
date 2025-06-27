from typing import Optional, Dict, Any
import httpx
from geopy.geocoders import Nominatim
import asyncio
from datetime import datetime, date

from config.settings import settings
import logging

logger = logging.getLogger(__name__)
geolocator = Nominatim(user_agent="outfitai_app")
context_cache: Dict[str, Dict[str, Any]] = {}

# -------------------- Fallback Data -------------------- #

def fallback_weather_data(is_forecast: bool = False) -> Dict[str, Any]:
    return {
        "temperature_c": 25.0,
        "feels_like_c": 25.0,
        "condition": "Unknown",
        "description": "Default fallback weather",
        "humidity_percent": 50,
        "wind_speed_mps": 3.0,
        "precipitation_mm": 0.0,
        "uv_index": 5.0,
        "visibility_km": 10.0,
        "is_forecast": is_forecast,
        "note": "This is fallback data due to external API failure."
    }

# -------------------- Geolocation -------------------- #

async def get_coordinates_for_location(location_name: str) -> Optional[Dict[str, float]]:
    location_name_lower = location_name.lower()
    if location_name_lower in context_cache and "coords" in context_cache[location_name_lower]:
        return context_cache[location_name_lower]["coords"]
    try:
        location_data = await asyncio.to_thread(geolocator.geocode, location_name)
        if location_data:
            coords = {"latitude": location_data.latitude, "longitude": location_data.longitude}
            context_cache.setdefault(location_name_lower, {})["coords"] = coords
            return coords
    except Exception as e:
        logger.error(f"Error during geocoding for '{location_name}': {e}")
    return None

# -------------------- UV Index -------------------- #

async def get_uv_index(lat: float, lon: float) -> float:
    url = "https://api.openweathermap.org/data/2.5/uvi"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": settings.OPENWEATHER_API_KEY,
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("value", 0.0)
    except Exception as e:
        logger.warning(f"[Fallback] UV index fetch failed: {e}")
        return 5.0  # average fallback value

# -------------------- Current Weather -------------------- #

async def get_current_weather(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    if not settings.OPENWEATHER_API_KEY:
        return fallback_weather_data()

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": settings.OPENWEATHER_API_KEY,
        "units": "metric"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return {
                "temperature_c": data["main"]["temp"],
                "feels_like_c": data["main"]["feels_like"],
                "condition": data["weather"][0]["main"],
                "description": data["weather"][0]["description"],
                "humidity_percent": data["main"]["humidity"],
                "wind_speed_mps": data["wind"]["speed"],
                "precipitation_mm": data.get("rain", {}).get("1h", 0.0),
                "uv_index": await get_uv_index(lat, lon),
                "visibility_km": data.get("visibility", 10000) / 1000  # meters to km
            }

    except Exception as e:
        logger.warning(f"[Fallback] Current weather fetch failed: {e}")
        return fallback_weather_data()

# -------------------- Forecast Weather -------------------- #

async def get_weather_forecast(lat: float, lon: float, event_date: date) -> Optional[Dict[str, Any]]:
    if not settings.OPENWEATHER_API_KEY:
        return fallback_weather_data(is_forecast=True)

    days_from_now = (event_date - date.today()).days
    if not (0 <= days_from_now < 5):
        return {"error": "Forecast is only available for the next 5 days."}

    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": settings.OPENWEATHER_API_KEY,
        "units": "metric"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            forecast_data = response.json()

        target_datetime = datetime.combine(event_date, datetime.strptime("12:00:00", "%H:%M:%S").time())

        closest_forecast = min(
            forecast_data.get("list", []),
            key=lambda f: abs(datetime.strptime(f["dt_txt"], "%Y-%m-%d %H:%M:%S") - target_datetime)
        )

        return {
            "temperature_c": closest_forecast["main"]["temp"],
            "feels_like_c": closest_forecast["main"]["feels_like"],
            "condition": closest_forecast["weather"][0]["main"],
            "description": closest_forecast["weather"][0]["description"],
            "humidity_percent": closest_forecast["main"]["humidity"],
            "wind_speed_mps": closest_forecast["wind"]["speed"],
            "precipitation_mm": closest_forecast.get("rain", {}).get("3h", 0.0),
            "uv_index": 0.0,  # Forecast API doesn't return UV index
            "visibility_km": closest_forecast.get("visibility", 10000) / 1000,
            "is_forecast": True
        }

    except Exception as e:
        logger.warning(f"[Fallback] Forecast fetch failed: {e}")
        return fallback_weather_data(is_forecast=True)

# -------------------- Orchestrator -------------------- #

async def get_context_for_location_name(
    location_name: str,
    event_date_str: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    coords = await get_coordinates_for_location(location_name)
    if not coords:
        return {"error": "Could not find coordinates for the specified location."}

    weather = None
    event_date = None

    if event_date_str:
        try:
            event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD."}

    if event_date and event_date >= date.today():
        weather = await get_weather_forecast(coords["latitude"], coords["longitude"], event_date)
    else:
        weather = await get_current_weather(coords["latitude"], coords["longitude"])

    return {
        "location_name": location_name.title(),
        "event_date": event_date.isoformat() if event_date else None,
        "coordinates": coords,
        "weather": weather
    }
