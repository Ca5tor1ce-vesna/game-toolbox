/**
 * 用 Edge 的 CDP 给界面截图 + 像素级验收（headless 也走同一套命令）。
 *
 * 用法：<node> tools/shot_ui.mjs <输出目录> [端口] [调试端口]
 *   <node> tools/shot_ui.mjs dist\shots 8960 9222
 *   需要先起服务（python run.py --no-open --port 8960）和 Edge
 *   （--headless=new --remote-debugging-port=9222 --user-data-dir=<临时目录>）。
 *
 * 为什么要自己驱动 CDP：需要**点开浮层**再截图，`--screenshot` 那种一次性命令
 * 截不到浮层里的图标。这里只依赖 Node 内置的 WebSocket（Node 22+）与 fetch，
 * 不装任何第三方包。
 *
 * 与 v0.16.x 那版的差别（0.17.2 的界面是新的两栏步骤卡片）：
 *   - 进功能页仍是 `.nav-feature[data-feature="speed-plan"]`；
 *   - 下拉浮层从 `.picker-panel` 改名 `.picker-popup`，角色改成 `.sp-char` 头像网格；
 *   - 旧的「面板 vs 卡片镜像控件」在 0.17.2 已经不存在（每个字段只有一个控件，
 *     `syncControls()` 是唯一写入口）。这里的等价断言换成
 *     **「控件 ↔ 步骤抬头 #sum-*」往返一致性** + **「控件 → 结果」真实生效**（改一下
 *     速度鞋，`#hero-current` 必须真的变），因为 0.16.x 那个 bug 的本质就是
 *     "显示没勾、其实在算 +25"，这条断言仍然能钉住它。
 *
 * 退出码：0 = 全部断言通过；1 = 有断言失败（细节在报告里）。
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const outDir = process.argv[2] || "dist/shots";
const port = Number(process.argv[3] || 8960);
const debugPort = Number(process.argv[4] || 9222);
const BASE = `http://127.0.0.1:${port}`;

mkdirSync(outDir, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ---------------- CDP 小客户端 ---------------- */

async function firstPageTarget() {
  for (let i = 0; i < 40; i += 1) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
      const page = list.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
      if (page) return page;
    } catch {
      /* 浏览器还没起来 */
    }
    await sleep(250);
  }
  throw new Error(`连不上 CDP（Edge 起来了但没开 --remote-debugging-port=${debugPort}？）`);
}

class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      const slot = this.pending.get(msg.id);
      if (!slot) return;
      this.pending.delete(msg.id);
      if (msg.error) slot.reject(new Error(JSON.stringify(msg.error)));
      else slot.resolve(msg.result);
    });
  }

  send(method, params = {}) {
    const id = (this.id += 1);
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`${method} 超时`));
        }
      }, 30000);
    });
  }

  async eval(expression) {
    const res = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (res.exceptionDetails) {
      throw new Error(
        `${res.exceptionDetails.text} ${res.exceptionDetails.exception?.description || ""}`,
      );
    }
    return res.result.value;
  }

  /**
   * 复杂对象统一回传成 JS 对象（普通表达式自己先 stringify 一遍，
   * 因为 `returnByValue` 偶尔给 undefined）。
   *
   * 坑：**异步体不能套 `JSON.stringify`** —— 那是对 Promise 做 stringify，结果恒为
   * `{}`。所以 `(async () => {...})()` 这种表达式直接交给 `awaitPromise` 等结果。
   */
  async json(expression) {
    const source = expression.trim();
    if (source.startsWith("(async")) return this.eval(source);
    return JSON.parse(await this.eval(`JSON.stringify(${expression})`));
  }

  async shot(name, { fullPage = false } = {}) {
    const params = { format: "png" };
    if (fullPage) params.captureBeyondViewport = true;
    const { data } = await this.send("Page.captureScreenshot", params);
    const path = join(outDir, `${name}.png`);
    writeFileSync(path, Buffer.from(data, "base64"));
    console.log(`  📷 ${path}`);
    return path;
  }
}

/* ---------------- 断言台账 ---------------- */

