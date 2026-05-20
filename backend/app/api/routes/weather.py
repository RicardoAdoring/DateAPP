from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.weather_service import get_weather_forecast


class WeatherForecastDay(BaseModel):
    """单日天气预报。"""

    date: str | None = Field(default=None, description="日期")
    week: str | None = Field(default=None, description="星期索引")
    day_weather: str | None = Field(default=None, description="白天天气")
    night_weather: str | None = Field(default=None, description="夜间天气")
    day_temp: str | None = Field(default=None, description="白天温度")
    night_temp: str | None = Field(default=None, description="夜间温度")
    day_wind: str | None = Field(default=None, description="白天风向")
    night_wind: str | None = Field(default=None, description="夜间风向")


class WeatherForecastResponse(BaseModel):
    """天气预报接口响应。"""

    city: str = Field(..., description="城市名称")
    province: str | None = Field(default=None, description="省份")
    adcode: str | None = Field(default=None, description="行政区编码")
    report_time: str | None = Field(default=None, description="预报发布时间")
    days: list[WeatherForecastDay] = Field(default_factory=list, description="未来天气")


router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/forecast", response_model=WeatherForecastResponse)
def get_forecast(city: str = Query(..., description="目的地城市")) -> WeatherForecastResponse:
    """根据城市名称返回天气预报。"""
    try:
        payload = get_weather_forecast(city)
        return WeatherForecastResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
