from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import TextIO

APP_NAME = "DocOps Agent"
APP_DIRECTORY_NAME = "DocOpsAgent"
DEFAULT_API_PORT = 8000
DEFAULT_UI_PORT = 8501
STARTUP_TIMEOUT_SECONDS = 90
CONFIG_KEYS = frozenset(
    {
        "DOCOPS_LLM_PROVIDER",
        "DOCOPS_LLM_BASE_URL",
        "DOCOPS_LLM_API_KEY",
        "DOCOPS_LLM_MODEL",
        "DOCOPS_TOP_K",
        "DOCOPS_MIN_EVIDENCE_SCORE",
        "DOCOPS_MAX_UPLOAD_BYTES",
        "DOCOPS_APPROVAL_TTL_SECONDS",
        "DOCOPS_LOG_LEVEL",
    }
)
DEFAULT_CONFIG = """# DocOps Agent desktop configuration
# Changes take effect after the desktop application is restarted.

# The extractive provider runs offline and does not require an API key.
DOCOPS_LLM_PROVIDER=extractive

# To use an OpenAI-compatible /chat/completions endpoint, set all fields below.
DOCOPS_LLM_BASE_URL=https://api.openai.com/v1
DOCOPS_LLM_API_KEY=
DOCOPS_LLM_MODEL=

DOCOPS_TOP_K=4
DOCOPS_MIN_EVIDENCE_SCORE=0.08
DOCOPS_MAX_UPLOAD_BYTES=10485760
DOCOPS_APPROVAL_TTL_SECONDS=900
DOCOPS_LOG_LEVEL=INFO
"""


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _show_error(message: str) -> None:
    if os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
    else:
        print(f"{APP_NAME}: {message}", file=sys.stderr)


