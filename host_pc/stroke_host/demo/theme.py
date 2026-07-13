"""Presentation-focused visual tokens for the StrokeGuard desktop demo."""

COLORS = {
    "canvas": "#edf1ef",
    "surface": "#ffffff",
    "surface_alt": "#f5f8f6",
    "ink": "#18211e",
    "muted": "#65726d",
    "line": "#d5ddda",
    "green": "#16835f",
    "amber": "#b36b00",
    "red": "#bd3434",
    "gray": "#7b8581",
}

APP_STYLE = f"""
QMainWindow, QWidget#appRoot {{ background: {COLORS['canvas']}; }}
QWidget {{
    color: {COLORS['ink']};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei";
    font-size: 14px;
}}
QFrame#topBar, QFrame#loginPanel, QFrame#riskPanel, QFrame#advicePanel,
QFrame#maintenancePanel, QFrame[metricCard="true"] {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['line']};
    border-radius: 6px;
}}
QLabel#brandTitle {{ font-size: 27px; font-weight: 800; color: {COLORS['ink']}; }}
QLabel#brandSubtitle, QLabel#smallMeta, QLabel#adviceMeta {{ color: {COLORS['muted']}; font-size: 13px; }}
QLabel[metricValue="true"] {{ font-size: 36px; font-weight: 800; }}
QLabel[sectionTitle="true"] {{ font-size: 17px; font-weight: 700; }}
QLabel#riskLevel {{ font-size: 31px; font-weight: 800; }}
QLabel#adviceText {{ font-size: 15px; line-height: 1.5; }}
QLabel#connectionState {{ font-weight: 700; padding: 5px 10px; border-radius: 4px; }}
QLineEdit, QComboBox, QPlainTextEdit {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['line']};
    border-radius: 4px;
    padding: 7px 9px;
    selection-background-color: {COLORS['green']};
}}
QPlainTextEdit {{ font-family: Consolas, "Microsoft YaHei UI"; font-size: 13px; }}
QPushButton {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['line']};
    border-radius: 4px;
    padding: 7px 12px;
    font-weight: 600;
}}
QPushButton:hover {{ border-color: {COLORS['green']}; color: {COLORS['green']}; }}
QPushButton#primaryButton, QPushButton#loginButton {{
    background: {COLORS['green']}; color: white; border-color: {COLORS['green']};
}}
QPushButton#eraseButton {{ color: {COLORS['red']}; border-color: #e3bcbc; }}
QPushButton:disabled {{ color: #a0aaa6; background: #eef1ef; border-color: #dde3e0; }}
QCheckBox {{ spacing: 7px; }}
"""


def metric_color(value: int | None) -> str:
    if value is None:
        return COLORS["gray"]
    if value < 30:
        return COLORS["red"]
    if value < 60:
        return COLORS["amber"]
    return COLORS["green"]
