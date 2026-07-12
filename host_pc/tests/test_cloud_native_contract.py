from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
CLOUD = ROOT / "cloud"
NATIVE = CLOUD / "native"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_native_script_inventory_and_generated_paths_are_ignored():
    required = {
        "lib.sh",
        "install.sh",
        "start.sh",
        "stop.sh",
        "status.sh",
        "healthcheck.sh",
        "deploy_remote.sh",
    }

    assert required <= {path.name for path in NATIVE.glob("*.sh")}
    assert (NATIVE / "bootstrap.py").is_file()
    assert (NATIVE / "e2e_mqtt.py").is_file()
    assert (NATIVE / "config" / "emqx-base.hocon.template").is_file()
    assert (ROOT / "scripts" / "deploy_cloud_native_interactive.ps1").is_file()
    assert (ROOT / "scripts" / "run_cloud_e2e_interactive.ps1").is_file()
    assert (ROOT / "scripts" / "open_cloud_tunnel.ps1").is_file()
    assert (ROOT / "scripts" / "configure_llm_key_interactive.ps1").is_file()

    gitignore = read(CLOUD / ".gitignore")
    for generated in ("native/runtime/", "native/state/", "native/logs/", "native/run/", "native/downloads/"):
        assert generated in gitignore


def test_installer_pins_official_archives_and_verifies_sha256():
    install = read(NATIVE / "install.sh")
    base_requirements = read(CLOUD / "backend" / "requirements.txt")
    llm_requirements = read(CLOUD / "backend" / "requirements-llm.txt")

    assert "emqx-5.7.2-ubuntu22.04-amd64.tar.gz" in install
    assert "influxdb2-2.7.11_linux_amd64.tar.gz" in install
    assert "338b90fe101d5802ff921324e2bb1b745f220f9a6c8a8a6f992ad25afe8804a5" in install.lower()
    assert "8d7872013cad3524fb728ca8483d0adc30125ad1af262ab826dcf5d1801159cf" in install.lower()
    assert "sha256sum" in install
    assert "python3 -m venv" in install
    assert "pip==25.1.1" in install
    assert install.index("pip==25.1.1") < install.index('-r "$cloud_root/backend/requirements.txt"')
    assert "openai" not in base_requirements.lower()
    assert "openai>=1.30" in llm_requirements
    assert "https://pypi.org/simple" in install
    assert "LLM SDK unavailable" in install


def test_startup_is_local_idempotent_and_keeps_influx_private():
    start = read(NATIVE / "start.sh")
    lib = read(NATIVE / "lib.sh")

    assert start.index("start_influx") < start.index("start_emqx") < start.index("start_backend")
    assert "127.0.0.1:8086" in start
    assert 'MQTT_HOST="127.0.0.1"' in start
    assert 'INFLUX_URL="http://127.0.0.1:8086"' in start
    assert "EMQX_NODE__COOKIE" in start
    assert "node.cookie" in start
    assert "wait_http" in start
    assert "max_attempts" in lib
    assert "CHANGE_THIS" in lib
    assert "set -a" in lib and ". \"$cloud_root/.env\"" in lib
    assert '[ -d "/proc/$pid" ]' in lib


def test_lifecycle_scripts_use_scoped_pid_files_and_do_not_echo_secrets():
    combined = "\n".join(read(path) for path in NATIVE.glob("*.sh"))

    assert "kill -9" not in combined
    assert "pkill" not in combined
    for name in ("MQTT_APP_PASS", "MQTT_HOST_PASS", "INFLUX_TOKEN", "EMQX_DASHBOARD_PASS"):
        assert not re.search(rf"(?:echo|printf)[^\n]*\$\{{?{name}\b", combined)
    assert "pid_matches" in combined


def test_native_deploy_helper_targets_project_directory_without_password_literal():
    deploy = read(ROOT / "scripts" / "deploy_cloud_native_interactive.ps1")
    remote = read(NATIVE / "deploy_remote.sh")

    assert "/opt/strokeguard" in remote
    assert 'cloud_target="$deploy_root/cloud"' in remote
    assert '[string]$HostIp = $env:SG_VPS_HOST' in deploy
    assert '[string]$RemoteUser = "ubuntu"' in deploy
    assert "native/install.sh" in remote
    assert "deploy_remote.sh" in deploy
    assert "native/start.sh" in remote
    assert "native/healthcheck.sh" in remote
    assert 'bash "$cloud_target/native/stop.sh"' in remote
    assert remote.index('bash "$cloud_target/native/stop.sh"') < remote.index("for name in runtime")
    assert '[string]$SshPort = "22"' in deploy
    assert "sudo" in deploy
    assert "password=" not in deploy.lower()
    assert "76A0" not in deploy


def test_mqtt_e2e_probe_uses_numeric_payload_only():
    probe = read(NATIVE / "e2e_mqtt.py")

    assert '"scores"' in probe
    assert '"profile"' in probe
    assert '"device_id"' in probe
    assert "jpeg_b64" not in probe
    assert "mfcc" not in probe
    assert "127.0.0.1" in probe
    assert "Path.cwd()" in probe


def test_cloud_tunnel_exposes_only_expected_local_ports():
    tunnel = read(ROOT / "scripts" / "open_cloud_tunnel.ps1")

    assert "11883:127.0.0.1:1883" in tunnel
    assert "18000:127.0.0.1:8000" in tunnel
    assert "18084:127.0.0.1:18083" in tunnel
    assert "ExitOnForwardFailure=yes" in tunnel
    assert "-N" in tunnel


def test_main_launcher_uses_public_mqtt_and_has_no_embedded_password():
    launcher = read(ROOT / "launch.ps1")

    assert '[string]$MqttHost = $env:SG_MQTT_HOST' in launcher
    assert '[string]$MqttPort = "1883"' in launcher
    assert "cloud\\.env" in launcher
    assert "mqtt_secret_sentinel_2026" not in launcher
    assert "SG_MQTT_USER" in launcher


def test_llm_key_configurator_uses_secure_prompt_without_logging_secret():
    configurator = read(ROOT / "scripts" / "configure_llm_key_interactive.ps1")

    assert "Read-Host" in configurator
    assert "-AsSecureString" in configurator
    assert "VOLC_ARK_API_KEY" in configurator
    assert "Start-Transcript" not in configurator
    assert "Write-Host $plainKey" not in configurator


def test_cloud_config_uses_endpoint_id_instead_of_retired_model_name():
    llm = read(CLOUD / "backend" / "app" / "llm_advice.py")
    compose = read(CLOUD / "docker-compose.yml")
    example = read(CLOUD / ".env.example")

    assert "doubao-1-5-lite-32k-250115" not in llm
    assert "doubao-1-5-lite-32k-250115" not in compose
    assert "VOLC_ARK_MODEL=REPLACE_ME_ENDPOINT_ID" in example