const checks = [];
const check = (name, ok, detail = "") => {
  checks.push({ name, ok: Boolean(ok), detail: String(detail) });
  console.log(`  ${ok ? "OK  " : "FAIL"} ${name}${detail ? "  " + detail : ""}`);
};

/* ---------------- 接上浏览器 ---------------- */

const target = await firstPageTarget();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  ws.addEventListener("open", resolve);
  ws.addEventListener("error", reject);
});
const cdp = new Cdp(ws);
await cdp.send("Page.enable");
await cdp.send("Runtime.enable");
await cdp.send("Emulation.setDeviceMetricsOverride", {
  width: 1360,
  height: 1000,
  deviceScaleFactor: 1,
  mobile: false,
});

const waitFor = async (expression, { tries = 60, wait = 500, label = expression } = {}) => {
  for (let i = 0; i < tries; i += 1) {
    try {
      if (await cdp.eval(`Boolean(${expression})`)) return true;
    } catch {
      /* 页面还在换 DOM */
    }
    await sleep(wait);
  }
  console.log(`  ⚠ 等待超时：${label}`);
  return false;
};

console.log(`打开 ${BASE}/ …`);
await cdp.send("Page.navigate", { url: `${BASE}/` });
const shellReady = await waitFor("document.querySelector('#nav')", { label: "外壳 #nav" });
check("外壳挂载（#nav / #view）", shellReady);

// 进「配速查询」：外壳只是侧边栏 + 空 #view，功能要点了才挂载。
// 注意两点：① `#nav` 容器先出现、按钮要等 `/api/registry` 回来才有；
//          ② 导航模块可能被上次的折叠状态收起来（localStorage 记着），所以先展开再点。
const navReady = await waitFor("document.querySelector('.nav-feature[data-feature=\"speed-plan\"]')", {
  label: "导航出现 speed-plan 按钮",
});
const entered = await cdp.json(`(() => {
  const box = document.querySelector('.nav-module[data-module-id="honkai-star-rail"]');
  if (box && box.classList.contains('collapsed')) {
    box.querySelector('.nav-module-title')?.click();
  }
  const all = [...document.querySelectorAll('.nav-feature')].map(b => b.dataset.feature);
  const btn = document.querySelector('.nav-feature[data-feature="speed-plan"]');
  if (!btn) return { ok: false, features: all };
  btn.click();
  return { ok: true, features: all };
})()`);
console.log("  导航功能列表:", entered.features.join(","));
check("找得到 speed-plan 入口并点进去了", navReady && entered.ok);

check("功能页挂载（.sp / #char-grid）", await waitFor("document.querySelector('#char-grid')"));
check("角色头像网格有内容（.sp-char）", await waitFor("document.querySelectorAll('.sp-char').length > 2"));
// 等首次计算落地（pickCharacter → run() 会写 #hero-current）
check("首屏算出结果（#hero-current 有数字）", await waitFor("/\\d/.test(document.querySelector('#hero-current')?.textContent || '')"));
await cdp.eval("window.scrollTo(0, 0)");
await sleep(800);

/* ---------------- 截图：首屏与浮层 ---------------- */

await cdp.shot("01-选角色与配装");

// ① 角色头像网格（0.17.2 换成了头像墙，图标必须真的画出来）
const gridReport = await cdp.json(`(() => {
  const tiles = [...document.querySelectorAll('.sp-char')];
  const withImg = tiles.filter(t => t.querySelector('img'));
  const broken = withImg.filter(t => {
    const img = t.querySelector('img');
    return img.style.visibility !== 'hidden' && !(img.naturalWidth > 0 && img.naturalHeight > 0);
  });
  const custom = tiles.filter(t => t.querySelector('.sp-custom-icon')).length;
  return {
    tiles: tiles.length,
    withImg: withImg.length,
    broken: broken.length,
    custom,
    sample: withImg.slice(0, 3).map(t => {
      const img = t.querySelector('img');
      return { name: (t.textContent || '').trim().slice(0, 12), w: img.naturalWidth, h: img.naturalHeight };
    }),
  };
})()`);
console.log("  角色网格:", JSON.stringify(gridReport));
check(
  "角色头像网格：每个格子都真的解码出了图标",
  gridReport.withImg > 0 && gridReport.broken === 0,
  `格子 ${gridReport.tiles}，带图 ${gridReport.withImg}，坏图 ${gridReport.broken}`,
);
check("角色网格里有「＋ 自定义角色」", gridReport.custom === 1);

