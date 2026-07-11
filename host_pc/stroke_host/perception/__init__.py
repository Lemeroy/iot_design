"""感知模块 (M2 起).

对外统一返回 ModalScore(score:int 0-100, reasons:list[str], raw:dict).
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ModalScore:
    """单模态评分结果."""
    score: int              # 0-100, 越低越危险; -1 表示不可用
    reasons: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.score >= 0
