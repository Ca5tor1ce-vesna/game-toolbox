/**
 * 欢愉队配速（aha-speed）与行动值排轴（action-value）界面验收。
 *
 * 这是 shot_ui.mjs 的姊妹件：那个钉「配速查询」的像素级断言，这个钉新加的两个界面
 * （欢愉队配速模拟 + 行动值排轴）的**数值与机制**：阿哈时刻速度、真珠拉人/额外回合、
 * 星神★阿哈拉条阿哈、砂金终结技提速、速度拆解 153.18/135.00、隔离角色护栏、爻光结界 3-2-1-0、原版模式切换。
 *
 * 用法：<node> verify_aha_ui.mjs [服务端口] [调试端口] [截图目录] [单文件网页版 html 路径]
 *   需要先起服务（python run.py --no-open --port 8960）与 headless Edge
 *   （--headless=new --remote-debugging-port=9333 --user-data-dir=<临时目录>）。
 *   给了第 4 个参数时，额外做一段**离线**检查：把单文件网页版当本地文件打开、
 *   断网、切到「欢愉队配速」页签，确认模拟器照样挂载并出数（算法全内联）。
 *
 * 退出码：0 = 断言全过；1 = 有失败。
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const port = Number(process.argv[2] || 8960);
const debugPort = Number(process.argv[3] || 9333);
const outDir = process.argv[4] || "shots-aha";
const BASE = `http://127.0.0.1:${port}`;

mkdirSync(outDir, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function firstPageTarget() {
  for (let i = 0; i < 40; i += 1) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
      const page = list.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
      if (page) return page;
    } catch {
      /* 等浏览器起来 */
    }
    await sleep(250);
  }
  throw new Error(`连不上 CDP（Edge 没开 --remote-debugging-port=${debugPort}？）`);
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
      throw new Error(`${res.exceptionDetails.text} ${res.exceptionDetails.exception?.description || ""}`);
    }
    return res.result.value;
  }

  async json(expression) {
    const source = expression.trim();
    if (source.startsWith("(async")) return this.eval(source);
    return JSON.parse(await this.eval(`JSON.stringify(${expression})`));
  }

  async shot(name, { fullPage = false } = {}) {
    const params = { format: "png" };
    if (fullPage) {
      const metrics = await this.send("Page.getLayoutMetrics");
      const h = Math.ceil(metrics.cssContentSize?.height || 1000);
      await this.send("Emulation.setDeviceMetricsOverride", {
        width: 1360, height: Math.min(Math.max(h, 800), 6000), deviceScaleFactor: 1, mobile: false,
      });
      await sleep(400);
    }
    const { data } = await this.send("Page.captureScreenshot", { format: "png" });
    writeFileSync(join(outDir, `${name}.png`), Buffer.from(data, "base64"));
    console.log(`  截图 ${join(outDir, `${name}.png`)}`);
    if (fullPage) {
      await this.send("Emulation.setDeviceMetricsOverride", {
        width: 1360, height: 1000, deviceScaleFactor: 1, mobile: false,
      });
      await sleep(300);
    }
  }
}

const checks = [];
const check = (name, ok, detail = "") => {
  checks.push({ name, ok: Boolean(ok), detail: String(detail) });
  console.log(`  ${ok ? "OK  " : "FAIL"} ${name}${detail ? "  " + detail : ""}`);
};

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
  width: 1360, height: 1000, deviceScaleFactor: 1, mobile: false,
});

const waitFor = async (expression, { tries = 60, wait = 500, label = expression } = {}) => {
  for (let i = 0; i < tries; i += 1) {
    try {
      if (await cdp.eval(`Boolean(${expression})`)) return true;
    } catch {
      /* DOM 还在换 */
    }
    await sleep(wait);
  }
  console.log(`  等待超时：${label}`);
  return false;
};

/* ==================== 一、欢愉队配速（aha-speed） ==================== */

