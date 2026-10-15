"""零依赖 HTTP 服务：静态资源 + 功能 API + 心跳看门狗。

只用 Python 标准库，装都不用装。同一份服务同时服务两种用法：

* 桌面窗口：由启动器用 Edge 的 app 模式打开 `http://127.0.0.1:<port>/`；
* 网页版：浏览器直接访问同一个地址。

看门狗：桌面窗口模式下前端每 2 秒发一次心跳，超过阈值没心跳（即窗口被关掉）就自动退出进程。
"""

from __future__ import annotations

import hashlib
import json
import math
import mimetypes
import threading
import time
import traceback
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from . import __toolbox_name__, __version__, config, feature_api, registry

# 只允许把这些类型的文件放到浏览器能拿到的位置，避免 api.py 之类的源码被直接下载。
ALLOWED_SUFFIXES = {
    ".html", ".js", ".mjs", ".css", ".json", ".svg", ".png", ".jpg", ".jpeg",
    ".webp", ".gif", ".ico", ".woff2", ".woff", ".ttf", ".md", ".txt", ".map",
}

# 图片按需缓存：只允许从这些域名取图，取回来存在 userdata/.asset-cache 里，
# 同一个 URL 只下载一次 —— 包里就不用塞几十 MB 的图了。
ASSET_HOSTS = {
    "act-upload.mihoyo.com",
    "uploadstatic.mihoyo.com",
    "api-static.mihoyo.com",
    "act.mihoyo.com",
    "webstatic.mihoyo.com",
    "raw.githubusercontent.com",
}
ASSET_MAX_BYTES = 8 * 1024 * 1024
ASSET_TIMEOUT = 25
MAX_BODY_BYTES = 2 * 1024 * 1024

# 显式登记 MIME：mimetypes.guess_type 在 Windows 上读注册表，部分机器查不到 .webp，
# 本地化素材会被发成 application/octet-stream。
_EXPLICIT_MIME = {
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".mjs": "text/javascript",
    ".js": "text/javascript",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".json": "application/json",
    ".map": "application/json",
}
for _suffix, _mime in _EXPLICIT_MIME.items():
    mimetypes.add_type(_mime, _suffix)

LOCAL_ONLY_PATHS = ("/api/call", "/api/reload", "/api/shutdown")
IMAGE_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/avif",
    "image/bmp", "image/x-icon", "image/vnd.microsoft.icon",
}
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"


def _check_asset_url(url: str) -> None:
    """只认白名单域名 + 默认端口（80/443）。白名单域名配上任意端口也是在探测内网服务。"""
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        raise PermissionError("图片地址的端口不合法") from None
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ASSET_HOSTS:
        raise PermissionError("这个域名不在允许列表里")
    if port not in (None, 80, 443):
        raise PermissionError("图片地址只允许默认端口")


