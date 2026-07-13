import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_demo_environment_template_leaves_optional_auth_disabled_by_default():
    example = read(ROOT / "cloud" / ".env.example")

    for name in (
        "SG_DEMO_USER",
        "SG_DEMO_PASSWORD",
        "SG_DEMO_SESSION_SECRET",
        "SG_ALLOW_INSECURE_HTTP",
    ):
        assert f"{name}=" in example
    assert "SG_ALLOW_INSECURE_HTTP=0" in example
    assert "SG_DEMO_USER=" in example
    assert "SG_DEMO_PASSWORD=" in example
    assert "SG_DEMO_SESSION_SECRET=" in example
    assert "SG_DEMO_USER=CHANGE_THIS" not in example
    assert "SG_DEMO_PASSWORD=CHANGE_THIS" not in example
    assert "SG_DEMO_SESSION_SECRET=CHANGE_THIS" not in example
    assert "Example: SG_DEMO_USER=demo-user" in example
    assert "Example: SG_DEMO_PASSWORD=choose-a-strong-password" in example
    assert "Example: SG_DEMO_SESSION_SECRET=generate-a-long-random-secret" in example


def test_native_start_exports_optional_demo_settings_without_making_them_required():
    start = read(ROOT / "cloud" / "native" / "start.sh")

    for name in (
        "SG_DEMO_USER",
        "SG_DEMO_PASSWORD",
        "SG_DEMO_SESSION_SECRET",
        "SG_ALLOW_INSECURE_HTTP",
    ):
        assert f'export {name}="${{{name}:-}}"' in start
        assert name not in start.split("require_env", 1)[1].split("influx_bin", 1)[0]


def test_demo_deployment_docs_limit_monitor_scope_and_require_recent_uplink():
    docs = "\n".join(
        (
            read(ROOT / "cloud" / "README.md"),
            read(ROOT / "README.md"),
        )
    ).lower()

    assert "device id" in docs
    assert "last 30 seconds" in docs
    assert "read-only" in docs
    assert "monitoring scores/status" in docs
    assert "latest llm advice" in docs
    assert "https" in docs
    assert "sg_allow_insecure_http=1" in docs
    for excluded in (
        "profile",
        "wi-fi",
        "mqtt",
        "fusion",
        "thresholds",
        "veto rules",
        "remote commands",
        "raw audio",
        "raw video",
        "mfcc",
        "landmarks",
        "roi",
    ):
        assert excluded in docs


def test_release_wrapper_preserves_two_artifact_build_and_checks_demo_handoff_contents():
    package = read(ROOT / "scripts" / "package_release.ps1")

    assert "build_release.ps1" in package
    assert "StrokeGuard-Demo.exe" in package
    assert "StrokeGuard-Developer-Handoff.zip" in package
    assert "cloud/backend/app/static/demo/" in package
    assert "cloud/README.md" in package
    assert "cloud/.env" in package
    assert "raw audio" in package.lower()
    assert "raw video" in package.lower()
    assert "mfcc" in package.lower()
    assert "landmarks" in package.lower()
    assert "roi" in package.lower()


def test_release_wrapper_validates_paths_without_building_and_reuses_its_helper():
    package = read(ROOT / "scripts" / "package_release.ps1")

    assert "[string[]]$ValidatePaths" in package
    assert "function Assert-ReleasePathsAllowed" in package
    assert "Assert-ReleasePathsAllowed -Paths $trackedPaths -Source \"tracked\"" in package
    assert "Assert-ReleasePathsAllowed -Paths $entries -Source \"archive\"" in package


@pytest.mark.parametrize("cache_dir", (".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"))
def test_release_wrapper_rejects_cache_paths_via_validate_paths(cache_dir):
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "package_release.ps1"),
            "-ValidatePaths",
            f"host_pc/{cache_dir}/state",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Forbidden release path" in result.stderr


def test_release_wrapper_accepts_safe_paths_via_validate_paths():
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "package_release.ps1"),
            "-ValidatePaths",
            "cloud/README.md",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