console.log(`\n[1] 欢愉队配速：${BASE}/#/honkai-star-rail/aha-speed`);
await cdp.send("Page.navigate", { url: `${BASE}/#/honkai-star-rail/aha-speed` });
const shellOk = await waitFor("document.querySelector('#nav')", { label: "外壳 #nav" });
check("外壳挂载", shellOk);
const ahaMounted = await waitFor("document.querySelector('.aha-sim-wrap')", { label: "aha-sim-wrap" });
check("欢愉队配速界面挂载（.aha-sim-wrap）", ahaMounted);
await waitFor("document.querySelectorAll('.aha-unit-card').length >= 4", { label: "4 个角色卡" });
check("默认四欢愉旗舰队：4 张角色卡", (await cdp.eval("document.querySelectorAll('.aha-unit-card').length")) === 4);
check("4 套预设按钮都在", (await cdp.eval("document.querySelectorAll('.aha-preset-btn').length")) === 4);

const ahaSummary = await cdp.json(`(() => {
  const box = document.querySelector('#aha-summary-box');
  const text = box ? box.textContent.replace(/\\s+/g, ' ') : '';
  const m = text.match(/有效速度[^0-9]*([0-9]+\\.?[0-9]*)/);
  return { text: text.slice(0, 260), speed: m ? Number(m[1]) : null };
})()`);
console.log("  摘要：", ahaSummary.text.slice(0, 150));
check("【阿哈时刻】有效速度已算出且 > 100", ahaSummary.speed !== null && ahaSummary.speed > 100, `speed=${ahaSummary.speed}`);
check("摘要含底速 106（星神★阿哈 94+专武12）", ahaSummary.text.includes("106"), "");

const mechBoard = await cdp.json(`(() => {
  const boxes = [...document.querySelectorAll('.aha-mech-box')];
  return boxes.map(b => ({
    title: (b.querySelector('.aha-mech-title')?.textContent || '').replace(/\\s+/g, ' ').trim(),
    logs: [...b.querySelectorAll('.aha-mech-item')].map(i => i.textContent.replace(/\\s+/g, ' ').trim()),
  }));
})()`);
check("核心机制看板 3 块（真珠 / 星神★阿哈 / 砂金）", mechBoard.length === 3);
const mechAll = mechBoard.map((b) => b.title + " " + b.logs.join(" ")).join(" | ");
check("真珠看板含【美学底本】与拉条记录", /美学底本/.test(mechAll) && /拉条/.test(mechBoard[0].title + mechBoard[0].logs.join(" ")), "");
check("真珠 4 欢愉触发额外回合记录", /额外回合/.test(mechBoard[0].logs.join(" ")), "");
check("星神★阿哈看板含终结技《啊哈！宇宙笑点大爆炸》与拉条 20%", /宇宙笑点大爆炸/.test(mechBoard[1].logs.join(" ")) && /20%/.test(mechBoard[1].logs.join(" ")), "");
check("星神★阿哈看板含【愿力】或【欢愉令使】记录", /愿力|令使/.test(mechBoard[1].logs.join(" ")), "");
check("砂金看板含终结技《胜局，凌越飓浪之上》与速度 +30%", /凌越飓浪之上/.test(mechBoard[2].logs.join(" ")) && /30/.test(mechBoard[2].logs.join(" ")), "");
check("砂金看板含【热意】回合外欢愉技记录", /举杯/.test(mechBoard[2].logs.join(" ")), "");

const tl = await cdp.json(`(() => {
  const rows = [...document.querySelectorAll('.aha-timeline-list .aha-ev-row')];
  const ahaRows = rows.filter(r => r.className.includes('ev-aha'));
  const anyText = rows.map(r => r.textContent).join(' ');
  return { total: rows.length, aha: ahaRows.length, anyText: anyText.slice(0, 200) };
})()`);
check("时间线渲染事件 > 40 条", tl.total > 40, `total=${tl.total}`);
check("时间线含【阿哈时刻】事件行", tl.aha > 0, `aha=${tl.aha}`);
await cdp.eval("window.scrollTo(0,0)");
await sleep(500);
await cdp.shot("01-欢愉队模拟-上半");
await cdp.eval(`(() => { document.querySelector('.aha-mech-grid')?.scrollIntoView({block:'start'}); return true; })()`);
await sleep(500);
await cdp.shot("02-机制看板");
await cdp.eval(`(() => { document.querySelector('#aha-timeline-list')?.scrollIntoView({block:'start'}); return true; })()`);
await sleep(500);
await cdp.shot("03-时间线");
await cdp.shot("04-欢愉队-整页", { fullPage: true });

