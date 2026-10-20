"""把「配速查询」打成一个独立单文件网页。

产物：dist/配速查询-网页版.html

为什么能单文件：这个功能的算法已经在 `web_api.js` 里移植成了纯 JS，
数据是 JSON，界面是 ui.js + style.css。全部内联后，双击即可用，
不需要 Python 服务、不需要联网装依赖。

图片：`data/*.json` 里的 `icon` / `splash` 现在是**本地化**过的站内路径
（`/modules/honkai-star-rail/assets/xxx.webp`，见 tools/localize_assets.py）。
单文件 HTML 没有服务端，所以这里把它们读出来做成 data URI 内联进来；
内联后如果整个文件超过 `INLINE_LIMIT`，就放弃内联、退回远程 URL
（数据里每条都留了 `_remote` 兜底），并在输出里说明。

页面打开时会自动跑一遍自检：拿 Python 版算出的标准答案对拍，
结果直接显示在页面上 —— 这样"网页版算得对不对"你自己就能看见。
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "modules" / "honkai-star-rail"
FEATURE = MODULE / "features" / "speed-plan"
DATA = MODULE / "data"
HERTA = ROOT / "modules" / "herta" / "features" / "records"
DIST = ROOT / "dist"

OUT_NAME = "配速查询-网页版.html"

# 内联素材后整个 HTML 的上限。
# 立绘本地化到 320px 后素材约 3.4 MB，base64 后约 4.6 MB → HTML 约 5.1 MB，
# 离这条线还有余量；超过就退回远程 URL（数据里每条都有 `_remote` 兜底）。
INLINE_LIMIT = 7 * 1024 * 1024
ASSET_PREFIX = "/modules/honkai-star-rail/assets/"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def asset_data_uris() -> dict[str, str]:
    """把用到的本地素材读成 {站内路径: data:image/webp;base64,...}。"""
    folder = MODULE / "assets"
    out: dict[str, str] = {}
    if folder.is_dir():
        for path in sorted(folder.glob("*.webp")):
            raw = path.read_bytes()
            out[f"{ASSET_PREFIX}{path.name}"] = (
                "data:image/webp;base64," + base64.b64encode(raw).decode("ascii")
            )
    # 角色顶分（herta）的头像等素材也一并内联
    herta_folder = ROOT / "modules" / "herta" / "assets"
    if herta_folder.is_dir():
        for path in sorted(herta_folder.glob("*.webp")):
            raw = path.read_bytes()
            out[f"/modules/herta/assets/{path.name}"] = (
                "data:image/webp;base64," + base64.b64encode(raw).decode("ascii")
            )
    return out



def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def strip_export(source: str) -> str:
    """ui.js 是 ES module（export default {...}），单文件页面里要当普通脚本用。"""
    if "export default" not in source:
        raise SystemExit("ui.js 结构变了：找不到 export default")
    return source.replace("export default {", "const GT_FEATURE = {", 1)


SHIM_JS = r"""
/* ---------------- 与工具箱一致的 ctx 契约（见 app/app.js 的 makeCtx） ---------------- */
const gtFmt = {
  num(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(value)) return "-";
    const n = Number(value);
    if (!Number.isFinite(n)) return "-";
    return n.toFixed(digits);
  },
  int(value) {
    if (value === null || value === undefined) return "-";
    return String(Math.round(Number(value)));
  },
  pct(value, digits = 2) {
    if (value === null || value === undefined) return "-";
    return (Number(value) * 100).toFixed(digits) + "%";
  },
  money(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "-";
    return Math.round(n).toLocaleString("zh-CN");
  },
};
const gtEscapeHtml = (text) =>
  String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function buildCtx(api) {
  return {
    moduleId: "honkai-star-rail",
    featureId: "speed-plan",
    module: { id: "honkai-star-rail", name: "崩坏：星穹铁道" },
    feature: { id: "speed-plan", name: "配速查询" },
    // 没有网络往返：直接同步算完，包成 Promise 保持和工具箱一样的调用方式
    call: (action, payload) => Promise.resolve(api.call(action, payload)),
    data: async (name) => window.GT_DATA[name],
    fmt: gtFmt,
    ui: { escapeHtml: gtEscapeHtml, fmt: gtFmt },
  };
}
"""

THEME_APPLY_JS = r"""
/* ---------------- 跟随用户保存的外观主题 ----------------
   工具箱里改的配色/字体/字号（userdata/interface/theme.json）在打包时被内联进来，
   单文件网页版没有服务端，所以在这里直接套用。 */
