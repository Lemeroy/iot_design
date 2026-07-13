"""Controlled ESP-IDF task runner for the desktop maintenance page."""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, TextIO

from .schema import DeploymentConfig, redact_text


SUPPORTED_IDF_VERSION = "5.5.3"
COM_PORT_RE = re.compile(r"^COM[1-9][0-9]{0,2}$", re.IGNORECASE)


class IdfRunnerError(RuntimeError):
    """A provisioning stage could not be completed safely."""


@dataclass(frozen=True)
class IdfInstallation:
    root: Path
    version: str

    @classmethod
    def discover(cls, preferred: Path | None = None) -> "IdfInstallation":
        root = (preferred or Path(r"E:\esp\v5.5.3\esp-idf")).expanduser().resolve()
        export_script = root / "export.ps1"
        if not export_script.is_file():
            raise IdfRunnerError(f"ESP-IDF installation not found: {root}")
        version = _read_idf_version(root)
        if version != SUPPORTED_IDF_VERSION:
            raise IdfRunnerError(
                f"ESP-IDF {SUPPORTED_IDF_VERSION} is required; found {version or 'unknown'}"
            )
        return cls(root=root, version=version)


def _read_idf_version(root: Path) -> str:
    version_file = root / "version.txt"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()

    cmake_file = root / "tools" / "cmake" / "version.cmake"
    if not cmake_file.is_file():
        return ""
    content = cmake_file.read_text(encoding="utf-8")
    parts: list[str] = []
    for name in ("MAJOR", "MINOR", "PATCH"):
        match = re.search(
            rf"set\(IDF_VERSION_{name}\s+([0-9]+)\s*\)",
            content,
        )
        if match is None:
            return ""
        parts.append(match.group(1))
    return ".".join(parts)


@dataclass(frozen=True)
class StageEvent:
    stage: str
    status: str
    message: str


class _Process(Protocol):
    stdout: TextIO
    returncode: int

    def wait(self) -> int: ...
    def terminate(self) -> None: ...


class IdfRunner:
    def __init__(
        self,
        installation: IdfInstallation,
        project_dir: Path,
        *,
        launcher: Callable[..., _Process] = subprocess.Popen,
        on_event: Callable[[StageEvent], None] | None = None,
        script_path: Path | None = None,
    ) -> None:
        self.installation = installation
        self.project_dir = project_dir.resolve()
        self._launcher = launcher
        self._on_event = on_event or (lambda event: None)
        self._script_path = (
            script_path or self.project_dir.parent / "scripts" / "run_idf_task.ps1"
        ).resolve()
        self._generated_dir = self.project_dir / ".strokeguard-build"
        self._overlay_path = self._generated_dir / "sdkconfig.defaults"
        self._config: DeploymentConfig | None = None
        self._active_process: _Process | None = None
        self._lock = threading.Lock()

    def prepare(self, config: DeploymentConfig) -> Path:
        self._generated_dir.mkdir(parents=True, exist_ok=True)
        content = "# Generated locally by StrokeGuard; contains credentials.\n"
        content += "\n".join(f"{key}={value}" for key, value in sorted(config.kconfig.items()))
        content += "\n"
        self._overlay_path.write_text(content, encoding="utf-8")
        self._config = config
        self._emit("prepare", "success", "部署配置已校验并生成本地构建配置")
        return self._overlay_path

    def build(self) -> None:
        if self._config is None or not self._overlay_path.is_file():
            raise IdfRunnerError("prepare must complete before build")
        self._run("build", "build")

    def erase(self, port: str, confirmed: bool) -> None:
        if not confirmed:
            raise IdfRunnerError("erase confirmation is required")
        self._run("erase", "erase", port=self._validate_port(port))

    def flash(self, port: str) -> None:
        self._run("flash", "flash", port=self._validate_port(port))

    def cancel(self) -> None:
        with self._lock:
            process = self._active_process
        if process is not None:
            process.terminate()
            self._emit("task", "cancelled", "操作已取消")

    def cleanup(self) -> None:
        self.cancel()
        if self._generated_dir.exists():
            shutil.rmtree(self._generated_dir)
        self._config = None

    def _run(self, stage: str, action: str, port: str | None = None) -> None:
        args = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self._script_path),
            "-IdfPath",
            str(self.installation.root),
            "-ProjectPath",
            str(self.project_dir),
            "-Action",
            action,
        ]
        if self._overlay_path.is_file():
            args.extend(["-OverlayPath", str(self._overlay_path)])
        if port is not None:
            args.extend(["-Port", port])
        self._emit(stage, "running", f"{stage} 开始")
        process = self._launcher(
            args,
            cwd=self.project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        with self._lock:
            self._active_process = process
        try:
            for line in process.stdout:
                message = line.rstrip("\r\n")
                if message:
                    self._emit(stage, "output", self._redact(message))
            code = process.wait()
        finally:
            with self._lock:
                self._active_process = None
        if code != 0:
            self._emit(stage, "failed", f"{stage} 失败，退出码 {code}")
            raise IdfRunnerError(f"{stage} failed with exit code {code}")
        self._emit(stage, "success", f"{stage} 完成")

    def _redact(self, message: str) -> str:
        return redact_text(message, self._config) if self._config is not None else message

    def _emit(self, stage: str, status: str, message: str) -> None:
        self._on_event(StageEvent(stage=stage, status=status, message=self._redact(message)))

    @staticmethod
    def _validate_port(port: str) -> str:
        normalized = port.strip().upper()
        if not COM_PORT_RE.fullmatch(normalized):
            raise IdfRunnerError("invalid COM port")
        return normalized
