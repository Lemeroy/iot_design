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

from .auth_api import LoginRateLimiter, bootstrap_auth_store, router as auth_router
from .device_api import router as device_router
from .db_influx import InfluxWriter
from .llm_advice import DoubaoAdvisor
from .mqtt_bridge import MqttBridge
from .schemas import (
    HealthResp,
    ManualAdviceReq,
    ManualAdviceResp,
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
    app.state.auth_store = bootstrap_auth_store()
    app.state.auth_enabled = app.state.auth_store is not None
    app.state.auth_limiter = LoginRateLimiter()
    _advisor = DoubaoAdvisor()
    _influx = InfluxWriter()
    loop = asyncio.get_running_loop()
    _bridge = MqttBridge(loop, _advisor, _influx)
    app.state.bridge = _bridge
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
app.include_router(auth_router)
app.include_router(device_router)


@app.get("/health", response_model=HealthResp)
async def health() -> HealthResp:
    return HealthResp(
        status="ok",
        mqtt=_bridge.connected() if _bridge else False,
        influx=_influx.ping() if _influx else False,
        llm=_advisor.available if _advisor else False,
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
