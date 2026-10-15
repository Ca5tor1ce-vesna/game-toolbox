"""把「配速查询」单文件网页挂到局域网上，让手机也能打开。

    python tools/serve_web.py                # 默认 0.0.0.0:8770
    python tools/serve_web.py --port 9000
    python tools/serve_web.py --rebuild      # 先重新生成网页版再挂

为什么单独一个服务，而不是直接用工具箱的服务：
  * 工具箱的服务只监听 127.0.0.1（本机），是**故意**的——它会暴露源码接口；
  * 这个服务只对外提供一个**已经打包好的静态 HTML 文件**，没有接口、没有源码，
    给手机用足够了，暴露面最小。
  * 手机要能访问，必须监听 0.0.0.0（局域网），所以这里把"只提供这一个文件"写死。

安全提醒：同一个 Wi-Fi 下的其他人只要知道地址也能打开。用完 Ctrl+C 关掉即可。
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_PORT = 8770
PAGE_NAME = "配速查询-网页版.html"


def ensure_page(rebuild: bool) -> Path:
    """确保单文件网页版存在（没有就生成一份）。"""
    page = ROOT / "dist" / PAGE_NAME
    if rebuild or not page.is_file():
        sys.path.insert(0, str(ROOT / "tools"))
        import make_web_standalone  # type: ignore

        page = make_web_standalone.build()
    return page


def lan_addresses() -> list[str]:
    """列出本机所有可能的局域网地址（手机要用这些地址里的某一个）。"""
    found: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = info[4][0]
            if address not in found and not address.startswith("127."):
                found.append(address)
    except OSError:
        pass
    # getaddrinfo 有时给不全，补一条「连外网时会用的本机地址」的探测法
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.settimeout(0.5)
        probe.connect(("8.8.8.8", 80))
        address = probe.getsockname()[0]
        probe.close()
        if address not in found and not address.startswith("127."):
            found.insert(0, address)
    except OSError:
        pass
    return found


class Handler(BaseHTTPRequestHandler):
    server_version = "GameToolboxPhone/1.0"
    page: Path = Path()
    hits: list[str] = []

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # 手机刷新要拿到最新的，所以不缓存
        self.send_header("Cache-Control", "no-store, must-revalidate")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (标准库命名)
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html", f"/{PAGE_NAME}"):
            try:
                body = self.page.read_bytes()
            except OSError as exc:
                self._send(500, f"读不到网页文件：{exc}".encode(), "text/plain; charset=utf-8")
                return
            client = self.client_address[0]
            stamp = time.strftime("%H:%M:%S")
            self.hits.append(client)
            print(f"  [{stamp}] {client} 打开了网页（第 {len(self.hits)} 次）")
            self._send(200, body, "text/html; charset=utf-8")
            return
        if path == "/health":
            self._send(200, b"ok", "text/plain; charset=utf-8")
            return
        # 只提供这一个页面，其它一律 404（不做静态文件服务器）
        self._send(404, "这里只有配速查询网页版，没有别的路径。".encode(), "text/plain; charset=utf-8")

    def do_HEAD(self) -> None:  # noqa: N802
        self._send(200, b"", "text/html; charset=utf-8")

    def log_message(self, *args) -> None:  # 静音默认日志，自己打更好看的
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="把配速查询网页版挂到局域网，供手机访问")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="0.0.0.0", help="默认 0.0.0.0（局域网可见）")
    parser.add_argument("--rebuild", action="store_true", help="先重新生成网页版再挂")
    args = parser.parse_args()

    page = ensure_page(args.rebuild)
    Handler.page = page

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        print(f"端口 {args.port} 起不来：{exc}")
        print("换个端口试试：python tools\\serve_web.py --port 9000")
        return 1

    addresses = lan_addresses()
    print()
    print("=" * 58)
    print("  配速查询 · 手机访问已开启")
    print("=" * 58)
    print(f"  文件：{page.name}（{page.stat().st_size / 1024:.0f} KB，单文件）")
    print()
    print("  手机连同一个 Wi-Fi，然后用浏览器打开：")
    if addresses:
        for address in addresses:
            print(f"      http://{address}:{args.port}")
    else:
        print(f"      http://<这台电脑的局域网IP>:{args.port}")
        print("      （没探测到局域网地址，请在「设置 → 网络」里看本机 IP）")
    print()
    print("  打不开的话按顺序检查：")
    print("    1. 手机和电脑是不是同一个 Wi-Fi（别一个 5G 一个访客网络）")
    print("    2. Windows 防火墙弹窗要点「允许访问」（专用网络）")
    print("       或用管理员命令行执行一次：")
    print(f"       netsh advfirewall firewall add rule name=\"配速查询手机版\" dir=in action=allow protocol=TCP localport={args.port}")
    print("    3. 电脑不能休眠/睡眠")
    print()
    print("  用完在这里按 Ctrl+C 关闭。")
    print("=" * 58)
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("已关闭。手机再打开会连不上，这是正常的。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
