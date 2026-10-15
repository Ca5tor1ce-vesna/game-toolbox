"""工具箱的路径与配置。

配置写在项目根目录的 `config.json`：端口、外壳类型、窗口大小、心跳看门狗时长。
用户数据写在 `userdata/`，与代码分离，升级代码不会丢数据。
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

_SOURCE_ROOT = Path(__file__).resolve().parent.parent
# 打包成 exe 之后，代码和模块在 _internal（只读、升级会被覆盖），
# 用户数据必须放在 exe 旁边。写进 _internal 会在升级时丢掉，也容易把
# Edge 的浏览记录一起打进发布包。
if getattr(sys, "frozen", False):
    BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", _SOURCE_ROOT))
    ROOT = Path(sys.executable).resolve().parent
else:
    BUNDLE_ROOT = _SOURCE_ROOT
    ROOT = _SOURCE_ROOT
APP_DIR = BUNDLE_ROOT / "app"
MODULES_DIR = BUNDLE_ROOT / "modules"


def _resolve_userdata() -> Path:
    """用户数据目录。默认 `<ROOT>/userdata`（exe 版是 exe 旁边），可用环境变量
    `GT_USERDATA` 覆盖（测试用临时目录，避免和正在运行的服务抢 userdata）。
    相对路径按 ROOT 解析；空值或带 `..` 的值忽略。"""
    raw = os.environ.get("GT_USERDATA", "").strip().strip('"')
    if not raw or ".." in raw:
        return ROOT / "userdata"
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


USERDATA_DIR = _resolve_userdata()
DOCS_DIR = BUNDLE_ROOT / "docs"
CONFIG_PATH = ROOT / "config.json"
# 外壳级覆盖（功能改名/隐藏/排序）——由「界面 → 功能与文字」写入，作者自己用。
# 放在 userdata 下：升级代码不会丢，也不会进发给别人的包。
OVERRIDES_PATH = USERDATA_DIR / "shell-overrides.json"
# 远程图片（角色头像/立绘、光锥与遗器图标）按需下载后缓存在这里，包里就不用塞图片
ASSET_CACHE_DIR = USERDATA_DIR / ".asset-cache"

DEFAULTS: dict[str, Any] = {
    "version": 1,
    "host": "127.0.0.1",
    "port": 8765,
    "autoPort": True,
    "shell": "edge",  # edge=桌面窗口 | browser=默认浏览器 | none=不打开
    "window": {"width": 1360, "height": 900},
    # 桌面窗口模式下，前端每 2 秒发一次心跳；超过这个秒数没心跳就认为窗口关了，服务自动退出。
    "watchdogSeconds": 25,
    # 「后门」开关：只有本机调试/作者自己用的功能模块（manifest 里标了 adminOnly）才会显示。
    # **默认关闭**是有意的：发给别人的包里就算忘了改配置，也不会把作者工具暴露出去。
    "admin": False,
}


def load() -> dict[str, Any]:
    """读配置，缺项用默认值补齐。坏掉的 config.json 不会让程序起不来。"""
    cfg: dict[str, Any] = json.loads(json.dumps(DEFAULTS))
    # exe 旁边没有 config.json 时，读包内的默认配置（只读）。
    config_file = CONFIG_PATH
    if not config_file.is_file():
        for candidate in (BUNDLE_ROOT / "config.json", BUNDLE_ROOT / "gt-exe-config.json"):
            if candidate.is_file():
                config_file = candidate
                break
    if config_file.is_file():
        try:
            user = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            user = {}
        if isinstance(user, dict):
            for key, value in user.items():
                if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                    cfg[key].update(value)
                else:
                    cfg[key] = value
    return cfg


def save(cfg: dict[str, Any]) -> Path:
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return CONFIG_PATH


def is_admin() -> bool:
    """是否开启「作者/调试」模块（默认关）。

    优先级：环境变量 GT_ADMIN（1/true/yes 开，0/false/no 关）> config.json 的 admin 键。
    环境变量优先是为了方便临时开一次跑测试，不用改配置文件。
    """
    env = os.environ.get("GT_ADMIN", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    return bool(load().get("admin"))


def ensure_dirs() -> None:
    for directory in (USERDATA_DIR, DOCS_DIR, MODULES_DIR, APP_DIR, ASSET_CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def load_overrides() -> dict[str, Any]:
    """读外壳覆盖（功能改名/隐藏/排序）。文件坏了就当没有，不影响启动。"""
    if not OVERRIDES_PATH.is_file():
        return {}
    try:
        data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_overrides(data: dict[str, Any]) -> Path:
    OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return OVERRIDES_PATH


def port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def pick_port(host: str, port: int, auto: bool = True, tries: int = 20) -> int:
    """端口被占用就往后找；关掉 autoPort 就直接报错，不偷偷换。"""
    if port_available(host, port):
        return port
    if not auto:
        raise SystemExit(f"端口 {port} 已被占用。请改 config.json 里的 port，或打开 autoPort。")
    for candidate in range(port + 1, port + 1 + tries):
        if port_available(host, candidate):
            print(f"[工具箱] 端口 {port} 被占用，改用 {candidate}。")
            return candidate
    raise SystemExit(f"从 {port} 开始连续 {tries} 个端口都被占用了。")
