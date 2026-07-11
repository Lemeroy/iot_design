"""M4 visual theme contract tests."""


def test_theme_exposes_health_mirror_tokens():
    from stroke_host.ui.theme import APP_STYLE, HERO_LAYOUT, SURFACE, STATUS, UI_COPY

    assert SURFACE["app_bg"] == "#071311"
    assert STATUS["normal"] == "#31d17c"
    assert STATUS["warning"] == "#f5b84b"
    assert STATUS["danger"] == "#ff5b5b"
    assert HERO_LAYOUT["light_size"] == 132
    assert HERO_LAYOUT["score_font_pt"] == 108
    assert UI_COPY["app_title"] == "卒中卫士"
    assert "QMainWindow" in APP_STYLE
    assert "MirrorHero" in APP_STYLE


def test_score_color_and_status_light_styles_are_stable():
    from stroke_host.ui.theme import score_color, status_light_style

    assert score_color(None) == "#50615d"
    assert score_color(20) == "#ff5b5b"
    assert score_color(45) == "#f5b84b"
    assert score_color(80) == "#31d17c"

    danger_style = status_light_style("#ff5b5b", active=True)
    assert "border-radius: 66px" in danger_style
    assert "#ff5b5b" in danger_style
    assert "rgba(255, 91, 91" in danger_style


def test_modal_card_style_uses_professional_card_shape():
    from stroke_host.ui.theme import modal_card_style

    style = modal_card_style("#31d17c", active=True)

    assert "border-radius: 8px" in style
    assert "#31d17c" in style
    assert "ModalCard" in style


def test_combo_popup_has_readable_dropdown_colors():
    from stroke_host.ui.theme import APP_STYLE, STATUS, SURFACE

    assert "QComboBox QAbstractItemView" in APP_STYLE
    assert f"color: {SURFACE['text']}" in APP_STYLE
    assert f"selection-background-color: {STATUS['accent']}" in APP_STYLE
    assert "selection-color: #04110d" in APP_STYLE