// ② 光锥下拉浮层（只显示同命途）
const openedCone = await cdp.eval(`(() => {
  const btn = document.querySelector('#lightcone-picker');
  if (!btn) return 'no #lightcone-picker';
  btn.click();
  return 'clicked';
})()`);
console.log("  光锥下拉:", openedCone);
await sleep(1200);
await cdp.shot("02-光锥下拉图标");
const conePopup = await cdp.json(`(() => {
  const popup = document.querySelector('.picker-popup:not(.hidden)');
  if (!popup) return { open: false };
  const items = [...popup.querySelectorAll('.picker-item')];
  const imgs = items.map(i => i.querySelector('img')).filter(Boolean);
  const broken = imgs.filter(i => i.style.visibility !== 'hidden' && !(i.naturalWidth > 0));
  const list = popup.querySelector('.picker-list');
  const cs = list ? getComputedStyle(list) : null;
  return {
    open: true,
    items: items.length,
    imgs: imgs.length,
    broken: broken.length,
    listMaxHeight: cs ? cs.maxHeight : null,
    listOverflowY: cs ? cs.overflowY : null,
    scrollbarWidth: cs ? (cs.scrollbarWidth || '(auto)') : null,
  };
})()`);
console.log("  光锥浮层:", JSON.stringify(conePopup));
check("光锥浮层打开且有选项", conePopup.open && conePopup.items > 0, `选项 ${conePopup.items}`);
check("光锥浮层图标全部解码成功", conePopup.imgs > 0 && conePopup.broken === 0, `图 ${conePopup.imgs}，坏 ${conePopup.broken}`);
check("光锥浮层列表限高可滚（max-height/auto）", conePopup.listMaxHeight === "340px" && conePopup.listOverflowY === "auto", `${conePopup.listMaxHeight} / ${conePopup.listOverflowY}`);

// ③ 遗器 4 件套下拉
const openedRelic = await cdp.eval(`(() => {
  document.body.click();                       // 先关掉上一个浮层
  const btn = document.querySelector('#fourPiece-picker');
  if (!btn) return 'no #fourPiece-picker';
  btn.click();
  return 'clicked';
})()`);
console.log("  遗器下拉:", openedRelic);
await sleep(1200);
await cdp.shot("03-遗器下拉图标");
const relicPopup = await cdp.json(`(() => {
  const popup = document.querySelector('.picker-popup:not(.hidden)');
  if (!popup) return { open: false };
  const imgs = [...popup.querySelectorAll('.picker-item img')];
  return {
    open: true,
    items: popup.querySelectorAll('.picker-item').length,
    imgs: imgs.length,
    broken: imgs.filter(i => i.style.visibility !== 'hidden' && !(i.naturalWidth > 0)).length,
  };
})()`);
console.log("  遗器浮层:", JSON.stringify(relicPopup));
check("遗器浮层打开且有选项", relicPopup.open && relicPopup.items > 0, `选项 ${relicPopup.items}`);
check("遗器浮层图标全部解码成功", relicPopup.imgs > 0 && relicPopup.broken === 0, `图 ${relicPopup.imgs}，坏 ${relicPopup.broken}`);
await cdp.eval("document.body.click()");
await sleep(400);

// ④ 立绘 #splash
const splash = await cdp.json(`(() => {
  const img = document.querySelector('#splash');
  if (!img) return { exists: false };
  return {
    exists: true,
    w: img.naturalWidth,
    h: img.naturalHeight,
    visibility: getComputedStyle(img).visibility,
    src: (img.currentSrc || '').slice(0, 60),
    meta: (document.querySelector('#splash-meta')?.textContent || '').trim().slice(0, 60),
  };
})()`);
console.log("  立绘:", JSON.stringify(splash));
check("立绘 #splash 可见且解码成功", splash.exists && splash.w > 0 && splash.h > 0 && splash.visibility === "visible", `${splash.w}x${splash.h} ${splash.visibility}`);

