"""FastAPI 主入口.

端点:
  GET  /health              健康检查
  GET  /devices/{id}/latest 最近一次评分与建议
  POST /advice              手动触发一次 LLM 建议 (不经 MQTT)
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException

from .db_influx import InfluxWriter
from .llm_advice import DoubaoAdvisor
from .mqtt_bridge import MqttBridge
from .schemas import (
    HealthResp,
    LatestResp,
    ManualAdviceReq,
    ManualAdviceResp,
    Scores,
)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("sg-backend")

# ---------- 全局单例 (lifespan 里创建) ----------
_advisor: Optional[DoubaoAdvisor] = None
_influx: Optional[InfluxWriter] = None
_bridge: Optional[MqttBridge] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _advisor, _influx, _bridge
    _advisor = DoubaoAdvisor()
    _influx = InfluxWriter()
    loop = asyncio.get_running_loop()
    _bridge = MqttBridge(loop, _advisor, _influx)
    _bridge.start()
    log.info("backend ready")
    try:
        yield
    finally:
        if _bridge:
            _bridge.stop()
        if _influx:
            _influx.close()
        log.info("backend stopped")


app = FastAPI(title="StrokeGuard Cloud", version="0.1.0-m5", lifespan=lifespan)


@app.get("/health", response_model=HealthResp)
async def health() -> HealthResp:
    return HealthResp(
        status="ok",
        mqtt=_bridge.connected() if _bridge else False,
        influx=_influx.ping() if _influx else False,
        llm=_advisor.available if _advisor else False,
    )


@app.get("/devices/{device_id}/latest", response_model=LatestResp)
async def latest(device_id: str) -> LatestResp:
    if _bridge is None:
        raise HTTPException(500, "bridge not ready")
    cache = _bridge.latest.get(device_id)
    if not cache:
        return LatestResp(device_id=device_id)
    up = cache.get("uplink")
    adv = cache.get("advice")
    return LatestResp(
        device_id=device_id,
        last_uplink_ts=up.ts if up else None,
        last_advice=adv,
        latest_scores=up.scores if up else None,
        latest_level=up.level if up else None,
    )


@app.post("/advice", response_model=ManualAdviceResp)
async def manual_advice(req: ManualAdviceReq) -> ManualAdviceResp:
    if _advisor is None:
        raise HTTPException(500, "advisor not ready")
    text, latency = await asyncio.to_thread(
        _advisor.generate, req.scores, req.level, req.profile, req.reasons
    )
    return ManualAdviceResp(
        advice_text=text,
        latency_ms=latency,
        model=_advisor.model if _advisor.available else "fallback",
    )
