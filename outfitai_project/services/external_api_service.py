# In outfitai_project/services/external_api_service.py

import httpx
import uuid  # <--- THIS IS THE FIX
from typing import Dict, Any, List
from config.settings import settings
from datetime import date, timedelta

async def get_weather_data(city: str = "New York") -> Dict[str, Any]:
    """Fetches current weather data from OpenWeatherMap."""
    if not settings.OPENWEATHER_API_KEY:
        return {"temperature": 25, "description": "weather service not configured"}
        
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={settings.OPENWEATHER_API_KEY}&units=metric"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            return {"temperature": data["main"]["temp"], "description": data["weather"][0]["description"]}
        except httpx.HTTPStatusError:
            return {"error": "Failed to fetch weather data."}

def get_calendar_events(user_id: uuid.UUID) -> List[Dict[str, Any]]:
    """MOCK function to simulate fetching events from a user's calendar."""
    print(f"Fetching calendar events for user {user_id}...")
    # In a real app, use the user's OAuth token to call the Google Calendar API.
    return [
        {"summary": "Team Project Meeting", "start": {"dateTime": "2025-08-25T10:00:00-04:00"}},
        {"summary": "Gym Workout", "start": {"dateTime": "2025-08-25T18:00:00-04:00"}},
    ]

async def get_weather_forecast(city: str = "New York", days: int = 7) -> List[Dict[str, Any]]:
    """
    Fetches a multi-day weather forecast.
    Note: OpenWeatherMap's free tier provides 5-day/3-hour forecast. We'll aggregate this.
    """
    if not settings.OPENWEATHER_API_KEY:
        # Return a simple fallback forecast
        return [{"date": (date.today() + timedelta(days=i)).isoformat(), "avg_temp": 25, "condition": "clear sky"} for i in range(days)]

    # Using the 5-day/3-hour forecast API
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={settings.OPENWEATHER_API_KEY}&units=metric&cnt={days*8}" # 8 intervals of 3 hours per day

    daily_forecasts = {}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            for forecast in data.get("list", []):
                forecast_date = date.fromisoformat(forecast['dt_txt'].split(' ')[0])
                if forecast_date not in daily_forecasts:
                    daily_forecasts[forecast_date] = {'temps': [], 'conditions': []}
                daily_forecasts[forecast_date]['temps'].append(forecast['main']['temp'])
                daily_forecasts[forecast_date]['conditions'].append(forecast['weather'][0]['main'])

        # Aggregate the 3-hour data into daily summaries
        weekly_plan = []
        for d, values in daily_forecasts.items():
            if len(weekly_plan) >= days: break # Ensure we don't exceed the requested number of days
            avg_temp = round(sum(values['temps']) / len(values['temps']), 1)
            # Find the most common weather condition for the day
            most_common_condition = max(set(values['conditions']), key=values['conditions'].count)
            weekly_plan.append({"date": d.isoformat(), "avg_temp": avg_temp, "condition": most_common_condition})
        
        return weekly_plan

    except httpx.HTTPStatusError:
        return [{"error": f"Failed to fetch weather forecast for {days} days."}]