/* ---------------- 结果区四个页签 ---------------- */

for (const [tab, shot] of [
  ["timeline", "04-行动时间轴"],
  ["tables", "05-各模式需求"],
  ["recommend", "06-自动推荐"],
]) {
  await cdp.eval(`(() => {
    const btn = document.querySelector('.sp-tabs .tab[data-tab="${tab}"]');
    if (btn) btn.click();
    return true;
  })()`);
  await sleep(500);
  await cdp.shot(shot);
}
// 回到「计算明细」，后面截结论区
await cdp.eval(`(() => { document.querySelector('.sp-tabs .tab[data-tab="detail"]')?.click(); return true; })()`);
await sleep(400);
const tabReport = await cdp.json(`(() => {
  const tabs = [...document.querySelectorAll('.sp-tabs .tab')].map(t => t.dataset.tab);
  const visible = [...document.querySelectorAll('.sp-panel')].filter(p => !p.classList.contains('hidden')).map(p => p.dataset.panel);
  return { tabs, visible };
})()`);
console.log("  页签:", JSON.stringify(tabReport));
check("四个结果页签都在，切回来只剩 detail 可见", tabReport.tabs.length === 4 && tabReport.visible.length === 1 && tabReport.visible[0] === "detail");

/* ---------------- 镜像一致性 + 控件真的生效 ---------------- */

// 先把角色区看得到的锚点滚到顶部，截「已选配装摘要」那张
await cdp.eval(`(() => { const b = document.querySelector('.sp-step[data-step="relic"]'); if (b) b.scrollIntoView({block: 'start'}); return true; })()`);
await sleep(600);
await cdp.shot("07-遗器与摘要");

/**
 * 0.17.2 的等价断言：每个字段只有一个控件，`syncControls()` 把 state 刷回控件；
 * 而**步骤抬头 #sum-*** 是从 state 渲染的。所以只要抬头与控件对得上，
 * 「显示的和在算的」就一致（0.16.x 的 bug 正是这两者不一致）。
 */
const mirror = await cdp.json(`(() => {
  const rows = [];
  const push = (label, ok, detail) => rows.push({ label, ok: Boolean(ok), detail: String(detail) });
  const pick = (s) => document.querySelector(s);
  const text = (s) => (pick(s)?.textContent || '').trim();

  const relicSum = text('#sum-relic');
  const boots = pick('#speedBoots');
  push(
    '速度鞋 #speedBoots ↔ #sum-relic',
    Boolean(boots) && (boots.checked ? relicSum.includes('速度鞋') && !relicSum.includes('非速度鞋') : relicSum.includes('非速度鞋')),
    'checkbox=' + (boots ? boots.checked : 'missing') + ' 抬头=' + relicSum,
  );

  const bonusSum = text('#sum-bonus');
  const substat = pick('#substat');
  push(
    '副词条 #substat ↔ #sum-bonus',
    Boolean(substat) && bonusSum.includes('+' + String(Number(substat.value || 0))),
    'input=' + (substat ? substat.value : 'missing') + ' 抬头=' + bonusSum,
  );

  const charSum = text('#sum-char');
  const eidolon = pick('#eidolon');
  push(
    '星魂 #eidolon ↔ #sum-char',
    Boolean(eidolon) && charSum.includes(String(eidolon.value) + ' 魂'),
    'select=' + (eidolon ? eidolon.value : 'missing') + ' 抬头=' + charSum,
  );

  const targetSum = text('#sum-target');
  const firstUlt = pick('#firstUltAction');
  push(
    '首次开大 #firstUltAction ↔ #sum-target',
    Boolean(firstUlt) && targetSum.includes(String(Number(firstUlt.value)) === 0 ? '进战' : '第 ' + Number(firstUlt.value) + ' 动后'),
    'input=' + (firstUlt ? firstUlt.value : 'missing') + ' 抬头=' + targetSum,
  );

  const coneSum = text('#sum-cone');
  push('光锥抬头有内容（#sum-cone）', coneSum.length > 0, coneSum);

  return { rows, ok: rows.every(r => r.ok) };
})()`);
for (const row of mirror.rows) {
  check(`镜像一致：${row.label}`, row.ok, row.detail);
}