def _finite(obj: Any) -> Any:
    """把 inf / nan 换成 null：裸 Infinity/NaN 不是合法 JSON，浏览器 JSON.parse 会直接失败。"""
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {key: _finite(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(value) for value in obj]
    return obj


class _Server(ThreadingHTTPServer):
    # 默认 backlog 只有 5：页面一次并发十几个请求（图片 + 接口）时会被重置连接
    request_queue_size = 64
    daemon_threads = True


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """只允许跳回同一个域名。白名单主机上的开放跳转不能把请求带到内网。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: A003
        new = urlparse(newurl)
        old = urlparse(req.full_url)
        if new.scheme not in ("http", "https") or new.hostname != old.hostname:
            raise PermissionError("图片地址跳到了别的域名，已拒绝")
        _check_asset_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ToolboxState:
    """进程内共享状态：注册表、错误、心跳时间。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.modules: list[registry.Module] = []
        self.errors: list[dict[str, Any]] = []
        self.module_dirs: dict[str, Path] = {}
        self.started_at = time.time()
        self.last_beat = time.time()
        self.watchdog_seconds: float | None = None
        self.verbose = False
        self.last_scan: dict[str, Any] = {}

    def rescan(self) -> dict[str, Any]:
        """重新扫描 modules/ 并重新导入所有 api.py —— 加功能不用重启。"""
        modules, errors = registry.scan()
        loaded = 0
        failed = 0
        for module in modules:
            assert module.dir is not None
            self.module_dirs[module.id] = module.dir
            self.module_dirs[module.folder] = module.dir
            for feature in module.features:
                if not feature.dir:
                    continue
                api_path = feature.dir / feature.api_file
                if api_path.is_file():
                    if feature_api.load_feature_api(
                        module.id, feature.id, api_path, module.dir, feature.dir, errors
                    ):
                        loaded += 1
                    else:
                        failed += 1
        with self.lock:
            self.modules = modules
            self.errors = errors
        self.last_scan = {
            "modules": len(modules),
            "features": sum(len(m.features) for m in modules),
            "apisLoaded": loaded,
            "apisFailed": failed,
            "at": time.time(),
        }
        return self.last_scan

    def registry_payload(self) -> dict[str, Any]:
        with self.lock:
            modules = list(self.modules)
            errors = list(self.errors)
        out_modules: list[dict[str, Any]] = []
        for module in modules:
            payload = module.to_dict()
            for feature_payload, feature in zip(payload["features"], module.features):
                feature_payload["actions"] = feature_api.actions(
                    feature.module_id, feature.id
                )
            out_modules.append(payload)
        return {
            "toolbox": {"name": __toolbox_name__, "version": __version__},
            "modules": out_modules,
            "errors": errors,
            "scan": self.last_scan,
        }


def fetch_asset(url: str) -> tuple[bytes, str]:
    """按需下载远程图片并缓存，返回 (数据, Content-Type)。同一个 URL 只下一次。"""
    _check_asset_url(url)

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    body_path = config.ASSET_CACHE_DIR / digest
    meta_path = config.ASSET_CACHE_DIR / f"{digest}.meta"

    if body_path.is_file() and meta_path.is_file():
        ctype = meta_path.read_text(encoding="utf-8").strip() or "application/octet-stream"
        return body_path.read_bytes(), ctype

    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Referer": "https://wiki.miyoushe.com/"}
    )
    opener = urllib.request.build_opener(_SameHostRedirect)
    with opener.open(request, timeout=ASSET_TIMEOUT) as response:
        ctype = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype not in IMAGE_TYPES:
            raise ValueError(f"不是图片（{ctype or '没有类型'}），拒绝缓存")
        data = response.read(ASSET_MAX_BYTES + 1)
    if len(data) > ASSET_MAX_BYTES:
        raise ValueError("图片超过 8MB，拒绝缓存")
    config.ASSET_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(data)
    meta_path.write_text(ctype, encoding="utf-8")
    return data, ctype


