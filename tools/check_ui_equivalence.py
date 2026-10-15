"""新旧配速界面的 plan 请求等价性检查（0.17.0 换界面时用）。

用同一套「选择」分别操作旧界面和新界面，截获最后一次 /api/call plan 的请求体和返回，
断言两边完全一致（只排除新界面才有的字段：customCharacter）。

用法：
    python tools/check_ui_equivalence.py --old http://127.0.0.1:9412 --new http://127.0.0.1:9411
旧界面：用 git worktree 检出 0.17.0 换界面前的提交（ece66af）跑一个服务即可：
    git worktree add ../legacy_wt ece66af
    cd ../legacy_wt && GT_USERDATA=$(mktemp -d) python run.py --web --no-open --port 9412
需要 playwright（pip install playwright）和一个 Chrome/Chromium。
"""

from __future__ import annotations

import argparse
import json
import sys

from playwright.sync_api import sync_playwright

ROUTE = "#/honkai-star-rail/speed-plan"
NEW_ONLY_FIELDS = {"customCharacter"}

# 每个场景是一串抽象操作；两个界面各自的驱动把它翻译成点击/输入
SCENARIOS: list[tuple[str, list[tuple]]] = [
    ("默认（第一个角色）", []),
    ("瓦尔特 2 魂 · 异相仲裁（含作用于敌方的效果）", [("char", "瓦尔特"), ("eid", 2), ("mode", "yixiang")]),
    ("银狼 · 不装光锥 · 无速度鞋 · 副词条 12", [("char", "银狼"), ("cone", ""), ("boots", False), ("substat", 12)]),
    (
        "花火 · 风套开大 2 次 · 光锥开大 1 · 轴底开大 · 3 动",
        [("char", "花火"), ("four", "晨昏交界的翔鹰"), ("fourUlts", 2), ("coneUlts", 1), ("exLast", True), ("actions", 3)],
    ),
    (
        "卡芙卡 · 信使打队友 · 翁瓦克 · 进战即开大",
        [("char", "卡芙卡"), ("four", "骇域漫游的信使"), ("ally", True), ("orn", "生命的翁瓦克"), ("fua", 0)],
    ),
    (
        "知更鸟 · 叠影 5 · 其它 6%/4 · 拉条 15 · 混沌 2T",
        [("char", "知更鸟"), ("si", 5), ("pct", 6), ("flat", 4), ("adv", 15), ("mode", "moc"), ("t", 2)],
    ),
    ("镜流 · 劫火 · 自定义行动值 250 · 第 3 动开大", [("char", "镜流"), ("orn", "劫火莲灯铸炼宫"), ("av", 250), ("fua", 3)]),
    ("景元 · 快捷 300 AV · 关掉第一条效果", [("char", "景元"), ("avbtn", 300), ("toggle", 0)]),
    ("黄泉 6 魂 叠影 3 · 末日幻影 4 动", [("char", "黄泉"), ("eid", 6), ("si", 3), ("mode", "mori"), ("actions", 4)]),
    (
        "阮•梅 · 伶人 + 翁法罗斯 · 副词条 20 · 虚构 1T · 效果开关两次",
        [
            ("char", "阮•梅"),
            ("four", "戏梦点星的伶人"),
            ("orn", "永恒之地翁法罗斯"),
            ("substat", 20),
            ("mode", "xugou"),
            ("t", 1),
            ("toggle", 0),
            ("toggle", 0),
        ],
    ),
]


