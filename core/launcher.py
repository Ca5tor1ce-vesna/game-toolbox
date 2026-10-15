"""打开界面：桌面窗口 / 默认浏览器。

桌面窗口用系统自带的 Edge 的 `--app=` 模式：没有地址栏和标签页，看起来就是一个独立程序窗口，
但**不用下载 Electron 那 200MB**，冷启动一秒不到。以后想换真正的原生壳，只改这个文件即可。
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from . import config


def find_edge() -> str | None:
    """找 Edge 可执行文件。找不到就返回 None（调用方会退回到默认浏览器）。"""
    candidates: list[Path] = []
    for env_key in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env_key)
        if base:
            candidates.append(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def open_window(
    url: str,
    size: tuple[int, int] = (1360, 900),
    shell: str = "edge",
    profile_dir: Path | None = None,
) -> str:
    """按 shell 打开界面，返回实际用的方式：edge / browser / none。"""
    if shell == "none":
        return "none"

    if shell in ("edge", "auto"):
        edge = find_edge()
        if edge:
            profile_dir = profile_dir or (config.USERDATA_DIR / "edge-profile")
            profile_dir.mkdir(parents=True, exist_ok=True)
            args = [
                edge,
                f"--app={url}",
                f"--window-size={size[0]},{size[1]}",
                # 用独立配置目录，不干扰你平时用的 Edge 窗口和账号
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=Translate,msEdgeIdentityIntegration",
            ]
            creationflags = 0
            if sys.platform == "win32":
                creationflags = getattr(subprocess, "DETACHED_PROCESS", 0)
            try:
                subprocess.Popen(args, creationflags=creationflags, close_fds=True)
                return "edge"
            except OSError as exc:
                print(f"[工具箱] 启动 Edge 窗口失败（{exc}），改用默认浏览器。")
        elif shell == "edge":
            print("[工具箱] 没找到 Edge，改用默认浏览器打开。")

    webbrowser.open(url)
    return "browser"
