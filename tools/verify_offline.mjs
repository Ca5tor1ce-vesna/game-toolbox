/**
 * 离线验证：把单文件网页版当成本地文件打开，**并把浏览器彻底断网**，
 * 然后检查图标/立绘是不是仍然画出来了。
 *
 * 用法：<node> tools/verify_offline.mjs [html 路径] [调试端口]
 *   <node> tools/verify_offline.mjs dist\配速查询-网页版.html 9223
 *   需要先起 Edge：--headless=new --remote-debugging-port=9223 --user-data-dir=<临时目录>
 *
 * 断网方式是 CDP 的 `Network.emulateNetworkConditions {offline: true}` ——
 * 这是浏览器内核级的断网，任何 http(s) 请求都会失败，比"拔网线"更可控。
 * 所以只要图片还在，就证明它们**不是**从网上取的。
 *
 * 对 0.17.2 的适配：
 *   - 单文件网页版仍然暴露 `window.GT_SELFTEST / GT_MOUNTED`、容器仍是 `#view`；
 *   - 下拉浮层从 `.picker-panel` 改名 `.picker-popup`，
 *     而且它是**挂载时就创建**的（不点按钮也存在），所以这里直接把浮层点开再查图标。
 *
 * 退出码：0 = 离线可用；1 = 断言不过；2 = 找不到 HTML。
 */

import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { resolve, join } from "node:path";

const htmlPath = resolve(process.argv[2] || "dist/配速查询-网页版.html");
const debugPort = Number(process.argv[3] || 9223);

if (!existsSync(htmlPath)) {
  console.error(`找不到 ${htmlPath}`);
  process.exit(2);
}

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

const target = await firstPageTarget();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res, rej) => {
  ws.addEventListener("open", res);
  ws.addEventListener("error", rej);
});

let id = 0;
const pending = new Map();
const requested = [];
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.method === "Network.requestWillBeSent") {
    requested.push(msg.params.request.url);
  }
  const slot = pending.get(msg.id);
  if (!slot) return;
  pending.delete(msg.id);
  if (msg.error) slot.reject(new Error(JSON.stringify(msg.error)));
  else slot.resolve(msg.result);
});
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const i = (id += 1);
    pending.set(i, { resolve, reject });
    ws.send(JSON.stringify({ id: i, method, params }));
    setTimeout(() => {
      if (pending.has(i)) {
        pending.delete(i);
        reject(new Error(`${method} 超时`));
      }
    }, 30000);
  });
const ev = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) {
    throw new Error(`页面里执行出错：${r.exceptionDetails.text} ${r.exceptionDetails.exception?.description || ""}`);
  }
  return r.result?.value;
};

/**
 * 复杂对象统一回传成 JS 对象（普通表达式先自己 stringify 一遍，
 * 因为 `returnByValue` 偶尔给 undefined）。
 *
 * 坑：**异步体不能套 `JSON.stringify`** —— 那是对 Promise 做 stringify，结果恒为
 * `{}`。所以 `(async () => {...})()` 这种表达式直接交给 `awaitPromise` 等结果。
 */
const json = async (expression) => {
  const source = expression.trim();
  if (source.startsWith("(async")) return ev(source);
  return JSON.parse(await ev(`JSON.stringify(${expression})`));
};

await send("Page.enable");
await send("Runtime.enable");
await send("Network.enable");
await send("Emulation.setDeviceMetricsOverride", {
  width: 1360, height: 1000, deviceScaleFactor: 1, mobile: false,
});

// 关键：浏览器内核级断网
await send("Network.emulateNetworkConditions", {
  offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0,
});
console.log("已把浏览器设为 offline=true（任何 http/https 请求都会失败）");

const fileUrl = pathToFileURL(htmlPath).href;
console.log(`打开本地文件 ${fileUrl}`);
await send("Page.navigate", { url: fileUrl });

for (let i = 0; i < 60; i += 1) {
  const ok = await ev("Boolean(document.querySelector('#view'))");
  if (ok) break;
  await sleep(500);
}
// 等挂载 + 页面自检（自检要跑一遍全量对拍，给足时间）
for (let i = 0; i < 40; i += 1) {
  const ready = await ev("Boolean(window.GT_MOUNTED || window.GT_SELFTEST)");
  if (ready) break;
  await sleep(500);
}
await sleep(3000);

