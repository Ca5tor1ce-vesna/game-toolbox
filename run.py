#!/usr/bin/env python


"""游戏实用工具箱 —— 统一入口。

用法
----
    python run.py                       启动（桌面窗口，关窗自动退出）
    python run.py --web                 启动并打开默认浏览器（服务一直开着，Ctrl+C 退出）
    python run.py --no-open             只起服务，不打开任何界面
    python run.py --port 9000           换端口
    python run.py --verbose             打印每个请求
    python run.py list                  列出所有模块与功能
    python run.py new-module <目录名> <显示名> [--icon 🌏]
    python run.py new-feature <模块> <功能目录名> <显示名> [--icon ⚔️]
"""

from __future__ import annotations

import os
import sys

# 打包成 exe 且用 --noconsole 时 sys.stdout/stderr 是 None，
# 任何 print() 都会抛 AttributeError 让程序直接起不来（踩过）。这里兜一下。
if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
    _null = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = _null
    if sys.stderr is None:
        sys.stderr = _null


import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config, launcher, registry, scaffold, server  # noqa: E402


def _setup_console() -> None:
    """中文 Windows 控制台默认是 GBK，打印 emoji 会直接抛 UnicodeEncodeError。

    这里只把错误策略改成 replace（打不出来的字符变成 ?），不会因为一个图标让命令崩掉。
    想要完整显示（含 emoji），用 start.bat 启动——它会先切到 UTF-8 代码页。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


def cmd_run(args: argparse.Namespace) -> int:
    cfg = config.load()
    config.ensure_dirs()

    host = args.host or cfg.get("host", "127.0.0.1")
    port = config.pick_port(
        host,
        int(args.port or cfg.get("port", 8765)),
        auto=bool(cfg.get("autoPort", True)),
    )

    shell = args.shell or cfg.get("shell", "edge")
    watchdog: float | None = None
    if args.web:
        shell = "browser"
        watchdog = None
    elif args.no_open:
        shell = "none"
        watchdog = None
    elif not args.no_watchdog:
        watchdog = float(cfg.get("watchdogSeconds", 25))

    if args.watchdog is not None:
        watchdog = float(args.watchdog)

    window = cfg.get("window") or {}
    size = (int(window.get("width", 1360)), int(window.get("height", 900)))

    def on_ready(url: str) -> None:
        if shell == "none":
            print(f"[工具箱] 在浏览器里打开：{url}")
            return
        opened = launcher.open_window(
            url,
            size=size,
            shell=shell,
            profile_dir=config.USERDATA_DIR / "edge-profile",
        )
        if opened == "edge":
            print("[工具箱] 已打开桌面窗口（关掉窗口程序会自动退出）。")
        elif opened == "browser":
            print("[工具箱] 已在默认浏览器打开；服务会一直开着，Ctrl+C 退出。")

    return server.serve(
        host=host,
        port=port,
        watchdog_seconds=watchdog,
        verbose=args.verbose,
        on_ready=on_ready,
    )


def cmd_list(args: argparse.Namespace) -> int:
    modules, errors = registry.scan()
    if not modules:
        print("还没有任何模块。用 `python run.py new-module <目录名> <显示名>` 建一个。")
    for module in modules:
        print(f"\n{module.icon} {module.name}  [{module.id}] v{module.version}")
        if module.description:
            print(f"   {module.description}")
        if module.data_files():
            print(f"   数据：{', '.join(module.data_files())}")
        for feature in module.features:
            ui = "有界面" if feature.dir and (feature.dir / feature.ui_file).is_file() else "无界面"
            api = "有后端" if feature.dir and (feature.dir / feature.api_file).is_file() else "无后端"
            print(f"   - {feature.icon} {feature.name}  [{feature.id}]  {ui}/{api}")
    if errors:
        print("\n警告：")
        for item in errors:
            print(f" - {item.get('scope')}: {item.get('error')}")
    return 0


def cmd_new_module(args: argparse.Namespace) -> int:
    created = scaffold.new_module(
        args.id, args.name, icon=args.icon, description=args.description or "", force=args.force
    )
    print("已创建模块：")
    for path in created:
        print(f"  {path}")
    print("\n下一步：`python run.py` 启动，界面里会出现这个模块。")
    return 0


def cmd_new_feature(args: argparse.Namespace) -> int:
    created = scaffold.new_feature(
        args.module,
        args.id,
        args.name,
        icon=args.icon,
        description=args.description or "",
        order=args.order,
        force=args.force,
    )
    print("已创建功能：")
    for path in created:
        print(f"  {path}")
    print("\n下一步：重启服务（或在界面点「重新扫描」）即可看到。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py", description="游戏实用工具箱", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="启动工具箱（默认命令）")
    _add_serve_args(run)
    run.set_defaults(func=cmd_run)

    listing = sub.add_parser("list", help="列出所有模块与功能")
    listing.set_defaults(func=cmd_list)

    new_module = sub.add_parser("new-module", help="新建一个游戏模块")
    new_module.add_argument("id", help="目录名，建议用英文小写加连字符，如 genshin")
    new_module.add_argument("name", help="显示名，如 原神")
    new_module.add_argument("--icon", default="🎮")
    new_module.add_argument("--description", default="")
    new_module.add_argument("--force", action="store_true")
    new_module.set_defaults(func=cmd_new_module)

    new_feature = sub.add_parser("new-feature", help="给某个模块加一个功能")
    new_feature.add_argument("module", help="模块目录名，如 honkai-star-rail")
    new_feature.add_argument("id", help="功能目录名，如 damage")
    new_feature.add_argument("name", help="显示名，如 伤害计算")
    new_feature.add_argument("--icon", default="🧩")
    new_feature.add_argument("--description", default="")
    new_feature.add_argument("--order", type=int, default=100)
    new_feature.add_argument("--force", action="store_true")
    new_feature.set_defaults(func=cmd_new_feature)

    return parser


def _add_serve_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--web", action="store_true", help="只开网页（默认浏览器），服务常驻")
    parser.add_argument("--no-open", action="store_true", help="不打开任何界面")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--shell", choices=["edge", "browser", "none"], default=None)
    parser.add_argument("--watchdog", type=float, default=None, help="心跳超时秒数")
    parser.add_argument("--no-watchdog", action="store_true", help="关掉关窗自动退出")
    parser.add_argument("--verbose", action="store_true")


def main(argv: list[str] | None = None) -> int:
    _setup_console()
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    # 没有子命令时，等价于 `run`（还要把 --web 之类的参数接住）
    known = {"run", "list", "new-module", "new-feature"}
    if not argv or (argv[0] not in known and not argv[0] in ("-h", "--help")):
        argv = ["run", *argv]

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