/**
 * 控件真的生效：勾掉「速度鞋」（主词条 +25）→ 当前速度必须下降 25，
 * 再勾回来必须回到原值。这条能同时钉住「勾选没绑上」和「算的时候没算」。
 *
 * 注意：这里**不能**写成 `JSON.stringify((async () => {...})())` ——
 * 那是对 Promise 做 stringify，结果恒为 `{}`（踩过一次）。异步体直接返回对象，
 * 由 CDP 的 `awaitPromise` 帮我们等。
 */
const bootsEffect = await cdp.json(`(async () => {
  const $ = (s) => document.querySelector(s);
  const speed = () => Number(($('#hero-current')?.textContent || '').trim());
  const settle = (ms) => new Promise(r => setTimeout(r, ms));
  const boots = $('#speedBoots');
  if (!boots) return { ok: false, reason: 'no #speedBoots' };
  const before = speed();
  boots.checked = false; boots.dispatchEvent(new Event('change', { bubbles: true }));
  await settle(1200);
  const off = speed();
  boots.checked = true; boots.dispatchEvent(new Event('change', { bubbles: true }));
  await settle(1200);
  const back = speed();
  return { ok: true, before, off, back, delta: Number((before - off).toFixed(1)) };
})()`);
console.log("  速度鞋实际生效:", JSON.stringify(bootsEffect));
check(
  "改「速度鞋」→ 当前速度真的变化（且差 25 速）",
  bootsEffect.ok && bootsEffect.delta === 25,
  `开=${bootsEffect.before} 关=${bootsEffect.off} 复位=${bootsEffect.back} Δ=${bootsEffect.delta}`,
);
check(
  "「速度鞋」复位后当前速度回到原值",
  bootsEffect.ok && bootsEffect.back === bootsEffect.before,
  `${bootsEffect.before} → ${bootsEffect.back}`,
);

/* ---------------- 自定义角色表单（只开表单，不建真实角色） ---------------- */

const customOpened = await cdp.eval(`(() => {
  const search = document.querySelector('#char-search');
  if (!search) return 'no #char-search';
  search.value = '自定义';
  search.dispatchEvent(new Event('input', { bubbles: true }));
  const tile = document.querySelector('.sp-char[data-char] .sp-custom-icon')?.closest('.sp-char');
  if (!tile) return '没找到自定义角色格子';
  tile.click();
  return 'clicked';
})()`);
console.log("  自定义角色:", customOpened);
check("点「＋ 自定义角色」进得去", customOpened === "clicked");
check("自定义角色表单展开（#custom-fields 可见）", await waitFor("!document.querySelector('#custom-fields')?.classList.contains('hidden')", { tries: 20 }));
await sleep(800);
const customForm = await cdp.json(`(() => {
  const box = document.querySelector('#custom-fields');
  return {
    visible: box ? !box.classList.contains('hidden') : false,
    name: document.querySelector('#customName')?.value,
    base: document.querySelector('#customBase')?.value,
    trace: document.querySelector('#customTrace')?.value,
    sum: (document.querySelector('#sum-char')?.textContent || '').trim(),
  };
})()`);
console.log("  自定义表单:", JSON.stringify(customForm));
check(
  "自定义抬头跟着表单走（#sum-char）",
  customForm.visible && customForm.sum.includes("自定义"),
  customForm.sum,
);
await cdp.eval(`(() => { const b = document.querySelector('.sp-step[data-step="char"]'); if (b) b.scrollIntoView({block:'start'}); return true; })()`);
await sleep(500);
await cdp.shot("08-自定义角色表单");