const GT_THEME_COLOR_VARS = {
  bg: "--bg", panel: "--panel", panel2: "--panel-2", border: "--border",
  text: "--text", muted: "--muted", accent: "--accent", accent2: "--accent-2",
  good: "--good", warn: "--warn", bad: "--bad",
};
const GT_THEME_NUMBER_VARS = {
  baseSize: ["fonts", "--base-size", "px"],
  lineHeight: ["fonts", "--line-height", ""],
  radius: ["layout", "--radius", "px"],
  sidebarWidth: ["layout", "--sidebar-w", "px"],
  viewPadding: ["layout", "--view-pad", "px"],
  cardPadding: ["layout", "--card-pad", "px"],
};
function applyStandaloneTheme(theme) {
  const root = document.documentElement;
  const colors = (theme && theme.colors) || {};
  for (const [key, varName] of Object.entries(GT_THEME_COLOR_VARS)) {
    if (colors[key]) root.style.setProperty(varName, colors[key]);
  }
  const fonts = (theme && theme.fonts) || {};
  const layout = (theme && theme.layout) || {};
  if (fonts.sans) root.style.setProperty("--sans", fonts.sans);
  if (fonts.mono) root.style.setProperty("--mono", fonts.mono);
  for (const [key, [group, varName, unit]] of Object.entries(GT_THEME_NUMBER_VARS)) {
    const value = (group === "fonts" ? fonts : layout)[key];
    if (value !== undefined && value !== null && value !== "") {
      root.style.setProperty(varName, value + unit);
    }
  }
  const text = (theme && theme.text) || {};
  if (text.brand) document.title = text.brand;
}
"""

SELFTEST_JS = r"""
/* ---------------- 自检：拿 Python 版的标准答案对拍 ---------------- */
function runSelfTest(api, oracle) {
  const TOLERANCE = 1e-6;
  let checks = 0;
  const failures = [];

  function cmp(path, expected, actual) {
    if (typeof expected === "number") {
      checks += 1;
      if (typeof actual !== "number" || Math.abs(expected - actual) > TOLERANCE) {
        failures.push(`${path}：期望 ${expected}，实际 ${actual}`);
      }
      return;
    }
    if (Array.isArray(expected)) {
      checks += 1;
      if (!Array.isArray(actual) || actual.length !== expected.length) {
        failures.push(`${path}：数组长度不一致`);
        return;
      }
      expected.forEach((item, index) => cmp(`${path}[${index}]`, item, actual[index]));
      return;
    }
    if (expected && typeof expected === "object") {
      if (!actual || typeof actual !== "object") {
        failures.push(`${path}：期望对象`);
        return;
      }
      Object.keys(expected).forEach((key) => cmp(`${path}.${key}`, expected[key], actual[key]));
      return;
    }
    checks += 1;
    if (expected !== actual) {
      failures.push(`${path}：期望 ${JSON.stringify(expected)}，实际 ${JSON.stringify(actual)}`);
    }
  }

  for (const entry of oracle.plans || []) {
    let result;
    try {
      result = api.call("plan", entry.payload);
    } catch (error) {
      failures.push(`plan(${entry.label}) 抛异常：${error.message}`);
      continue;
    }
    cmp(`${entry.label}.speed`, entry.speed, result.speed);
    cmp(`${entry.label}.advance.total`, entry.advance.total, result.advance.total);
    cmp(`${entry.label}.advance.items`, entry.advance.items, result.advance.items.map((i) => i.percent));
    cmp(`${entry.label}.verdict`, entry.verdict, {
      t: result.verdict.t,
      actions: result.verdict.actions,
      totalAV: result.verdict.totalAV,
      requiredSpeed: result.verdict.requiredSpeed,
      currentSpeed: result.verdict.currentSpeed,
      gap: result.verdict.gap,
      achievableActions: result.verdict.achievableActions,
    });
    cmp(`${entry.label}.relicSetCount`, entry.relicSetCount, (result.relicSets || []).length);
    cmp(`${entry.label}.warningCount`, entry.warningCount, (result.warnings || []).length);
    for (const expectedTable of entry.tables || []) {
      const table = (result.tables || []).find((item) => item.id === expectedTable.id);
      if (!table) {
        failures.push(`${entry.label}.tables.${expectedTable.id}：缺少表格`);
        continue;
      }
      cmp(`${entry.label}.${expectedTable.id}.firstCycleAV`, expectedTable.firstCycleAV, table.firstCycleAV);
      cmp(`${entry.label}.${expectedTable.id}.cycleAV`, expectedTable.cycleAV, table.cycleAV);
      cmp(`${entry.label}.${expectedTable.id}.tValues`, expectedTable.tValues, table.tValues);
      expectedTable.cells.forEach((row, rowIndex) => {
        cmp(
          `${entry.label}.${expectedTable.id}.cells[${rowIndex}]`,
          row,
          table.rows[rowIndex].cells.map((cell) => cell.speed),
        );
      });
    }
  }

  for (const entry of oracle.recommends || []) {
    let result;
    try {
      result = api.call("recommend", entry.payload);
    } catch (error) {
      failures.push(`recommend(${entry.label}) 抛异常：${error.message}`);
      continue;
    }
    cmp(`${entry.label}.assumptions`, entry.assumptions, result.assumptions);
    cmp(`${entry.label}.evaluated`, entry.evaluated, result.evaluated);
    (entry.results || []).forEach((expectedItem, index) => {
      const item = (result.results || [])[index];
      if (!item) {
        failures.push(`${entry.label}.results[${index}]：缺推荐`);
        return;
      }
      cmp(`${entry.label}.results[${index}].speed`, expectedItem.speed, item.speed);
      cmp(`${entry.label}.results[${index}].advance`, expectedItem.advance, item.advance);
      cmp(`${entry.label}.results[${index}].needed`, expectedItem.neededSubstatSpeed, item.neededSubstatSpeed);
      cmp(`${entry.label}.results[${index}].coneId`, expectedItem.coneId, item.coneId);
      cmp(`${entry.label}.results[${index}].fourPieceId`, expectedItem.fourPieceId, item.fourPieceId);
      cmp(`${entry.label}.results[${index}].ornamentIds`, expectedItem.ornamentIds, item.ornamentIds);
    });
  }

  return { checks, failures };
}
"""


def build(with_theme: bool = True, out_name: str | None = None) -> Path:
    """生成单文件网页版。

    with_theme=False 用于用户包：不把作者自己的外观主题内联进去。
    out_name 可以指定输出文件名（打包时给作者包/用户包各生成一份临时文件）。
    """
    characters = read_json(DATA / "characters.json")
    lightcones = read_json(DATA / "lightcones.json")
    relic_sets = read_json(DATA / "relic_sets.json")
    modes = read_json(DATA / "modes.json")
    sources = read_json(DATA / "sources.json")
    oracle = read_json(ROOT / "tests" / "fixtures" / "web_oracle.json")

    shell_css = read(ROOT / "app" / "style.css")
    feature_css = read(FEATURE / "style.css")
    web_api = read(FEATURE / "web_api.js")
    ui = strip_export(read(FEATURE / "ui.js"))

    herta_api = read(HERTA / "web_api.js")
    herta_css = read(HERTA / "style.css")
    herta_ui = read(HERTA / "ui.js")
    if "export default {" not in herta_ui:
        raise SystemExit("herta ui.js 结构变了")
    # 包一层函数作用域：两个 ui.js 都有 esc / MODES 之类的顶层名字，放在同一页的经典脚本里会撞名
    herta_ui = (
        "const GT_HERTA_FEATURE = (() => {\n"
        + herta_ui.replace("export default {", "return {", 1)
        + "\n})();"
    )

    AHA = MODULE / "features" / "aha-speed"
    aha_api = read(AHA / "web_api.js")
    aha_css = read(AHA / "style.css")
    aha_ui_raw = read(AHA / "ui.js")
    if "export default {" not in aha_ui_raw:
        raise SystemExit("aha-speed ui.js 结构变了")
    aha_ui = (
        "const GT_AHA_FEATURE = (() => {\n"
        + aha_ui_raw.replace("export default {", "return {", 1)
        + "\n})();"
    )
    # 单文件网页版不会再向服务器取 original.html / vendor，直接把源码内联成全局变量。
    aha_original_js = json.dumps(
        read(AHA / "original.html"), ensure_ascii=False
    ).replace("</", "<\\/")
    aha_vendor_js = json.dumps(
        read(AHA / "vendor" / "tailwind.js"), ensure_ascii=False
    ).replace("</", "<\\/")

    bundle = {
        "characters": characters,
        "lightcones": lightcones,
        "relic_sets": relic_sets,
        "modes": modes,
        "sources": sources,
    }
    # 用户保存的外观主题（有就内联进来，让网页版长得和工具箱一样）；
    # 用户包不要带作者的主题，所以 with_theme=False 时当作空主题。
    theme_path = ROOT / "userdata" / "interface" / "theme.json"
    theme: dict = {}
    if with_theme:
        try:
            theme = read_json(theme_path) if theme_path.is_file() else {}
            if not isinstance(theme, dict):
                theme = {}
        except (OSError, ValueError):
            theme = {}
    theme_js = json.dumps(theme, ensure_ascii=False, separators=(",", ":"))
    data_js = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    oracle_js = json.dumps(oracle, ensure_ascii=False, separators=(",", ":"))
    version = re.search(r'__version__\s*=\s*"([^"]+)"', read(ROOT / "core" / "__init__.py"))
    version_text = version.group(1) if version else "?"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>崩铁配速查询 · 角色顶分 · 网页版</title>
<style>
{shell_css}
</style>
<style>
{feature_css}
/* 单文件网页版的收尾样式：工具箱外壳的 html/body 是 height:100% + overflow:hidden，
   这里要放开滚动，否则只有一个屏幕高。字体沿用外壳的 font 声明。 */
html, body {{ height: auto; overflow: visible; }}
.gt-standalone-head {{
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  padding: 12px 20px; border-bottom: 1px solid var(--border); background: var(--panel);
}}
.gt-standalone-head h1 {{ font-size: 16px; margin: 0; }}
.gt-standalone-head .gt-sub {{ color: var(--muted); font-size: 12px; }}
.gt-standalone-head .gt-selftest {{
  margin-left: auto; font-size: 12.5px; padding: 5px 10px; border-radius: 8px;
  border: 1px solid var(--border); background: var(--panel-2);
}}
.gt-selftest.ok {{ color: var(--good); border-color: color-mix(in srgb, var(--good) 45%, transparent); }}
.gt-selftest.bad {{ color: var(--bad); border-color: color-mix(in srgb, var(--bad) 45%, transparent); }}
.gt-standalone-body {{ max-width: 1180px; margin: 0 auto; padding: 16px 20px 60px; }}
#gt-failures {{ margin-top: 10px; font-size: 12px; color: var(--bad); white-space: pre-wrap; }}
.gt-tabs {{ display: flex; gap: 4px; }}
.gt-tab {{ background: transparent; border: 1px solid var(--border); color: var(--muted); padding: 5px 12px; border-radius: 8px; cursor: pointer; font-size: 13px; }}
.gt-tab.is-active {{ color: var(--text); border-color: var(--accent); background: var(--panel-2); }}

/* ---------------- 手机适配 ----------------
   窄屏上把「一行多列」摊成一列，输入框铺满，表格横向滚动，
   下拉浮层由 JS 钳在屏幕内（见 ui.js 的 open()）。 */
@media (max-width: 700px) {{
  .gt-standalone-head {{ padding: 10px 12px; gap: 8px; }}
  .gt-standalone-head h1 {{ font-size: 15px; }}
  .gt-standalone-head .gt-sub {{ font-size: 11px; }}
  .gt-standalone-head .gt-selftest {{ margin-left: 0; width: 100%; text-align: center; font-size: 12px; }}
  .gt-standalone-body {{ padding: 10px 10px 40px; }}
  .card {{ padding: 12px; border-radius: 8px; }}
  .card h2 {{ font-size: 15px; }}
  .row {{ gap: 8px; }}
  .field {{ width: 100%; min-width: 0; }}
  .input, select.input, .picker-button, .btn {{ width: 100%; min-width: 0; box-sizing: border-box; }}
  .row.tight {{ flex-wrap: wrap; }}
  .row.tight .input {{ width: auto; flex: 1 1 90px; }}
  .picker-layout {{ flex-direction: column; }}
  .splash-panel {{ width: 100%; max-width: 300px; margin: 0 auto; }}
  .splash-panel img {{ height: 250px; }}
  .picker-controls {{ min-width: 0; }}
  .pick-summary .ps-row > span {{ flex: 0 0 74px; }}
  /* 表格：窄屏靠横向滚动，别把页面撑破 */
  .card > div[style*="overflow-x"] {{ -webkit-overflow-scrolling: touch; }}
  table.data {{ font-size: 12.5px; }}
  table.data th, table.data td {{ padding: 6px 8px; white-space: nowrap; }}
  .stat .v {{ font-size: 18px; }}
  .gt-tabs {{ width: 100%; }}
  .gt-tab {{ flex: 1; }}
}}
</style>
<style>
{herta_css}
</style>
<style>
{aha_css}
</style>
</head>
<body>
<header class="gt-standalone-head">
  <h1>🚄 崩铁工具 · 网页版</h1>
  <nav class="gt-tabs"><button class="gt-tab is-active" data-view="view">🎯 配速查询</button><button class="gt-tab" data-view="view-aha">🎭 欢愉队配速</button><button class="gt-tab" data-view="view-herta">📜 角色顶分</button></nav>
  <span class="gt-sub" id="gt-sub">单文件 · 双击即用 · 不需要服务</span>
  <span class="gt-selftest" id="gt-selftest">自检中…</span>
</header>
<div class="gt-standalone-body">
  <div id="view"></div>
  <div id="view-aha" hidden></div>
  <div id="view-herta" hidden></div>
  <div id="gt-failures"></div>
</div>

<script>window.GT_STANDALONE = true; window.GT_THEME = {theme_js};</script>
<script>window.GT_ASSETS = __GT_ASSETS_JSON__;</script>
<script>
{THEME_APPLY_JS}
</script>
<script>applyStandaloneTheme(window.GT_THEME);</script>
<script>window.GT_DATA = {data_js};</script>
<script>window.GT_ORACLE = {oracle_js};</script>
<script>
{web_api}
</script>
<script>
{SELFTEST_JS}
</script>
<script>
{SHIM_JS}
</script>
<script>
{ui}
</script>
<script>
{herta_api}
</script>
<script>
{herta_ui}
</script>
<script>
{aha_api}
</script>
<script>
window.GT_AHA_ORIGINAL_HTML = {aha_original_js};
window.GT_AHA_VENDOR_JS = {aha_vendor_js};
</script>
<script>
{aha_ui}
</script>
<script>
(async function () {{
  const storage = {{
    load: () => {{
      try {{ return JSON.parse(localStorage.getItem("gt-speed-plan") || "{{}}"); }} catch (e) {{ return {{}}; }}
    }},
    save: (value) => {{
      try {{ localStorage.setItem("gt-speed-plan", JSON.stringify(value)); }} catch (e) {{ /* 隐私模式就算了 */ }}
    }},
  }};

  const api = window.GT_WEB_API.createApi(window.GT_DATA, storage);

  // 自检先跑：算法对不对，页面自己先说清楚
  const badge = document.getElementById("gt-selftest");
  try {{
    const result = runSelfTest(api, window.GT_ORACLE);
    if (result.failures.length === 0) {{
      badge.textContent = `✅ 自检通过 ${{result.checks}}/${{result.checks}}（与 Python 版逐项一致）`;
      badge.className = "gt-selftest ok";
      window.GT_SELFTEST = {{ ok: true, checks: result.checks, failures: [] }};
    }} else {{
      badge.textContent = `⚠ 自检 ${{result.checks - result.failures.length}}/${{result.checks}}，${{result.failures.length}} 项不一致`;
      badge.className = "gt-selftest bad";
      document.getElementById("gt-failures").textContent = result.failures.slice(0, 20).join("\\n");
      window.GT_SELFTEST = {{ ok: false, checks: result.checks, failures: result.failures }};
    }}
  }} catch (error) {{
    badge.textContent = "⚠ 自检执行失败：" + error.message;
    badge.className = "gt-selftest bad";
    window.GT_SELFTEST = {{ ok: false, checks: 0, failures: [String(error.message)] }};
  }}

  // 和工具箱一样的调用契约（app/app.js 的 makeCtx）
  const ctx = buildCtx(api);

  try {{
    await GT_FEATURE.mount(document.getElementById("view"), ctx);
    window.GT_MOUNTED = true;
  }} catch (error) {{
    document.getElementById("view").innerHTML =
      `<p class="error-text">界面挂载失败：${{error.message}}</p>`;
    window.GT_MOUNTED = false;
  }}

  // 角色顶分：切到该标签时才挂载（会联网拉镜像）
  const hertaStorage = {{
    load: () => {{ try {{ return JSON.parse(localStorage.getItem("gt-herta") || "{{}}"); }} catch (e) {{ return {{}}; }} }},
    save: (value) => {{ try {{ localStorage.setItem("gt-herta", JSON.stringify(value)); }} catch (e) {{}} }},
  }};
  const hertaApi = window.GT_HERTA_API.createApi({{ storage: hertaStorage, characters: window.GT_DATA.characters, lightcones: window.GT_DATA.lightcones }});
  const hertaCtx = {{ moduleId: "herta", featureId: "records", call: (action, payload) => hertaApi.call(action, payload) }};
  const ahaApi = window.GT_AHA_SPEED_API.createApi();
    const readTeams = () => JSON.parse(localStorage.getItem("gt-aha-teams") || "{{}}");
    async function ahaCall(action, payload = {{}}) {{
      if (action === "library") return {{ presets: api.call("presets").presets, teams: readTeams(), characters: window.GT_DATA.characters, lightcones: window.GT_DATA.lightcones, relicSets: window.GT_DATA.relic_sets }};
      if (action === "resolve_build") {{
        const entry = api.call("presets").presets[payload.characterId];
        if (!entry) throw new Error("该角色尚未保存配装，请先到配速查询保存。");
        if (!ahaApi.call("catalog").roster.some(r => r.id === payload.characterId)) throw new Error("模拟器尚未支持该角色机制。");
        return {{ entry, result: api.call("plan", {{ ...entry.config, characterId: payload.characterId }}) }};
      }}
      if (action === "save_team") {{
        const name = String(payload.name || "").trim();
        if (!name || name.length > 80) throw new Error("队伍名称需要 1 到 80 个字符。");
        if (!Array.isArray(payload.team) || payload.team.length < 1 || payload.team.length > 4 || !payload.config || typeof payload.config !== "object") throw new Error("缺少有效的队伍模拟配置。");
        if (payload.team.some(u => !ahaApi.call("catalog").roster.some(r => r.id === u.id))) throw new Error("队伍包含模拟器尚未支持的角色。");
        ahaApi.call("simulate", {{ ...payload.config, team: payload.team }});
        const teams = readTeams();
        if (payload.id && !teams[payload.id]) throw new Error("该队伍存档已不存在，请另存队伍。");
        const id = payload.id || crypto.randomUUID();
        teams[id] = {{ name, team: payload.team, config: payload.config, savedAt: new Date().toISOString() }};
        localStorage.setItem("gt-aha-teams", JSON.stringify(teams));
        return {{ id, teams }};
      }}
      if (action === "delete_team") {{
        const teams = readTeams();
        if (!teams[payload.id]) throw new Error("请选择已有的队伍存档。");
        delete teams[payload.id]; localStorage.setItem("gt-aha-teams", JSON.stringify(teams)); return {{ teams }};
      }}
      return ahaApi.call(action, payload);
    }}
    const ahaCtx = {{ moduleId: "honkai-star-rail", featureId: "aha-speed", feature: {{ baseUrl: "/modules/honkai-star-rail/features/aha-speed" }}, call: ahaCall, fmt: gtFmt, ui: {{ escapeHtml: gtEscapeHtml, fmt: gtFmt }} }};
  let hertaMounted = false;
  let ahaMounted = false;
  async function showView(id) {{
    document.querySelectorAll(".gt-tab").forEach((b) => b.classList.toggle("is-active", b.dataset.view === id));
    document.getElementById("view").hidden = id !== "view";
    document.getElementById("view-aha").hidden = id !== "view-aha";
    document.getElementById("view-herta").hidden = id !== "view-herta";
    if (id === "view-aha" && !ahaMounted) {{
      ahaMounted = true;
      try {{ await GT_AHA_FEATURE.mount(document.getElementById("view-aha"), ahaCtx); window.GT_AHA_MOUNTED = true; }}
      catch (error) {{ document.getElementById("view-aha").innerHTML = `<p class="error-text">界面挂载失败：${{error.message}}</p>`; window.GT_AHA_MOUNTED = false; }}
    }}
    if (id === "view-herta" && !hertaMounted) {{
      hertaMounted = true;
      try {{ await GT_HERTA_FEATURE.mount(document.getElementById("view-herta"), hertaCtx); window.GT_HERTA_MOUNTED = true; }}
      catch (error) {{ document.getElementById("view-herta").innerHTML = `<p class="error-text">界面挂载失败：${{error.message}}</p>`; window.GT_HERTA_MOUNTED = false; }}
    }}
    const hash = id === "view-herta" ? "#herta" : (id === "view-aha" ? "#aha" : "");
    if (location.hash !== hash) history.replaceState(null, "", hash || (location.pathname + location.search));
  }}
  document.querySelectorAll(".gt-tab").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  if (location.hash === "#herta") showView("view-herta");
  if (location.hash === "#aha") showView("view-aha");
}})();
</script>
</body>
</html>
"""

    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / (out_name or OUT_NAME)

    # 素材内联：先全内联，超过 INLINE_LIMIT 就退回远程 URL（_remote 兜底）。
    # 注意：HTML 是由 f-string 拼出来的（JSON 里也全是花括号），所以这里**不能**再用
    # str.format 填模板 —— 用唯一 token 做字符串替换。
    assets = asset_data_uris()
    inlined = 0
    if assets:
        html_with = html.replace(
            "__GT_ASSETS_JSON__", json.dumps(assets, separators=(",", ":"))
        )
        if len(html_with.encode("utf-8")) <= INLINE_LIMIT:
            html = html_with
            inlined = len(assets)
        else:
            print(
                f"  素材内联后会到 {len(html_with.encode('utf-8')) / 1024 / 1024:.1f} MB"
                f"（上限 {INLINE_LIMIT / 1024 / 1024:.0f} MB）→ 退回远程 URL，网页版需要联网看图"
            )
    if not inlined:
        # 不内联：GT_ASSETS 给空对象，ui.js 会退回远程地址
        html = html.replace("__GT_ASSETS_JSON__", "{}")

    # 副标题跟着实际情况走，别写死「图片从 CDN 取」——内联之后那句话就是错的
    html = html.replace(
        "单文件 · 双击即用 · 不需要服务",
        "单文件 · 双击即用 · 不需要服务 · 图片已内联（完全离线）"
        if inlined
        else "单文件 · 双击即用 · 不需要服务（图片从官方 CDN 取）",
    )

    out.write_text(html, encoding="utf-8")
    print(f"网页版已生成：{out}")
    print(f"  大小：{out.stat().st_size / 1024:.1f} KB（内联了角色 {len(characters)}、光锥 {len(lightcones)}、遗器 {len(relic_sets)}）")
    print(f"  图片素材：{'内联 ' + str(inlined) + ' 张（完全离线）' if inlined else '未内联（走远程 CDN）'}")
    print(f"  工具箱版本：v{version_text}")
    return out


if __name__ == "__main__":
    build()
