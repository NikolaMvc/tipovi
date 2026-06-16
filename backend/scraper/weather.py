"""OpenWeatherMap lookup for the stadium city -> WeatherData with a
GOL_SUPPRESSING flag for rain / snow / strong wind."""
from __future__ import annotations

from typing import Optional

from backend.config import settings
from backend.schemas import WeatherData
from backend.scraper.utils import fetch_json, log

BASE = "https://api.openweathermap.org/data/2.5/weather"
SUPPRESSING_CONDITIONS = {"Rain", "Snow", "Thunderstorm", "Drizzle"}
STRONG_WIND_MS = 10.0


def get_weather(city: Optional[str]) -> Optional[WeatherData]:
    if not city or not settings.OPENWEATHER_API_KEY:
        return None
    data = fetch_json(BASE, params={
        "q": city,
        "appid": settings.OPENWEATHER_API_KEY,
        "units": "metric",
    })
    if not data or data.get("cod") not in (200, "200"):
        log.info("weather: no data for %s", city)
        return None

    main = data.get("main", {})
    wind = data.get("wind", {})
    conditions = (data.get("weather") or [{}])[0].get("main")
    wind_speed = wind.get("speed")

    gol_suppressing = bool(
        (conditions in SUPPRESSING_CONDITIONS)
        or (wind_speed is not None and wind_speed >= STRONG_WIND_MS)
    )
    return WeatherData(
        temp=main.get("temp"),
        conditions=conditions,
        wind_speed=wind_speed,
        gol_suppressing=gol_suppressing,
    )