// 切筛选：仅【阿哈时刻】
await cdp.eval(`(() => { document.querySelector('.aha-filter-btn[data-filter="aha"]')?.click(); return true; })()`);
await sleep(400);
const filtered = await cdp.eval("document.querySelectorAll('#aha-timeline-list .aha-ev-row').length");
check("筛选「仅【阿哈时刻】」有结果", filtered > 0, `rows=${filtered}`);
await cdp.eval(`(() => { document.querySelector('.aha-filter-btn[data-filter="all"]')?.click(); return true; })()`);
await sleep(300);

// 切换预设：三赌牌局
await cdp.eval(`(() => { document.querySelectorAll('.aha-preset-btn')[1]?.click(); return true; })()`);
await waitFor("document.querySelector('.aha-preset-desc') && document.querySelector('.aha-preset-desc').textContent.includes('三赌牌局')", { tries: 20 });
const sandu = await cdp.json(`(() => {
  const mech = [...document.querySelectorAll('.aha-mech-box')].map(b => b.textContent).join(' ');
  const sum = document.querySelector('#aha-summary-box')?.textContent.replace(/\\s+/g,' ') || '';
  return { mech: mech.includes('三赌牌局'), sum: sum.includes('三赌牌局') || mech.includes('全队速度'), text: sum.slice(0, 120) };
})()`);
check("预设切到「三赌牌局」后机制看板提到三赌牌局/全队提速", sandu.mech && sandu.sum, sandu.text);
await cdp.shot("05-三赌牌局预设");

// 切换原版模式
await cdp.eval(`(() => { document.querySelector('.aha-mode-btn[data-mode="original"]')?.click(); return true; })()`);
const iframeOk = await waitFor("document.querySelector('.aha-original-frame')", { tries: 30 });
check("可切回「原版静态工具」模式（iframe 存在）", iframeOk);
await sleep(2000);
const iframeInfo = await cdp.json(`(() => {
  const f = document.querySelector('.aha-original-frame');
  if (!f) return { exists: false };
  let title = '';
  try { title = (f.contentDocument?.title || '').slice(0, 60); } catch (e) { title = 'cross-origin'; }
  return { exists: true, title };
})()`);
check("原版 iframe 内容加载（标题含「阿哈时刻」）", /阿哈时刻/.test(iframeInfo.title || ""), JSON.stringify(iframeInfo));
await cdp.shot("06-原版模式");
// 切回模拟器
await cdp.eval(`(() => { document.querySelector('.aha-mode-btn[data-mode="simulator"]')?.click(); return true; })()`);
await waitFor("document.querySelector('.aha-sim-wrap')", { tries: 20 });

/* ==================== 二、行动值排轴（action-value/timeline） ==================== */

console.log(`\n[2] 行动值排轴：${BASE}/#/action-value/timeline`);
// 注意：只改 hash 不会重载页面（外壳只在启动时读一次 hash），所以带个查询参数强制整页导航
await cdp.send("Page.navigate", { url: `${BASE}/?r=2#/action-value/timeline` });
const avMounted = await waitFor("document.querySelector('.av-wrap')", { label: "av-wrap" });
check("行动值排轴界面挂载（.av-wrap）", avMounted);
await waitFor("/\\d/.test(document.querySelector('#av-out')?.textContent || '')", { label: "首屏出数" });

