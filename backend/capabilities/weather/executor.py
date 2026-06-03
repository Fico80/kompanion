import requests
from shared.i18n import lang


_WEATHER_DESC_DE = {
    "Sunny": "☀️ Sonnig",
    "Clear": "🌙 Klar",
    "Partly cloudy": "⛅ Teilweise bewölkt",
    "Cloudy": "☁️ Bewölkt",
    "Overcast": "☁️ Bedeckt",
    "Mist": "🌫️ Neblig",
    "Fog": "🌫️ Nebel",
    "Light rain": "🌦️ Leichter Regen",
    "Moderate rain": "🌧️ Regen",
    "Heavy rain": "🌧️ Starker Regen",
    "Light snow": "🌨️ Leichter Schnee",
    "Moderate snow": "❄️ Schnee",
    "Heavy snow": "❄️ Starker Schnee",
    "Thundery outbreaks possible": "⛈️ Gewitter möglich",
    "Blizzard": "🌨️ Schneesturm",
    "Patchy rain possible": "🌦️ Vereinzelt Regen",
    "Patchy snow possible": "🌨️ Vereinzelt Schnee",
}


def _day_label(day: str | None, response_lang: str) -> str:
    if day == "tomorrow":
        return "morgen" if response_lang == "de" else "tomorrow"
    return "heute" if response_lang == "de" else "today"


def _forecast_desc(day_data: dict) -> str:
    hourly = day_data.get("hourly") or []
    if hourly:
        noon = hourly[min(4, len(hourly) - 1)]
        return noon.get("weatherDesc", [{}])[0].get("value", "")
    return ""


def query_weather(city: str | None, aspect: str | None = None,
                  response_lang: str = "en", day: str | None = "today") -> dict:
    location = city.strip() if city else ""
    wttr_lang = "de" if response_lang == "de" else "en"
    url = f"https://wttr.in/{location}?format=j1&lang={wttr_lang}"
    try:
        resp = requests.get(url, timeout=6, headers={"User-Agent": "lokaler-assistent/1.0"})
        resp.raise_for_status()
        data = resp.json()

        cur = data["current_condition"][0]
        temp = cur["temp_C"]
        feels = cur["FeelsLikeC"]
        humidity = cur["humidity"]
        wind = cur["windspeedKmph"]
        desc_raw = cur["weatherDesc"][0]["value"]
        desc = _WEATHER_DESC_DE.get(desc_raw, desc_raw) if response_lang == "de" else desc_raw

        day_index = 1 if day == "tomorrow" and len(data.get("weather", [])) > 1 else 0
        forecast = data["weather"][day_index]
        t_min = forecast["mintempC"]
        t_max = forecast["maxtempC"]
        avg_temp = forecast.get("avgtempC", temp)
        forecast_desc_raw = _forecast_desc(forecast) or desc_raw
        forecast_desc = _WEATHER_DESC_DE.get(forecast_desc_raw, forecast_desc_raw) if response_lang == "de" else forecast_desc_raw
        day_word = _day_label(day, response_lang)

        area = data.get("nearest_area", [{}])[0]
        city_name = area.get("areaName", [{}])[0].get("value", location or ("Aktueller Standort" if response_lang == "de" else "Current location"))

        if day == "tomorrow":
            if aspect == "temperature":
                msg = f"{city_name}: {day_word} etwa {avg_temp}°C · {forecast_desc}" if response_lang == "de" else f"{city_name}: about {avg_temp}°C {day_word} · {forecast_desc}"
            elif aspect == "max_temp":
                msg = f"{city_name}: Höchsttemperatur {day_word} {t_max}°C" if response_lang == "de" else f"{city_name}: {day_word}'s high is {t_max}°C"
            elif aspect == "min_temp":
                msg = f"{city_name}: Tiefsttemperatur {day_word} {t_min}°C" if response_lang == "de" else f"{city_name}: {day_word}'s low is {t_min}°C"
            elif aspect in ("rain", "snow"):
                msg = f"{city_name}: {day_word} {forecast_desc} · Min {t_min}° / Max {t_max}°" if response_lang == "de" else f"{city_name}: {forecast_desc} {day_word} · Low {t_min}° / High {t_max}°"
            else:
                msg = (
                    f"{city_name}: {day_word} {forecast_desc}, etwa {avg_temp}°C · Min {t_min}° / Max {t_max}°"
                    if response_lang == "de"
                    else f"{city_name}: {forecast_desc} {day_word}, about {avg_temp}°C · Low {t_min}° / High {t_max}°"
                )
        elif aspect == "temperature":
            msg = f"{city_name}: {temp}°C (fühlt sich an wie {feels}°C) · {desc}" if response_lang == "de" else f"{city_name}: {temp}°C (feels like {feels}°C) · {desc}"
        elif aspect == "max_temp":
            msg = f"{city_name}: Höchsttemperatur heute {t_max}°C" if response_lang == "de" else f"{city_name}: today's high is {t_max}°C"
        elif aspect == "min_temp":
            msg = f"{city_name}: Tiefsttemperatur heute {t_min}°C" if response_lang == "de" else f"{city_name}: today's low is {t_min}°C"
        elif aspect == "wind":
            msg = f"{city_name}: Wind {wind} km/h"
        elif aspect == "humidity":
            msg = f"{city_name}: Luftfeuchtigkeit {humidity}%" if response_lang == "de" else f"{city_name}: humidity {humidity}%"
        elif aspect in ("rain", "snow"):
            msg = f"{city_name}: {desc} · Min {t_min}° / Max {t_max}°"
        else:
            if response_lang == "de":
                msg = (
                    f"{city_name}: {desc}, {temp}°C (fühlt sich an wie {feels}°C) · "
                    f"Min {t_min}° / Max {t_max}° · "
                    f"Luftfeuchtigkeit {humidity}% · Wind {wind} km/h"
                )
            else:
                msg = (
                    f"{city_name}: {desc}, {temp}°C (feels like {feels}°C) · "
                    f"Min {t_min}° / Max {t_max}° · "
                    f"Humidity {humidity}% · Wind {wind} km/h"
                )
        return {"success": True, "message": msg}

    except requests.exceptions.Timeout:
        msg = "Wetter-API antwortet nicht." if response_lang == "de" else "Weather API is not responding."
        return {"success": False, "message": msg}
    except Exception as e:
        msg = f"Wetterfehler: {e}" if response_lang == "de" else f"Weather error: {e}"
        return {"success": False, "message": msg}


def execute(parsed: dict) -> dict | None:
    if parsed.get("action") == "query_weather":
        return query_weather(parsed.get("target"), parsed.get("weather_aspect"), lang(parsed), parsed.get("weather_day"))
    return None