/* ---------------- 两栏对齐 / 横向溢出 / 图片体检 ---------------- */

const measure = async (width) => {
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  // 量 rect 前必须滚到顶，否则拿到的是视口相对坐标（可能是负数）
  await cdp.eval(`(() => { window.scrollTo(0, 0); return true; })()`);
  await sleep(700);
  return cdp.json(`(() => {
    const rect = (el) => {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { top: Math.round(r.top), height: Math.round(r.height), bottom: Math.round(r.bottom), width: Math.round(r.width) };
    };
    const left = document.querySelector('.sp-left');
    const right = document.querySelector('.sp-right');
    const grid = document.querySelector('.sp');
    return {
      viewport: [window.innerWidth, window.innerHeight],
      scrollWidth: document.documentElement.scrollWidth,
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
      gridColumns: grid ? getComputedStyle(grid).gridTemplateColumns : null,
      left: rect(left),
      right: rect(right),
      rightOverflowY: right ? getComputedStyle(right).overflowY : null,
      rightCanScroll: right ? right.scrollHeight > right.clientHeight + 1 : null,
    };
  })()`);
};

const layout1360 = await measure(1360);
const layout1024 = await measure(1024);
console.log("  1360px:", JSON.stringify(layout1360));
console.log("  1024px:", JSON.stringify(layout1024));
check("1360px 无横向溢出", !layout1360.horizontalOverflow, `scrollWidth=${layout1360.scrollWidth} viewport=${layout1360.viewport[0]}`);
check("1024px 无横向溢出", !layout1024.horizontalOverflow, `scrollWidth=${layout1024.scrollWidth} viewport=${layout1024.viewport[0]}`);
check(
  "两栏都在、顶部对齐（1024px 起右栏改静态堆叠）",
  Boolean(layout1024.left && layout1024.right) && (layout1024.right.top === layout1024.left.top || layout1024.right.top > layout1024.left.top),
  `left.top=${layout1024.left?.top} right.top=${layout1024.right?.top}`,
);
check("右栏限高可滚（overflow-y auto）", layout1360.rightOverflowY === "auto", String(layout1360.rightOverflowY));
await cdp.shot("09-两栏对齐-1024");
await measure(1360);
await cdp.shot("10-两栏对齐-1360");

// 图片体检：页面上所有在用的 img 是否都真的解码出了尺寸
const imageReport = await cdp.json(`(() => {
  const imgs = [...document.querySelectorAll('img')];
  const broken = [], sample = [];
  let ok = 0, hidden = 0, lazy = 0;
  for (const img of imgs) {
    const src = img.currentSrc || img.getAttribute('src') || '';
    if (!src) { hidden += 1; continue; }
    if (img.style.visibility === 'hidden') { hidden += 1; continue; }
    if (img.naturalWidth > 0 && img.naturalHeight > 0) {
      ok += 1;
      if (sample.length < 4) sample.push({ src: src.slice(0, 48), w: img.naturalWidth, h: img.naturalHeight });
    } else if (img.loading === 'lazy' || !img.complete) {
      lazy += 1;                                  // 懒加载还没进视口，不算坏图
    } else {
      broken.push(src.slice(0, 80));
    }
  }
  return { total: imgs.length, ok, hidden, lazy, broken, sample };
})()`);
console.log("  图片体检:", JSON.stringify(imageReport, null, 1));
check("页面图片没有坏图（naturalWidth=0）", imageReport.broken.length === 0, `OK ${imageReport.ok} / 坏 ${imageReport.broken.length}`);

/* ---------------- 汇总 ---------------- */

ws.close();

const failed = checks.filter((c) => !c.ok);
console.log(`\n=== 像素级验收：${checks.length - failed.length}/${checks.length} 通过 ===`);
if (failed.length) {
  console.log("失败项：");
  for (const f of failed) console.log(`  ❌ ${f.name}  ${f.detail}`);
  console.log("❌ 验收未通过");
  process.exit(1);
}
console.log(`✅ 全部通过，截图在 ${outDir}\\`);