const avTop = await cdp.json(`(() => {
  const chips = [...document.querySelectorAll('#av-out .av-chip')].map(c => c.textContent.replace(/\\s+/g,' '));
  const sel = document.querySelector('#av-char');
  return { chips, charValue: sel ? sel.value : null, charCount: sel ? sel.options.length : 0 };
})()`);
console.log("  顶部摘要：", avTop.chips.join(" | "));
check("默认角色为爻光 1502", avTop.charValue === "1502");
check("角色下拉含 87+ 名（含特殊能量分组）", avTop.charCount >= 87, `options=${avTop.charCount}`);
check("速度拆解：基础白值 101", avTop.chips.some((c) => /基础白值\s*101/.test(c)), avTop.chips.join("|").slice(0, 160));
check("速度拆解：行迹速度 +9.0（百分比外）", avTop.chips.some((c) => /行迹速度\s*\+9(\.0)?/.test(c)), "");
check("最终速度 = 101×1.18+25+9 = 153.18", avTop.chips.some((c) => /153\.18/.test(c)), "");

// 速度方案页签：第一行 速度鞋 = 135.00
await cdp.eval(`(() => { document.querySelector('.av-tab[data-tab="compare"]')?.click(); return true; })()`);
await waitFor("document.querySelector('#av-out table tbody tr')", { tries: 30 });
const cmp = await cdp.json(`(() => {
  const rows = [...document.querySelectorAll('#av-out table tbody tr')].map(r =>
    [...r.querySelectorAll('td')].map(td => td.textContent.trim()));
  return { rows: rows.slice(0, 3) };
})()`);
console.log("  速度方案：", JSON.stringify(cmp.rows));
check("速度方案第一行「速度鞋」= 135.00", cmp.rows[0] && cmp.rows[0][0].includes("速度鞋") && cmp.rows[0][3] === "135.00", JSON.stringify(cmp.rows[0]));
check("速度方案第二行「速度鞋 + 18%」= 153.18", cmp.rows[1] && cmp.rows[1][3] === "153.18", JSON.stringify(cmp.rows[1]));
await cdp.shot("07-速度方案");

// 回能曲线页签：流萤战技固定 144（不吃 ERR）
await cdp.eval(`(() => { document.querySelector('.av-tab[data-tab="energy"]')?.click(); return true; })()`);
await waitFor("document.querySelector('#av-rotation')", { tries: 30 });
await cdp.eval(`(() => {
  const sel = document.querySelector('#av-char');
  sel.value = '1310';
  sel.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
})()`);
await waitFor("(document.querySelector('#av-out')?.textContent || '').includes('144')", { tries: 40 });
const firefly = await cdp.json(`(() => {
  const text = document.querySelector('#av-out').textContent.replace(/\\s+/g, ' ');
  const fixedTag = [...document.querySelectorAll('#av-out .av-src.is-fixed')].map(e => e.textContent.trim());
  return { has144: text.includes('144'), fixedTag, hasFixed: text.includes('固定能量（不吃 ERR）'), note: text.slice(0, 200) };
})()`);
check("流萤战技 = 144 且标为「固定能量（不吃 ERR）」", firefly.has144 && firefly.hasFixed, JSON.stringify(firefly.fixedTag));
await cdp.shot("08-回能曲线-流萤");

// 隔离角色护栏：黄泉
await cdp.eval(`(() => {
  const sel = document.querySelector('#av-char');
  sel.value = '1308';
  sel.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
})()`);
await waitFor("(document.querySelector('#av-out')?.textContent || '').includes('不适用')", { tries: 40 });
const excluded = await cdp.eval("document.querySelector('#av-out').textContent.replace(/\\s+/g,' ').slice(0, 160)");
check("隔离角色（黄泉）提示「这套回能公式不适用」", /这套回能公式不适用/.test(excluded), excluded.slice(0, 100));
await cdp.shot("09-隔离角色提示");

