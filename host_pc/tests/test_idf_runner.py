from __future__ import annotations

from pathlib import Path

import pytest

from test_deployment_schema import BASE_ENV, deployment_data


class FakeProcess:
    def __init__(self, returncode=0, lines=()):
        self.returncode = returncode
        self.stdout = iter(lines)
        self.terminated = False

    def wait(self):
        return self.returncode

    def terminate(self):
        self.terminated = True


class FakeLauncher:
    def __init__(self, processes=None):
        self.processes = list(processes or [FakeProcess()])
        self.calls = []

    def __call__(self, args, *, cwd, stdout, stderr, text, encoding, errors):
        self.calls.append((list(args), Path(cwd)))
        return self.processes.pop(0)


def make_idf(tmp_path: Path, version="5.5.3") -> Path:
    root = tmp_path / "esp-idf"
    root.mkdir()
    (root / "export.ps1").write_text("# test", encoding="utf-8")
    (root / "version.txt").write_text(version, encoding="utf-8")
    return root


def test_idf_installation_discovers_exact_supported_version(tmp_path):
    from stroke_host.deployment.idf_runner import IdfInstallation

    root = make_idf(tmp_path)

    installation = IdfInstallation.discover(root)

    assert installation.root == root.resolve()
    assert installation.version == "5.5.3"


def test_idf_installation_reads_official_cmake_version_layout(tmp_path):
    from stroke_host.deployment.idf_runner import IdfInstallation

    root = make_idf(tmp_path)
    (root / "version.txt").unlink()
    cmake = root / "tools" / "cmake"
    cmake.mkdir(parents=True)
    (cmake / "version.cmake").write_text(
        "set(IDF_VERSION_MAJOR 5)\n"
        "set(IDF_VERSION_MINOR 5)\n"
        "set(IDF_VERSION_PATCH 3)\n",
        encoding="utf-8",
    )

    installation = IdfInstallation.discover(root)

    assert installation.version == "5.5.3"


def test_idf_installation_rejects_missing_or_wrong_version(tmp_path):
    from stroke_host.deployment.idf_runner import IdfInstallation, IdfRunnerError

    with pytest.raises(IdfRunnerError, match="ESP-IDF"):
        IdfInstallation.discover(tmp_path / "missing")

    wrong = make_idf(tmp_path, "5.4.0")
    with pytest.raises(IdfRunnerError, match="5.5.3"):
        IdfInstallation.discover(wrong)


def test_prepare_writes_isolated_sdkconfig_without_emitting_secrets(tmp_path):
    from stroke_host.deployment.idf_runner import IdfInstallation, IdfRunner
    from stroke_host.deployment.schema import validate_deployment

    idf = IdfInstallation.discover(make_idf(tmp_path))
    project = tmp_path / "firmware"
    project.mkdir()
    (project / "sdkconfig.defaults").write_text("CONFIG_IDF_TARGET=\"esp32s3\"\n")
    events = []
    runner = IdfRunner(idf, project, launcher=FakeLauncher(), on_event=events.append)
    config = validate_deployment(deployment_data(), BASE_ENV)

    generated = runner.prepare(config)
    content = generated.read_text(encoding="utf-8")

    assert generated.parent == project / ".strokeguard-build"
    assert "CONFIG_STROKEGUARD_DEVICE_ID=\"sg-0002\"" in content
    assert "wifi-secret" in content
    assert all("wifi-secret" not in event.message for event in events)
    runner.cleanup()
    assert not generated.exists()


def test_build_uses_fixed_powershell_script_and_argument_array(tmp_path):
    from stroke_host.deployment.idf_runner import IdfInstallation, IdfRunner
    from stroke_host.deployment.schema import validate_deployment

    idf = IdfInstallation.discover(make_idf(tmp_path))
    project = tmp_path / "firmware"
    project.mkdir()
    launcher = FakeLauncher([FakeProcess(lines=["Building\n", "Done\n"])])
    events = []
    runner = IdfRunner(idf, project, launcher=launcher, on_event=events.append)
    runner.prepare(validate_deployment(deployment_data(), BASE_ENV))

    runner.build()

    args, cwd = launcher.calls[0]
    assert args[:4] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    assert "build" in args
    assert cwd == project
    assert events[-1].stage == "build"
    assert events[-1].status == "success"


def test_erase_requires_explicit_confirmation_and_valid_com_port(tmp_path):
    from stroke_host.deployment.idf_runner import IdfInstallation, IdfRunner, IdfRunnerError

    runner = IdfRunner(
        IdfInstallation.discover(make_idf(tmp_path)),
        tmp_path,
        launcher=FakeLauncher(),
    )

    with pytest.raises(IdfRunnerError, match="confirmation"):
        runner.erase("COM5", confirmed=False)
    with pytest.raises(IdfRunnerError, match="COM port"):
        runner.erase("COM5; Remove-Item *", confirmed=True)


def test_flash_failure_reports_failed_stage(tmp_path):
    from stroke_host.deployment.idf_runner import IdfInstallation, IdfRunner, IdfRunnerError

    events = []
    runner = IdfRunner(
        IdfInstallation.discover(make_idf(tmp_path)),
        tmp_path,
        launcher=FakeLauncher([FakeProcess(returncode=2, lines=["fatal error\n"])]),
        on_event=events.append,
    )

    with pytest.raises(IdfRunnerError, match="flash failed"):
        runner.flash("COM5")

    assert events[-1].stage == "flash"
    assert events[-1].status == "failed"


def test_cancel_terminates_active_child_process(tmp_path):
    from stroke_host.deployment.idf_runner import IdfInstallation, IdfRunner

    runner = IdfRunner(IdfInstallation.discover(make_idf(tmp_path)), tmp_path)
    process = FakeProcess()
    runner._active_process = process

    runner.cancel()

    assert process.terminated is True
