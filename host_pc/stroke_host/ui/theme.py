"""Visual theme for the StrokeGuard PyQt5 health mirror UI."""
from __future__ import annotations

from typing import Optional

SURFACE = {
    "app_bg": "#071311",
    "panel": "#0d1e1b",
    "panel_soft": "#102923",
    "panel_lift": "#15342d",
    "line": "#255147",
    "text": "#eaf7f2",
    "muted": "#8ba59d",
    "faint": "#50615d",
}

STATUS = {
    "normal": "#31d17c",
    "warning": "#f5b84b",
    "danger": "#ff5b5b",
    "insufficient": SURFACE["faint"],
    "accent": "#58d7d1",
}

UI_COPY = {
    "app_title": "卒中卫士",
    "subtitle": "FAST / BE-FAST 多模态早期风险提示",
    "advice_title": "个性化建议",
}

HERO_LAYOUT = {
    "light_size": 132,
    "score_font_pt": 108,
}


def score_color(score: Optional[int]) -> str:
    if score is None or score < 0:
        return STATUS["insufficient"]
    if score < 30:
        return STATUS["danger"]
    if score < 60:
        return STATUS["warning"]
    return STATUS["normal"]


def modal_card_style(color: str, active: bool = False) -> str:
    glow = f"rgba(49, 209, 124, 0.22)" if active else "rgba(0, 0, 0, 0.18)"
    return f"""
    ModalCard {{
        background: {SURFACE["panel_soft"]};
        border: 1px solid {color};
        border-radius: 8px;
        padding: 8px;
    }}
    ModalCard:hover {{
        background: {SURFACE["panel_lift"]};
        border: 1px solid {STATUS["accent"]};
    }}
    QLabel {{
        background: transparent;
    }}
    /* glow={glow} */
    """


def status_light_style(color: str, active: bool = False) -> str:
    alpha = "0.42" if active else "0.18"
    radius = HERO_LAYOUT["light_size"] // 2
    return f"""
    border-radius: {radius}px;
    background: qradialgradient(
        cx:0.42, cy:0.35, radius:0.82,
        fx:0.36, fy:0.28,
        stop:0 rgba(255,255,255,0.86),
        stop:0.16 {color},
        stop:0.68 {color},
        stop:1 rgba(7,19,17,0.90)
    );
    border: 2px solid {color};
    /* glow: rgba(255, 91, 91, {alpha}); */
    """


APP_STYLE = f"""
QMainWindow {{
    background: {SURFACE["app_bg"]};
    color: {SURFACE["text"]};
}}
QWidget {{
    color: {SURFACE["text"]};
    font-family: "Microsoft YaHei", "Segoe UI";
    font-size: 13px;
}}
QLabel#BrandTitle {{
    color: {SURFACE["text"]};
    font-size: 28px;
    font-weight: 700;
}}
QLabel#BrandSubtitle {{
    color: {SURFACE["muted"]};
    font-size: 12px;
}}
QFrame#MirrorHero, QFrame#ControlStrip, QFrame#AdvicePanel {{
    background: {SURFACE["panel"]};
    border: 1px solid {SURFACE["line"]};
    border-radius: 8px;
}}
QFrame#MirrorHero {{
    background: {SURFACE["panel_soft"]};
}}
QPushButton {{
    background: {SURFACE["panel_lift"]};
    border: 1px solid {SURFACE["line"]};
    border-radius: 6px;
    padding: 7px 12px;
    color: {SURFACE["text"]};
}}
QPushButton:hover {{
    border-color: {STATUS["accent"]};
    background: #183d35;
}}
QPushButton#PrimaryButton {{
    background: {STATUS["normal"]};
    color: #04110d;
    border: 1px solid {STATUS["normal"]};
    font-weight: 700;
}}
QPushButton#DangerButton {{
    background: #3b1717;
    color: #ffdada;
    border: 1px solid {STATUS["danger"]};
}}
QLineEdit, QComboBox {{
    background: #0a1715;
    border: 1px solid {SURFACE["line"]};
    border-radius: 6px;
    padding: 6px 8px;
    color: {SURFACE["text"]};
    selection-background-color: {STATUS["accent"]};
}}
QComboBox QAbstractItemView {{
    background: #0a1715;
    color: {SURFACE["text"]};
    border: 1px solid {STATUS["accent"]};
    outline: 0;
    padding: 4px;
    selection-background-color: {STATUS["accent"]};
    selection-color: #04110d;
}}
QComboBox QAbstractItemView::item {{
    min-height: 28px;
    padding: 5px 8px;
}}
QComboBox QAbstractItemView::item:selected {{
    background: {STATUS["accent"]};
    color: #04110d;
}}
QCheckBox {{
    spacing: 7px;
    color: {SURFACE["muted"]};
}}
QTextEdit {{
    background: #081714;
    border: 1px solid {SURFACE["line"]};
    border-radius: 8px;
    color: {SURFACE["text"]};
    padding: 8px;
}}
QLabel#MetricTitle {{
    color: {SURFACE["muted"]};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#MetricScore {{
    font-size: 38px;
    font-weight: 800;
}}
QLabel#SmallMeta {{
    color: {SURFACE["muted"]};
    font-size: 11px;
}}
"""