def make_handler(state: ToolboxState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = f"GameToolbox/{__version__}"
        protocol_version = "HTTP/1.1"

        # ---------------- 输出小工具 ----------------

        def _send(self, status: int, body: bytes, ctype: str, cache_seconds: int = 0) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            if cache_seconds > 0:
                # 远程图片这类不会变的内容，让浏览器缓存一天
                self.send_header("Cache-Control", f"public, max-age={cache_seconds}")
            else:
                # 其它一律不吃缓存：改了 ui.js 刷新页面就能看到，方便迭代。
                self.send_header("Cache-Control", "no-store, max-age=0")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj: Any, status: int = 200) -> None:
            self._send(
                status,
                json.dumps(_finite(obj), ensure_ascii=False, allow_nan=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _text(self, text: str, status: int = 200) -> None:
            self._send(status, text.encode("utf-8"), "text/plain; charset=utf-8")

        def _content_length(self) -> int:
            """Content-Length 不合法（非数字/负数）时关掉连接：没读走的字节会被当成下一个请求。"""
            raw = self.headers.get("Content-Length")
            if raw is None or raw.strip() == "":
                return 0
            try:
                length = int(raw)
            except ValueError:
                length = -1
            if length < 0:
                self.close_connection = True
                raise ValueError("Content-Length 不合法")
            return length

        def _read_json_body(self) -> dict[str, Any]:
            length = self._content_length()
            if length <= 0:
                return {}
            if length > MAX_BODY_BYTES:
                self.close_connection = True  # 不读走 2MB+ 的请求体，连接也就不能再复用
                raise ValueError("请求体超过 2MB")
            raw = self.rfile.read(length)
            if not raw:
                return {}
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                raise ValueError(f"请求体不是合法 JSON：{exc}") from exc
            if not isinstance(data, dict):
                raise ValueError("请求体必须是 JSON 对象")
            return data

        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            if state.verbose:
                print(f"[{self.log_date_time_string()}] {fmt % args}")

        # ---------------- 静态资源 ----------------

        def _serve_static(self, url_path: str) -> None:
            rel = unquote(url_path)
            if rel in ("", "/"):
                base, sub = config.APP_DIR, "index.html"
            elif rel.startswith("/app/"):
                base, sub = config.APP_DIR, rel[len("/app/") :]
            elif rel.startswith("/modules/"):
                base, sub = config.MODULES_DIR, rel[len("/modules/") :]
            elif rel.startswith("/docs/"):
                base, sub = config.DOCS_DIR, rel[len("/docs/") :]
            elif rel == "/favicon.ico":
                self._text("", 204)
                return
            else:
                self._text("404 Not Found", 404)
                return

            try:
                target = (base / sub).resolve()
                target.relative_to(base.resolve())
            except (ValueError, OSError):
                self._text("403 Forbidden", 403)
                return

            if not target.is_file() or target.suffix.lower() not in ALLOWED_SUFFIXES:
                self._text("404 Not Found", 404)
                return

            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in (
                "application/javascript",
                "application/json",
            ):
                ctype += "; charset=utf-8"
            self._send(200, target.read_bytes(), ctype)

        # ---------------- GET ----------------

        def _drain_body(self) -> None:
            """GET/HEAD 带了请求体：小的读掉丢弃，大的/不合法的直接关连接，防止错位。"""
            try:
                length = self._content_length()
            except ValueError:
                return
            if 0 < length <= MAX_BODY_BYTES:
                self.rfile.read(length)
            elif length > MAX_BODY_BYTES:
                self.close_connection = True

        def _internal_error(self, exc: BaseException) -> None:
            # 详细信息只打到控制台；回给前端的不带异常原文和绝对路径
            traceback.print_exc()
            self._json({"ok": False, "error": f"内部错误（{type(exc).__name__}），详情见控制台"}, 500)

        def do_HEAD(self) -> None:  # noqa: N802
            # 与 GET 同一条路径，_send 在 HEAD 时只发头（aha-speed 用 HEAD 探测本地 Tailwind）
            self.do_GET()

        def do_GET(self) -> None:  # noqa: N802
            self._drain_body()
            path = urlparse(self.path).path
            try:
                if path.startswith("/api/"):
                    self._api_get(path)
                else:
                    self._serve_static(path)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            except Exception as exc:
                self._internal_error(exc)

        def _api_get(self, path: str) -> None:
            if path == "/api/asset":
                query = urllib.parse.parse_qs(urlparse(self.path).query)
                target_url = (query.get("url") or [""])[0]
                if not target_url:
                    self._json({"ok": False, "error": "缺少 url 参数"}, 400)
                    return
                try:
                    data, ctype = fetch_asset(target_url)
                except PermissionError as exc:
                    self._json({"ok": False, "error": str(exc)}, 403)
                    return
                except Exception as exc:
                    traceback.print_exc()
                    self._json({"ok": False, "error": f"取图失败（{type(exc).__name__}）"}, 502)
                    return
                self._send(200, data, ctype, cache_seconds=86400)
                return

            if path == "/api/health":
                self._json(
                    {
                        "ok": True,
                        "name": __toolbox_name__,
                        "version": __version__,
                    "admin": config.is_admin(),
                        "uptimeSeconds": round(time.time() - state.started_at, 1),
                        "watchdogSeconds": state.watchdog_seconds,
                    }
                )
                return

            if path == "/api/registry":
                self._json({"ok": True, **state.registry_payload()})
                return

            if path == "/api/overrides":
                # 外壳级覆盖（功能改名/隐藏/排序 + 界面文字替换）。
                # 单独一个接口是有意的：发给别人的包里没有「界面」模块，
                # 但外壳照样要能读到（读不到就是空对象，一切走默认）。
                self._json({"ok": True, "overrides": config.load_overrides()})
                return

            if path == "/api/heartbeat":
                state.last_beat = time.time()
                self._json({"ok": True, "at": state.last_beat})
                return

            if path.startswith("/api/docs/"):
                name = unquote(path[len("/api/docs/") :]).strip("/")
                if not name:
                    self._json({"ok": False, "error": "缺少文档名"}, 400)
                    return
                if not name.endswith((".md", ".txt")):
                    name += ".md"
                try:
                    if "\x00" in name:
                        raise ValueError
                    target = (config.DOCS_DIR / name).resolve()
                    target.relative_to(config.DOCS_DIR.resolve())
                    is_file = target.is_file()
                except (ValueError, OSError):
                    self._json({"ok": False, "error": "非法路径"}, 403)
                    return
                if not is_file:
                    self._json({"ok": False, "error": f"没有这篇文档：{name}"}, 404)
                    return
                self._json(
                    {"ok": True, "name": name, "text": target.read_text(encoding="utf-8-sig")}
                )
                return

            if path.startswith("/api/data/"):
                parts = [p for p in path[len("/api/data/") :].split("/") if p]
                if len(parts) < 2:
                    self._json({"ok": False, "error": "用法：/api/data/<模块id>/<数据名>"}, 400)
                    return
                module_id, name = parts[0], parts[1]
                module_dir = state.module_dirs.get(module_id)
                if module_dir is None:
                    self._json({"ok": False, "error": f"没有这个模块：{module_id}"}, 404)
                    return
                ctx = feature_api.FeatureContext(module_id, "_module", module_dir, module_dir)
                self._json({"ok": True, "name": name, "data": ctx.data(name)})
                return

            self._json({"ok": False, "error": f"未知接口：{path}"}, 404)

        # ---------------- POST ----------------

        def _is_local_client(self) -> bool:
            """/api/call、/api/reload、/api/shutdown 只给本机（回环地址）用。
            用 --host 0.0.0.0 绑到局域网时，这几个接口不能变成谁都能调的后门。"""
            host = (self.client_address or ("",))[0]
            return host in ("127.0.0.1", "::1", "localhost", "")

        def _cross_site(self) -> bool:
            """别的网站在浏览器里偷偷 POST 过来（CSRF）：浏览器一定会带 Origin / Sec-Fetch-Site。
            Origin 与 Host 不一致、或 Sec-Fetch-Site=cross-site 就拒绝。没有 Origin 的（curl、
            同源旧浏览器）照常放行 —— 回环限制仍然生效。"""
            if (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":
                return True
            origin = self.headers.get("Origin")
            if origin is None:
                return False
            parsed = urlparse(origin)
            host = (self.headers.get("Host") or "").lower()
            return parsed.scheme not in ("http", "https") or parsed.netloc.lower() != host

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if self._cross_site():
                self.close_connection = True
                self._json({"ok": False, "error": "拒绝跨站请求"}, 403)
                return
            if path in LOCAL_ONLY_PATHS and not self._is_local_client():
                self.close_connection = True
                self._json({"ok": False, "error": "仅允许本机调用"}, 403)
                return
            try:
                body = self._read_json_body()
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return

            try:
                if path == "/api/call":
                    self._api_call(body)
                elif path == "/api/heartbeat":
                    state.last_beat = time.time()
                    self._json({"ok": True, "at": state.last_beat})
                elif path == "/api/reload":
                    info = state.rescan()
                    self._json({"ok": True, "scan": info})
                elif path == "/api/shutdown":
                    self._json({"ok": True, "message": "正在退出"})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    self._json({"ok": False, "error": f"未知接口：{path}"}, 404)
            except Exception as exc:
                self._internal_error(exc)

        def _api_call(self, body: dict[str, Any]) -> None:
            module_id = str(body.get("module") or "")
            feature_id = str(body.get("feature") or "")
            action = str(body.get("action") or "")
            payload = body.get("payload") or {}
            if not (module_id and feature_id and action):
                self._json(
                    {"ok": False, "error": "需要 module / feature / action 三个字段"}, 400
                )
                return
            if not isinstance(payload, dict):
                self._json({"ok": False, "error": "payload 必须是对象"}, 400)
                return
            try:
                result = feature_api.call(module_id, feature_id, action, payload)
            except KeyError as exc:
                self._json({"ok": False, "error": str(exc)}, 404)
                return
            except ValueError as exc:
                # 参数问题：这是用户能自己改的，直接回显
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            self._json({"ok": True, "result": result})

    return Handler


def _watchdog(state: ToolboxState, httpd: ThreadingHTTPServer, stop: threading.Event) -> None:
    while not stop.wait(2.0):
        window = state.watchdog_seconds
        if not window:
            continue
        if time.time() - state.last_beat > window:
            print("[工具箱] 窗口已关闭（心跳超时），退出。")
            httpd.shutdown()
            return


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    watchdog_seconds: float | None = None,
    verbose: bool = False,
    on_ready=None,
) -> int:
    """启动服务。`on_ready(url)` 在端口就绪后、进入事件循环前调用（用来开窗口）。"""
    config.ensure_dirs()
    state = ToolboxState()
    state.watchdog_seconds = watchdog_seconds
    state.verbose = verbose
    info = state.rescan()

    httpd = _Server((host, port), make_handler(state))
    url = f"http://{host}:{port}/"

    def say(message: str) -> None:
        # flush=True：即使输出被重定向到文件/管道，也能立刻看到启动信息
        print(message, flush=True)

    say(f"[工具箱] {__toolbox_name__} v{__version__}")
    say(
        f"[工具箱] 已加载 {info['modules']} 个模块 / {info['features']} 个功能"
        f"（后端动作 {info['apisLoaded']} 个，失败 {info['apisFailed']} 个）"
    )
    if state.errors:
        say(f"[工具箱] 有 {len(state.errors)} 条警告，界面左下角「模块状态」里能看。")
    say(f"[工具箱] 地址：{url}")

    if on_ready is not None:
        on_ready(url)

    stop = threading.Event()
    if watchdog_seconds:
        threading.Thread(
            target=_watchdog, args=(state, httpd, stop), daemon=True
        ).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[工具箱] 收到 Ctrl+C，退出。")
    finally:
        stop.set()
        httpd.server_close()
    return 0