class Driver:
    def __init__(self, page, legacy: bool):
        self.page = page
        self.legacy = legacy
        self.plans: list[tuple[dict, dict]] = []
        self.inflight = 0
        page.on("request", self._on_request)
        page.on("requestfinished", self._on_done)
        page.on("requestfailed", self._on_done)
        page.on("response", self._on_response)

    def _on_request(self, request):
        if request.url.endswith("/api/call"):
            self.inflight += 1

    def _on_done(self, request):
        if request.url.endswith("/api/call"):
            self.inflight -= 1

    def _on_response(self, response):
        if not response.url.endswith("/api/call"):
            return
        try:
            body = json.loads(response.request.post_data or "{}")
        except ValueError:
            return
        if body.get("action") != "plan":
            return
        try:
            data = response.json()
        except Exception:  # noqa: BLE001
            data = {"_unreadable": True}
        self.plans.append((body.get("payload"), data))

    def settle(self):
        # 等防抖（旧 150ms / 新 200ms）触发，再等所有 /api/call 回来；心跳不算
        self.page.wait_for_timeout(450)
        for _ in range(200):
            if self.inflight <= 0:
                break
            self.page.wait_for_timeout(50)
        self.page.wait_for_timeout(150)

    def pick_from_picker(self, button: str, name: str):
        self.page.click(button)
        popup = self.page.locator(".picker-popup:not(.hidden)")
        if name:
            popup.locator(".picker-search").fill(name)
        label = name or None
        items = popup.locator(".picker-item")
        for i in range(items.count()):
            text = items.nth(i).locator(".pi-name").inner_text().strip()
            if (label and text == label) or (not label and text.startswith("（")):
                items.nth(i).click()
                return
        raise AssertionError(f"下拉里找不到 {name!r}")

    def fill(self, selector: str, value):
        self.page.fill(selector, str(value))

    def check(self, selector: str, value: bool):
        if self.page.is_checked(selector) != value:
            self.page.click(selector)

    def do(self, op: tuple):
        kind, value = op[0], op[1]
        p = self.page
        if kind == "char":
            if self.legacy:
                self.pick_from_picker("#character-picker", value)
            else:
                p.fill("#char-search", value)
                tiles = p.locator("#char-grid [data-char]")
                for i in range(tiles.count()):
                    if tiles.nth(i).locator(".sp-char-name").inner_text().strip() == value:
                        tiles.nth(i).click()
                        break
                else:
                    raise AssertionError(f"网格里找不到 {value}")
                p.fill("#char-search", "")
        elif kind == "cone":
            self.pick_from_picker("#lightcone-picker", value)
        elif kind == "four":
            self.pick_from_picker("#fourPiece-picker", value)
        elif kind == "orn":
            self.pick_from_picker("#ornamentA-picker", value)
        elif kind == "si":
            p.select_option("#superimpose", str(value))
        elif kind == "eid":
            p.select_option("#eidolon", str(value))
        elif kind == "boots":
            self.check("#speedBoots", value)
        elif kind == "ally":
            self.check("#ultTargetsAlly", value)
        elif kind == "exLast":
            self.check("#excludeLastUlt", value)
        elif kind in ("substat", "pct", "flat", "fourUlts", "coneUlts", "adv", "actions", "av"):
            selector = {
                "substat": "#substat",
                "pct": "#customPct",
                "flat": "#customFlat",
                "fourUlts": "#fourUlts",
                "coneUlts": "#coneUlts",
                "adv": "#advCustom",
                "actions": "#targetActions",
                "av": "#customAV",
            }[kind]
            self.fill(selector, value)
        elif kind == "fua":
            self.fill("#firstUltAction-panel" if self.legacy else "#firstUltAction", value)
        elif kind == "mode":
            p.select_option("#mode", value)
        elif kind == "t":
            options = p.locator("#targetT option")
            p.select_option("#targetT", options.nth(value).get_attribute("value"))
        elif kind == "avbtn":
            p.click(f'[data-av="{value}"]')
        elif kind == "toggle":
            # 按「最近一次结果里第 n 条速度效果」的 id 点，两边排版不同但 id 一样
            effects = self.plans[-1][1].get("result", self.plans[-1][1])["effects"]["speed"]
            if not effects:
                return
            eid = effects[value]["id"]
            p.click(f'[data-effect="{eid}"]')
        else:
            raise ValueError(kind)
        self.settle()


def run_ui(browser, base: str, legacy: bool, ops: list[tuple]):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    driver = Driver(page, legacy)
    page.goto(base + "/" + ROUTE)
    page.wait_for_selector("#mode option", state="attached", timeout=15000)
    driver.settle()
    for op in ops:
        driver.do(op)
    driver.settle()
    page.close()
    if errors:
        raise AssertionError(f"页面报错：{errors}")
    if not driver.plans:
        raise AssertionError("没有截获到 plan 请求")
    payload, result = driver.plans[-1]
    payload = {k: v for k, v in (payload or {}).items() if k not in NEW_ONLY_FIELDS}
    return payload, result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", default="http://127.0.0.1:9412")
    parser.add_argument("--new", default="http://127.0.0.1:9411")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    args = parser.parse_args()
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chrome, args=["--no-sandbox"])
        for name, ops in SCENARIOS:
            old_payload, old_result = run_ui(browser, args.old, True, ops)
            new_payload, new_result = run_ui(browser, args.new, False, ops)
            same_payload = old_payload == new_payload
            same_result = old_result == new_result
            ok = same_payload and same_result
            failures += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
            if not same_payload:
                print("   旧 payload:", json.dumps(old_payload, ensure_ascii=False, sort_keys=True))
                print("   新 payload:", json.dumps(new_payload, ensure_ascii=False, sort_keys=True))
            elif not same_result:
                print("   payload 一致但结果不同")
        browser.close()
    print(f"\n{len(SCENARIOS) - failures}/{len(SCENARIOS)} 个场景一致")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