// 爻光机制页签：结界 3,2,1,0
await cdp.eval(`(() => {
  const sel = document.querySelector('#av-char');
  sel.value = '1502';
  sel.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
})()`);
await sleep(800);
await cdp.eval(`(() => { document.querySelector('.av-tab[data-tab="kit"]')?.click(); return true; })()`);
await waitFor("document.querySelector('.av-kit')", { tries: 30 });
const kit = await cdp.json(`(() => {
  const rows = [...document.querySelectorAll('#av-out table tbody tr')].map(r => {
    const tds = [...r.querySelectorAll('td')];
    return { field: tds[4] ? tds[4].textContent.trim() : '' };
  });
  return { fieldLeft: rows.slice(0, 5).map(r => r.field) };
})()`);
console.log("  结界剩余列：", kit.fieldLeft.join(","));
check("爻光结界覆盖自己 3 次正常行动（剩余 3,2,1,0…）", kit.fieldLeft.slice(0, 4).join(",") === "3,2,1,0", kit.fieldLeft.join(","));
await cdp.shot("10-爻光机制");

// 行动轴页签回到默认，整页截图
await cdp.eval(`(() => { document.querySelector('.av-tab[data-tab="timeline"]')?.click(); return true; })()`);
await sleep(600);
await cdp.shot("11-行动轴");

/* ==================== 三、单文件网页版（离线） ==================== */

const standaloneHtml = process.argv[5];
if (standaloneHtml) {
  const { pathToFileURL } = await import("node:url");
  console.log(`\n[3] 单文件网页版离线挂载：${standaloneHtml}`);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", {
    offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0,
  });
  await cdp.send("Page.navigate", { url: pathToFileURL(standaloneHtml).href });
  await waitFor("Boolean(window.GT_SELFTEST)", { label: "页面自检" });
  check("网页版自检通过（配速查询内核）", (await cdp.eval("window.GT_SELFTEST && window.GT_SELFTEST.ok")) === true);

  await waitFor(`document.querySelector('.gt-tab[data-view="view-aha"]')`, { label: "欢愉队页签" });
  await cdp.eval(`(() => { document.querySelector('.gt-tab[data-view="view-aha"]').click(); return true; })()`);
  const ahaMountedOffline = await waitFor("window.GT_AHA_MOUNTED === true", { tries: 40, label: "欢愉队界面挂载" });
  check("切到「欢愉队配速」页签后模拟器挂载（GT_AHA_MOUNTED）", ahaMountedOffline);

  await waitFor(
    `document.querySelector('#aha-summary-box') && /\\d/.test(document.querySelector('#aha-summary-box').textContent)`,
    { tries: 40 },
  );
  const offlineSummary = await cdp.json(`(() => {
    const box = document.querySelector('#aha-summary-box');
    const text = box ? box.textContent.replace(/\\s+/g, ' ') : '';
    const match = text.match(/有效速度[^0-9]*([0-9]+\\.?[0-9]*)/);
    return {
      speed: match ? Number(match[1]) : null,
      cards: document.querySelectorAll('.aha-unit-card').length,
      events: document.querySelectorAll('#aha-timeline-list .aha-ev-row').length,
    };
  })()`);
  check("网页版算出【阿哈时刻】速度（> 100）", offlineSummary.speed !== null && offlineSummary.speed > 100, `speed=${offlineSummary.speed}`);
  check(
    "网页版 4 张角色卡 + 时间线事件 > 40",
    offlineSummary.cards === 4 && offlineSummary.events > 40,
    JSON.stringify({ cards: offlineSummary.cards, events: offlineSummary.events }),
  );
  await cdp.shot("12-网页版离线-欢愉队");
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1,
  });
}

/* ==================== 汇总 ==================== */
ws.close();
const failed = checks.filter((c) => !c.ok);
console.log(`\n=== 界面验收：${checks.length - failed.length}/${checks.length} 通过 ===`);
if (failed.length) {
  console.log("失败项：");
  for (const f of failed) console.log(`  [X] ${f.name}  ${f.detail}`);
  process.exit(1);
}
console.log(`全部通过，截图在 ${outDir}/`);
