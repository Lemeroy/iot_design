"""火山引擎豆包 doubao-1.5-lite 客户端 (OpenAI 兼容接口).

安全边界:
  - 只接收数值评分 + 用户档案 (不含图像/音频)
  - 输出文本长度 <= 240 字, 避免 ST7789 显示折行
  - 医学表述遵循 Dr.Chen 免责声明模板
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

try:
    from openai import OpenAI
except ImportError:  # Native deployment may intentionally run in fallback mode.
    OpenAI = None  # type: ignore[assignment,misc]

from .schemas import LevelT, Profile, Scores

log = logging.getLogger(__name__)

SG_ADVICE_TEXT_MAX_BYTES = 384


def _truncate_utf8(text: str, max_bytes: int = SG_ADVICE_TEXT_MAX_BYTES) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    suffix = b"..."
    prefix = encoded[:max_bytes - len(suffix)].decode("utf-8", errors="ignore")
    return prefix + suffix.decode("ascii")

SYSTEM_PROMPT = """你是"卒中卫士"AI 健康助手。基于用户的五模态评分与档案,
生成一段面向老人及其家属的**简短建议**(120 字以内, 简体中文):

- 明确当前风险等级 (正常 / 警告 / 危险), 用词平实, 不吓人也不轻描淡写
- 若为 danger, 首句必须建议**立即拨打 120**, 并说明"识别脑卒中黄金时间窗 4.5 小时"
- 结合用户既往病史给出**1-2 条**可执行建议 (监测血压, 服药提醒, 陪同就医等)
- 不得推断用户未提供的用药; meds 为空时不得点名药物, 只能提示如有处方应遵医嘱
- 严禁自称医生, 严禁给出诊断结论, 严禁承诺治疗效果
- 严禁编造具体数字 (如"90% 中风概率"), 只做风险提示
- 输出纯文本, 不要 markdown 符号, 不要 emoji
"""


def _build_user_prompt(scores: Scores, level: LevelT,
                       profile: Profile, reasons: list) -> str:
    lines = [
        f"当前评分 (0-100 越低越危险):",
        f"  面部对称 F = {scores.face}",
        f"  言语清晰 S = {scores.speech}",
        f"  舌偏(辅助) T = {scores.tongue}",
        f"  眼动 E = {scores.eye}",
        f"  平衡(CSI) B = {scores.csi}",
        f"  融合总分 = {scores.final}",
        f"融合等级: {level}",
    ]
    if reasons:
        lines.append("触发原因: " + "; ".join(reasons))
    lines.append(f"用户档案: 年龄 {profile.age}, 性别 {profile.gender}")
    if profile.conditions:
        lines.append(f"慢性病: {', '.join(profile.conditions)}")
    if profile.meds:
        lines.append(f"长期用药: {', '.join(profile.meds)}")
    if profile.stroke_history:
        lines.append("既往卒中史: 有")
    lines.append("请生成建议:")
    return "\n".join(lines)


class DoubaoAdvisor:
    def __init__(self,
                 api_key: Optional[str] = None,
                 model: Optional[str] = None,
                 base_url: Optional[str] = None) -> None:
        self.api_key = api_key or os.environ.get("VOLC_ARK_API_KEY", "")
        self.model = model if model is not None else os.environ.get("VOLC_ARK_MODEL", "")
        self.base_url = base_url or os.environ.get(
            "VOLC_ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
        )
        self._client: Optional[OpenAI] = None
        self.available = bool(
            self.api_key
            and not self.api_key.startswith("<")
            and self.model
            and OpenAI is not None
        )
        if self.available:
            assert OpenAI is not None
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            log.info("DoubaoAdvisor ready, model=%s", self.model)
        else:
            log.warning("LLM API key, endpoint ID, or OpenAI SDK unavailable; advice will fallback")

    def generate(self, scores: Scores, level: LevelT,
                 profile: Profile, reasons: list) -> tuple[str, int]:
        """返回 (advice_text, latency_ms)."""
        t0 = time.time()
        if not self.available or self._client is None:
            return self._fallback(level, profile), 0

        user_prompt = _build_user_prompt(scores, level, profile, reasons)
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=240,
                timeout=15,
            )
            text = (resp.choices[0].message.content or "").strip()
            text = _truncate_utf8(text)
            latency = int((time.time() - t0) * 1000)
            return text, latency
        except Exception as e:
            log.exception("doubao call failed")
            if getattr(e, "status_code", None) in {400, 401, 403, 404}:
                self.available = False
                self._client = None
            return self._fallback(level, profile), int((time.time() - t0) * 1000)

    @staticmethod
    def _fallback(level: LevelT, profile: Profile) -> str:
        """LLM 不可用时的兜底文案 (Dr.Chen 会签)."""
        if level == "danger":
            return (
                "检测到高风险信号,请立即拨打 120 就医。"
                "识别脑卒中黄金时间窗为发病后 4.5 小时内。"
                "在等待救援时保持平卧,勿自行服药。"
            )
        if level == "warning":
            return (
                "本次评估存在异常提示,建议在 24 小时内前往神经内科复查。"
                "注意监测血压,规律服药,避免剧烈活动。"
            )
        if level == "insufficient":
            return "本次数据不足,建议在光线充足的环境重新检测。"
        return "本次评估未见明显异常,请保持规律作息与用药。"
