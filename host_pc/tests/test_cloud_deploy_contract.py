from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_deploy_script_uses_env_backed_mqtt_users():
    deploy = (ROOT / "cloud" / "deploy.sh").read_text(encoding="utf-8")
    init_users = (ROOT / "cloud" / "scripts" / "init_mqtt_users.sh").read_text(encoding="utf-8")

    assert "mqtt_secret_sentinel_2026" not in deploy
    assert "backend_pass_2026" not in deploy
    assert "admin / strokeguard" not in deploy
    assert "bash scripts/init_mqtt_users.sh" in deploy
    assert "MQTT_HOST_PASS" in init_users
    assert "MQTT_APP_PASS" in init_users


def test_generated_emqx_auth_files_are_ignored():
    gitignore = (ROOT / "cloud" / ".gitignore").read_text(encoding="utf-8")

    assert "emqx/auth-built-in-db-bootstrap.csv" in gitignore


def test_cloud_env_has_no_utf8_bom_when_present():
    env_path = ROOT / "cloud" / ".env"
    if env_path.exists():
        assert not env_path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_deploy_normalizes_windows_line_endings_before_loading_env():
    deploy = (ROOT / "cloud" / "deploy.sh").read_text(encoding="utf-8")

    normalize = "sed -i 's/\\r$//' .env"
    assert normalize in deploy
    assert deploy.index(normalize) < deploy.index(". ./.env")