const report = await json(`(() => {
  const imgs = [...document.querySelectorAll('img')];
  const loaded = [], remote = [], broken = [];
  let dataUris = 0, empty = 0, hidden = 0;
  for (const img of imgs) {
    const src = img.currentSrc || img.getAttribute('src') || '';
    if (!src) { empty += 1; continue; }
    if (img.style.visibility === 'hidden') { hidden += 1; continue; }
    if (src.startsWith('data:image/')) dataUris += 1;
    else if (/^https?:/.test(src)) remote.push(src.slice(0, 80));
    if (img.naturalWidth > 0 && img.naturalHeight > 0) {
      loaded.push(img.naturalWidth + 'x' + img.naturalHeight);
    } else if (img.loading !== 'lazy' && img.complete) {
      broken.push(src.slice(0, 80));
    }
  }
  const splash = document.querySelector('#splash');
  const tiles = document.querySelectorAll('.sp-char').length;
  return {
    standalone: Boolean(window.GT_STANDALONE),
    totalImgs: imgs.length,
    loadedCount: loaded.length,
    dataUriCount: dataUris,
    remoteSrc: remote,
    brokenSrc: broken,
    emptySlots: empty,
    hiddenImgs: hidden,
    charTiles: tiles,
    splash: splash ? { w: splash.naturalWidth, h: splash.naturalHeight, visibility: getComputedStyle(splash).visibility } : null,
    selfTest: window.GT_SELFTEST || null,
    mounted: Boolean(window.GT_MOUNTED),
    bodyScrollWidth: document.body.scrollWidth,
    viewport: [window.innerWidth, window.innerHeight],
    sizes: loaded.slice(0, 5),
  };
})()`);

// 把下拉浮层点开，确认浮层里的图标也是 data URI
// （异步体直接返回对象：对 Promise 做 JSON.stringify 只会得到 `{}`）
const picker = await json(`(async () => {
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  let popup = document.querySelector('.picker-popup:not(.hidden)');
  if (!popup) {
    const btn = document.querySelector('#lightcone-picker') || document.querySelector('.picker-button');
    if (btn) btn.click();
    await wait(1200);
    popup = document.querySelector('.picker-popup:not(.hidden)');
  }
  if (!popup) return { open: false };
  const items = [...popup.querySelectorAll('.picker-item img')];
  const visible = items.filter(i => i.style.visibility !== 'hidden');
  return {
    open: true,
    pickerImgs: items.length,
    pickerDataUris: visible.filter(i => (i.currentSrc || i.getAttribute('src') || '').startsWith('data:image/')).length,
    pickerRemote: visible.filter(i => /^https?:/.test(i.currentSrc || '')).length,
    pickerLoaded: visible.filter(i => i.naturalWidth > 0).length,
  };
})()`);

const { data } = await send("Page.captureScreenshot", { format: "png" });
mkdirSync("dist/shots", { recursive: true });
const shotPath = join("dist", "shots", "11-网页版离线.png");
writeFileSync(shotPath, Buffer.from(data, "base64"));

const external = requested.filter((u) => /^https?:/.test(u));
console.log("\n=== 离线验证结果 ===");
console.log(JSON.stringify(report, null, 1));
console.log("下拉浮层:", JSON.stringify(picker));
console.log(`页面请求过的 http/https 地址：${external.length} 个`, external.slice(0, 5));
console.log(`截图：${shotPath}`);

ws.close();

const checks = [
  ["单文件页面自报 standalone", report.standalone],
  ["界面挂载完成（GT_MOUNTED）", report.mounted],
  ["页面自检跑完且通过（GT_SELFTEST.ok）", Boolean(report.selfTest && report.selfTest.ok)],
  ["图片解码成功 >0", report.loadedCount > 0],
  ["图片全部来自内联 data URI（没有 http src）", report.dataUriCount > 0 && report.remoteSrc.length === 0],
  ["没有坏图", report.brokenSrc.length === 0],
  ["角色头像网格渲染出来（.sp-char）", report.charTiles > 0],
  ["整个页面没有发出任何 http/https 请求", external.length === 0],
  ["下拉浮层里的图标也是内联 data URI", picker.open && picker.pickerDataUris > 0 && picker.pickerRemote === 0],
];

let allOk = true;
for (const [name, ok] of checks) {
  console.log(`  ${ok ? "OK  " : "FAIL"} ${name}`);
  if (!ok) allOk = false;
}
if (report.selfTest && !report.selfTest.ok) {
  console.log("  自检失败项:", JSON.stringify(report.selfTest.failures?.slice(0, 5)));
}

console.log(
  allOk
    ? "\n✅ 离线可用：图片全部来自内联 data URI，且整个过程没有发出任何 http 请求"
    : "\n❌ 离线验证未通过",
);
process.exit(allOk ? 0 : 1);