def _app_home() -> Path:
    override = os.getenv("DOCOPS_DESKTOP_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if local_app_data := os.getenv("LOCALAPPDATA"):
        return Path(local_app_data) / APP_DIRECTORY_NAME
    return Path.home() / f".{APP_DIRECTORY_NAME.lower()}"


def _prepare_app_home() -> tuple[Path, Path, Path]:
    app_home = _app_home()
    data_directory = app_home / "data"
    log_directory = app_home / "logs"
    data_directory.mkdir(parents=True, exist_ok=True)
    log_directory.mkdir(parents=True, exist_ok=True)
    config_path = app_home / "config.env"
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return app_home, log_directory, config_path


def _load_config(config_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        config_path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"config.env line {line_number} must use NAME=value")
        name, value = line.split("=", maxsplit=1)
        name = name.strip()
        if name not in CONFIG_KEYS:
            raise ValueError(f"config.env line {line_number} uses unsupported setting {name}")
        values[name] = value.strip()
    return values


def _available_port(preferred: int) -> int:
    for port in (preferred, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
                candidate.bind(("127.0.0.1", port))
                selected = candidate.getsockname()[1]
            if selected:
                return selected
        except OSError:
            if port == 0:
                raise
    raise RuntimeError("No local TCP port is available")


def _desktop_environment(config: dict[str, str], app_home: Path) -> tuple[dict[str, str], str]:
    api_port = _available_port(DEFAULT_API_PORT)
    ui_port = _available_port(DEFAULT_UI_PORT if api_port != DEFAULT_UI_PORT else 0)
    api_url = f"http://127.0.0.1:{api_port}"
    environment = os.environ.copy()
    environment.update(config)
    environment.update(
        {
            "DOCOPS_ENVIRONMENT": "development",
            "DOCOPS_DATABASE_PATH": str(app_home / "data" / "docops.db"),
            "DOCOPS_API_KEYS": "",
            "DOCOPS_CORS_ORIGINS": "",
            "DOCOPS_TRUSTED_HOSTS": "localhost,127.0.0.1",
            "DOCOPS_DOCS_ENABLED": "false",
            "DOCOPS_API_URL": api_url,
            "DOCOPS_API_KEY": "",
            "DOCOPS_UI_PASSWORD": "",
            "DOCOPS_DESKTOP_API_PORT": str(api_port),
            "DOCOPS_DESKTOP_UI_PORT": str(ui_port),
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        }
    )
    return environment, f"http://127.0.0.1:{ui_port}"


def _child_command(mode: str, parent_pid: int) -> list[str]:
    arguments = [mode, "--parent-pid", str(parent_pid)]
    if _is_frozen():
        return [sys.executable, *arguments]
    return [sys.executable, "-m", "docops_agent.desktop", *arguments]


def _watch_parent(parent_pid: int) -> None:
    if parent_pid <= 0:
        return
    if os.name == "nt":
        import ctypes

        synchronize = 0x00100000
        infinite = 0xFFFFFFFF
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(synchronize, False, parent_pid)
        if not handle:
            os._exit(0)
        try:
            kernel32.WaitForSingleObject(handle, infinite)
        finally:
            kernel32.CloseHandle(handle)
        os._exit(0)

    while os.getppid() == parent_pid:
        time.sleep(1)
    os._exit(0)


def _start_parent_watch(parent_pid: int) -> None:
    if parent_pid > 0:
        threading.Thread(target=_watch_parent, args=(parent_pid,), daemon=True).start()


def _run_api(parent_pid: int) -> int:
    _start_parent_watch(parent_pid)
    import uvicorn

    uvicorn.run(
        "docops_agent.api:app",
        host="127.0.0.1",
        port=int(os.environ["DOCOPS_DESKTOP_API_PORT"]),
        workers=1,
        access_log=False,
        server_header=False,
        log_level=os.getenv("DOCOPS_LOG_LEVEL", "INFO").lower(),
    )
    return 0


def _run_ui(parent_pid: int) -> int:
    _start_parent_watch(parent_pid)
    from streamlit.web import cli as streamlit_cli

    if _is_frozen():
        script_path = Path(sys._MEIPASS) / "docops_agent" / "streamlit_app.py"  # type: ignore[attr-defined]
    else:
        script_path = Path(__file__).resolve().with_name("streamlit_app.py")
    if not script_path.exists():
        raise FileNotFoundError(f"Bundled Streamlit entry point is missing: {script_path}")
    sys.argv = [
        "streamlit",
        "run",
        str(script_path),
        "--server.address=127.0.0.1",
        f"--server.port={os.environ['DOCOPS_DESKTOP_UI_PORT']}",
        "--server.headless=true",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    return int(streamlit_cli.main() or 0)


def _spawn_child(
    mode: str,
    environment: dict[str, str],
    parent_pid: int,
    log_handle: TextIO,
) -> subprocess.Popen[bytes]:
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(
        _child_command(mode, parent_pid),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
    )


def _wait_for_service(
    url: str,
    process: subprocess.Popen[bytes],
    name: str,
    timeout: int = STARTUP_TIMEOUT_SECONDS,
) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    last_error = "service did not respond"
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(f"{name} exited during startup with code {return_code}")
        try:
            with opener.open(url, timeout=2) as response:
                if 200 <= response.status < 300:
                    return
                last_error = f"HTTP {response.status}"
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise TimeoutError(f"{name} did not become ready within {timeout}s: {last_error}")


def _stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _read_log_tail(path: Path, limit: int = 3000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-limit:]


def _run_controller(
    ui_url: str, app_home: Path, config_path: Path, processes: list[subprocess.Popen[bytes]]
) -> None:
    webbrowser.open(ui_url)
    if os.name != "nt":
        input(f"{APP_NAME} is running at {ui_url}. Press Enter to stop.\n")
        return

    import ctypes

    message = (
        "DocOps Agent 已启动，知识库 API 和 Web UI 正在本机运行。\n\n"
        f"界面：{ui_url}\n"
        f"配置：{config_path}\n"
        f"数据和日志：{app_home}\n\n"
        "点击“确定”可重新打开界面。\n"
        "点击“取消”或关闭此窗口将停止服务。"
    )
    ok_cancel = 0x00000001
    information_icon = 0x00000040
    set_foreground = 0x00010000
    while all(process.poll() is None for process in processes):
        result = ctypes.windll.user32.MessageBoxW(
            None,
            message,
            APP_NAME,
            ok_cancel | information_icon | set_foreground,
        )
        if result != 1:
            return
        webbrowser.open(ui_url)
    _show_error("服务意外停止，请查看数据目录中的日志。")


def _single_instance_mutex() -> object | None:
    if os.name != "nt":
        return object()
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, f"Local\\{APP_DIRECTORY_NAME}Desktop")
    if not handle:
        return None
    if kernel32.GetLastError() == 183:
        kernel32.CloseHandle(handle)
        return None
    return handle


def _close_mutex(handle: object | None) -> None:
    if os.name == "nt" and handle:
        import ctypes

        ctypes.windll.kernel32.CloseHandle(handle)


def _run_desktop(*, smoke_test: bool = False) -> int:
    mutex = _single_instance_mutex()
    if mutex is None:
        _show_error("DocOps Agent 已经在运行。")
        return 2

    api_process: subprocess.Popen[bytes] | None = None
    ui_process: subprocess.Popen[bytes] | None = None
    api_log: TextIO | None = None
    ui_log: TextIO | None = None
    try:
        app_home, log_directory, config_path = _prepare_app_home()
        config = _load_config(config_path)
        environment, ui_url = _desktop_environment(config, app_home)
        api_log_path = log_directory / "api.log"
        ui_log_path = log_directory / "ui.log"
        api_log = api_log_path.open("w", encoding="utf-8", buffering=1)
        ui_log = ui_log_path.open("w", encoding="utf-8", buffering=1)

        api_process = _spawn_child("--api-server", environment, os.getpid(), api_log)
        _wait_for_service(
            f"{environment['DOCOPS_API_URL']}/health/ready",
            api_process,
            "API",
        )
        ui_process = _spawn_child("--ui-server", environment, os.getpid(), ui_log)
        _wait_for_service(f"{ui_url}/_stcore/health", ui_process, "UI")

        if not smoke_test:
            _run_controller(ui_url, app_home, config_path, [api_process, ui_process])
        return 0
    except Exception as exc:
        details = [str(exc)]
        if api_log is not None:
            api_log.flush()
        if ui_log is not None:
            ui_log.flush()
        if "api_log_path" in locals() and (tail := _read_log_tail(api_log_path)):
            details.append(f"\nAPI log:\n{tail}")
        if "ui_log_path" in locals() and (tail := _read_log_tail(ui_log_path)):
            details.append(f"\nUI log:\n{tail}")
        _show_error("\n".join(details))
        return 1
    finally:
        _stop_process(ui_process)
        _stop_process(api_process)
        if ui_log is not None:
            ui_log.close()
        if api_log is not None:
            api_log.close()
        _close_mutex(mutex)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DocOps Agent Windows desktop launcher")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--api-server", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--ui-server", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--smoke-test", action="store_true", help="start, verify and stop services")
    parser.add_argument("--parent-pid", type=int, default=0, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    arguments = _parse_args()
    if arguments.api_server:
        return _run_api(arguments.parent_pid)
    if arguments.ui_server:
        return _run_ui(arguments.parent_pid)
    return _run_desktop(smoke_test=arguments.smoke_test)


if __name__ == "__main__":
    raise SystemExit(main())
