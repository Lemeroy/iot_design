from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_pushplus_environment_is_documented_and_exported_by_native_start():
    env_example = (ROOT / "cloud" / ".env.example").read_text(encoding="utf-8")
    native_start = (ROOT / "cloud" / "native" / "start.sh").read_text(encoding="utf-8")

    assert "PUSHPLUS_ENABLED=0" in env_example
    assert "PUSHPLUS_TOKEN=" in env_example
    assert "PUSHPLUS_DEVICE_NAME=" in env_example
    for name in ("PUSHPLUS_ENABLED", "PUSHPLUS_TOKEN", "PUSHPLUS_DEVICE_NAME"):
        assert f'export {name}="${{{name}:-' in native_start


def test_pushplus_configurator_masks_secret_and_writes_env_atomically():
    source = (ROOT / "scripts" / "configure_pushplus_interactive.ps1").read_text(
        encoding="utf-8"
    )

    assert "Read-Host" in source
    assert "-AsSecureString" in source
    assert "SecureStringToBSTR" in source
    assert "ZeroFreeBSTR" in source
    assert "PUSHPLUS_ENABLED" in source
    assert "PUSHPLUS_TOKEN" in source
    assert "PUSHPLUS_DEVICE_NAME" in source
    assert ".tmp" in source
    assert "WriteAllLines" in source
    assert "Move-Item" in source
    assert "RandomNumberGenerator]::Fill" not in source
    assert "Write-Host $plainToken" not in source


def test_cloud_secret_environment_file_is_gitignored():
    gitignore = (ROOT / "cloud" / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore.splitlines()
