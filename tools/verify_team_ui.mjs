/** 队伍存档与头像时间轴验收。只连接本任务独立浏览器的 about:blank 页面。
 * node tools\verify_team_ui.mjs <隔离服务端口> <隔离CDP端口> <截图目录> [离线HTML]
 * 服务必须使用临时 GT_USERDATA；本脚本会保存测试角色/队伍后清理。
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [port = '8961', debug = '9437', out = 'tools/.cache/team-shots', offline] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const base = `http://127.0.0.1:${port}`;
const targets = await (await fetch(`http://127.0.0.1:${debug}/json/list`)).json();
const target = targets.find(t => t.type === 'page' && (t.url === 'about:blank' || t.url.startsWith(base) || (offline && t.url.startsWith('file:'))));
if (!target) throw Error('请启动独立临时浏览器并打开 about:blank。');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
let id = 0;
const pending = new Map();
ws.onmessage = event => {
  const msg = JSON.parse(event.data), p = pending.get(msg.id);
  if (!p) return;
  pending.delete(msg.id); msg.error ? p.reject(Error(JSON.stringify(msg.error))) : p.resolve(msg.result);
};
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const key = ++id; pending.set(key, { resolve, reject }); ws.send(JSON.stringify({ id: key, method, params }));
    const timer = setTimeout(() => { if (pending.delete(key)) reject(Error(`${method} timeout`)); }, 15000); timer.unref();
  });
}
async function evaluate(expression) {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function wait(expression) {
  for (let i = 0; i < 80; i++) { if (await evaluate(expression)) return; await sleep(150); }
  throw Error(`等待失败: ${expression}`);
}
let checks = 0;
function check(name, ok) { if (!ok) throw Error(`[X] ${name}`); checks++; console.log(`[OK] ${name}`); }
async function shot(name) { await sleep(250); const r = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(join(out, `${name}.png`), Buffer.from(r.data, 'base64')); }
async function api(feature, action, payload = {}) {
  const r = await (await fetch(`${base}/api/call`, { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: base }, body: JSON.stringify({ module: 'honkai-star-rail', feature, action, payload }) })).json();
  if (!r.ok) throw Error(JSON.stringify(r)); return r.result;
}
await send('Page.enable');
await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1080, deviceScaleFactor: 1, mobile: false });
await send('Page.addScriptToEvaluateOnNewDocument', { source: `window.__errors=[]; window.__simCalls=0; window.addEventListener('error', e=>window.__errors.push(e.message)); const oldFetch=window.fetch; window.fetch=async (...args)=>{let sim=false,slow=false;try { const p=JSON.parse(args[1]?.body||'{}'); sim=p.feature==='aha-speed'&&p.action==='simulate'; if(sim){window.__simCalls++;slow=!!window.__delayNextSim;window.__delayNextSim=false;} } catch {} const r=await oldFetch(...args); if(slow)await new Promise(resolve=>setTimeout(resolve,700)); try { const p=JSON.parse(args[1]?.body||'{}'); if(sim){const data=await r.clone().json(); if(data.ok){window.__sim=data.result;window.__payload=p.payload;if(slow)window.__slowSimDone=true;else window.__fastSim=data.result;}} }catch{} return r;};` });
let savedTeam;
const original = (await api('speed-plan', 'presets')).presets['1502'];
const originalPearl = (await api('speed-plan', 'presets')).presets['1503'];
try {
  await send('Page.navigate', { url: `${base}/#/honkai-star-rail/speed-plan` });
  await wait("document.querySelector('#save-preset') && document.querySelector('#hero-current')?.textContent !== '—'");
  await evaluate(`document.querySelector('[data-char="1502"]').click()`);
  await wait(`document.querySelector('[data-char="1502"]').getAttribute('aria-selected')==='true'`);
  await evaluate(`for(const [id,value] of [['eidolon','0'],['superimpose','1']]){const el=document.querySelector('#'+id);el.value=value;el.dispatchEvent(new Event('change',{bubbles:true}));}document.querySelector('#preset-err').value='19.4'; document.querySelector('#preset-energy').value='80'; document.querySelector('#preset-rotation').value='basic'; document.querySelector('#save-preset').click()`);
  await wait("document.querySelector('#preset-note').textContent.includes('已保存')");
  const config = (await api('speed-plan', 'presets')).presets['1502'].config;
  check('角色配装保存模拟补充参数', config.aha.err === 19.4 && config.aha.initialEnergy === '80' && config.aha.rotation === 'basic');
  await evaluate(`document.querySelector('#preset-err').value='1';document.querySelector('#apply-preset').click()`);
  check('重新套用恢复模拟补充参数', await evaluate("document.querySelector('#preset-err').value==='19.4'"));
  const expected = await api('speed-plan', 'plan', { ...config, characterId: '1502' });
  await api('speed-plan', 'save_preset', { characterId: '1503', config: { ...config, lightconeId: '' } });
  await send('Page.navigate', { url: `${base}/?teamtest=1#/honkai-star-rail/aha-speed` });
  await wait("document.querySelectorAll('.aha-unit-card').length===4 && window.__sim");
  check('队伍页面显式声明侧栏布局', await evaluate("document.querySelector('#app').dataset.sidebarLayout === 'compact-tight'"));
  await evaluate("document.querySelector('.aha-unit-card.is-open .aha-unit-toggle').click()");
  await evaluate("document.querySelector('.aha-unit-card:not(.is-open) .aha-unit-toggle').click()");
  await wait("!!document.querySelector('.aha-unit-card.is-open .unit-num')");
  const countBeforeBurst = await evaluate("window.__simCalls");
  const originalInput = await evaluate("document.querySelector('.aha-unit-card.is-open .unit-num').value");
  await evaluate("(()=>{const i=document.querySelector('.aha-unit-card.is-open .unit-num');for(const v of ['101','102','103']){i.value=v;i.dispatchEvent(new Event('input',{bubbles:true}));}})()");
  await sleep(500);
  check('连续输入只触发一次模拟', await evaluate(`window.__simCalls === ${countBeforeBurst + 1}`));
  await evaluate("window.__delayNextSim=true;window.__slowSimDone=false;window.__fastSim=null;(()=>{const i=document.querySelector('.aha-unit-card.is-open .unit-num');i.value='110';i.dispatchEvent(new Event('input',{bubbles:true}));})()");
  await sleep(250);
  await evaluate("(()=>{const i=document.querySelector('.aha-unit-card.is-open .unit-num');i.value='120';i.dispatchEvent(new Event('input',{bubbles:true}));})()");
  check('等待新结果时不展示旧摘要', await evaluate("document.querySelector('#aha-summary-box').textContent === '计算中…'"));
  await wait('window.__slowSimDone && window.__fastSim');
  check('延迟旧请求不会覆盖新结果', await evaluate("document.querySelector('#unit-metrics-0').textContent.includes(Number(window.__fastSim.units[0].initialSpd).toFixed(1))"));
  await evaluate(`(()=>{const i=document.querySelector('.aha-unit-card.is-open .unit-num');i.value=${JSON.stringify(originalInput)};i.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await sleep(500);
  check('左侧角色、右侧模拟分区', await evaluate("!!document.querySelector('.aha-col-left #aha-team-list') && !!document.querySelector('.aha-col:not(.aha-col-left) #aha-timeline-list')"));
  check('角色卡展开使用动画，收起时内部不可操作', await evaluate("(()=>{const card=document.querySelectorAll('.aha-unit-card')[1], body=card.querySelector('.aha-unit-body');return body.inert && getComputedStyle(body).transitionProperty.includes('grid-template-rows');})()"));
  await evaluate("document.querySelector('.unit-char-select').dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true}))");
  check('角色下拉显示统一菜单', await evaluate("!!document.querySelector('.gt-select-menu [role=option]')"));
  await evaluate("document.querySelector('.gt-select-menu [aria-selected=true]').click()");
  check('选择后菜单关闭', await evaluate("!document.querySelector('.gt-select-menu')"));
  check('队伍与配装位于我的队伍之前', await evaluate("!!(document.querySelector('#aha-team-list').closest('.aha-card').compareDocumentPosition(document.querySelector('#aha-library')) & Node.DOCUMENT_POSITION_FOLLOWING)"));
  check('配装列表只显示当前角色，即使其他角色也有存档', await evaluate(`[...document.querySelectorAll('.unit-build')].every(select=>[...select.options].filter(o=>o.value).every(o=>o.value===document.querySelector('.unit-char-select[data-slot="'+select.dataset.slot+'"]').value))`));
  check('无配装角色的读取按钮禁用', await evaluate(`document.querySelector('.unit-apply-build[data-slot="0"]').disabled`));
  await evaluate(`const s=document.querySelector('.unit-build[data-slot="3"]');s.add(new Option('真珠','1503'));s.value='1503';document.querySelector('.unit-apply-build[data-slot="3"]').click()`);
  check('跨角色读取被拒绝且不会偷偷换人', await evaluate(`document.querySelector('#aha-library-note').textContent.includes('只能读取当前角色') && document.querySelector('.unit-char-select[data-slot="3"]').value==='1502'`));
  await evaluate(`window.__sim=null;window.__payload=null;document.querySelector('.unit-build[data-slot="3"]').value='1502';document.querySelector('.unit-apply-build[data-slot="3"]').click()`);
  await wait("document.querySelectorAll('.aha-build-source').length===1 && window.__payload?.team[3].initialEnergy==='80'");
  check('导入 S0 与配速接口计算一致', await evaluate(`Math.abs(window.__sim.units[3].initialSpd-${expected.speed.final})<1e-8`));
  check('装备充能仅叠加一次', await evaluate("Math.abs(window.__sim.units[3].err - (19.4 + (window.__payload.team[3].equipment.vonwacq?5:0) + (window.__payload.team[3].equipment.hasYaoLc?12:0)))<1e-8"));
  const e2Config = { ...config, eidolon: 2 };
  const e2Plan = await api('speed-plan', 'plan', { ...e2Config, characterId: '1502' });
  const managed = e2Plan.effects.speed.filter(e=>e.origin==='角色·星魂'&&e.rank===2&&e.apply==='team'&&e.kind==='pct'&&e2Plan.effects.enabled.includes(e.id)).reduce((n,e)=>n+e.value,0);
  check('二魂导入场景包含已勾选的结界速度效果', managed === 12);
  await api('speed-plan','save_preset',{characterId:'1502',config:e2Config});
  await evaluate(`document.querySelector('#aha-refresh-library').click()`);
  await wait(`document.querySelector('#aha-library-note').textContent.includes('存档已刷新')`);
  await evaluate(`window.__sim=null;window.__payload=null;document.querySelector('.unit-build[data-slot="3"]').value='1502';document.querySelector('.unit-apply-build[data-slot="3"]').click()`);
  await wait(`window.__payload?.team[3].eidolon===2`);
  const baseline = e2Plan.speed.final - e2Plan.speed.base * 0.12;
  check('二魂条件速度没有固化到常驻配装', await evaluate(`(()=>{const u=window.__payload.team[3];const speed=(u.baseSpd+u.lcBaseSpd)*(1+(u.permPct+(u.equipment.godJoy?6:0))/100)+u.permFlat+u.traceSpd;return Math.abs(speed-${baseline})<1e-8})()`));
  check('二魂结界开局仅由引擎叠加一次', await evaluate(`Math.abs(window.__sim.units[3].initialSpd-(${baseline}+window.__payload.team[3].baseSpd*0.12))<1e-8`));
  await evaluate(`document.querySelector('#aha-team-name').value='UI验收队伍';document.querySelector('#aha-save-team').click()`);
  await wait("document.querySelector('#aha-library-note').textContent==='队伍已保存。'");
  savedTeam = await evaluate("document.querySelector('#aha-saved-team').value");
  const snapshot = (await api('aha-speed', 'library')).teams[savedTeam];
  check('队伍保存完整角色参数', snapshot.team[3].initialEnergy === '80' && snapshot.team[3].rotation === 'basic');
  await evaluate(`document.querySelectorAll('.aha-preset-btn')[3].click();`);
  await wait("document.querySelector('.unit-char-select').value==='1506'");
  await evaluate(`const sel=document.querySelector('#aha-saved-team');sel.value=${JSON.stringify(savedTeam)};sel.dispatchEvent(new Event('change'));document.querySelector('#aha-load-team').click()`);
  await wait("window.__payload.team[3].initialEnergy==='80' && document.querySelector('.unit-char-select').value==='1511'");
  await wait(`JSON.stringify(window.__payload.team)===${JSON.stringify(JSON.stringify(snapshot.team))}`);
  check('队伍加载恢复精确参数', await evaluate(`JSON.stringify(window.__payload.team)===${JSON.stringify(JSON.stringify(snapshot.team))}`));
  await evaluate(`document.querySelector('#aha-team-name').value='欢愉队 · 配装试算';document.querySelector('#aha-overwrite-team').click()`);
  await wait("document.querySelector('#aha-saved-team').selectedOptions[0].textContent==='欢愉队 · 配装试算'");
  check('覆盖已有队伍', (await api('aha-speed', 'library')).teams[savedTeam].name === '欢愉队 · 配装试算');
  await evaluate(`document.querySelector('[data-filter="all"]').click()`);
  const integrity = await evaluate(`(()=>{const events=window.__sim.timeline;const rows=[...document.querySelectorAll('.aha-ev-row')];return rows.length===events.length && rows.every((r,i)=>Number(r.dataset.eventIndex)===i+1&&Math.abs(Number(r.dataset.av)-events[i].av)<1e-9&&r.textContent.includes(events[i].label));})()`);
  check('每条时间轴的序号、AV、说明与引擎事件逐条一致', integrity);
  await evaluate("document.querySelector('#aha-team-list').scrollIntoView()");
  await wait("[...document.querySelectorAll('.aha-unit-identity img')].every(i=>i.complete&&i.naturalWidth>0)");
  check('已有头像复用本地资源，缺图角色显示占位', await evaluate("document.querySelectorAll('.aha-unit-identity .aha-avatar').length===4 && document.querySelectorAll('.aha-unit-identity img').length>=3"));
  await evaluate("document.querySelector('.aha-ev-row summary').click()");
  check('事件可展开查看详细数据', await evaluate("document.querySelector('.aha-ev-row').open && !!document.querySelector('.aha-ev-details .aha-ev-chip')"));
  await evaluate(`document.querySelector('[data-filter="actions"]').click();document.querySelector('.aha-ev-row summary').click()`);
  await shot('desktop');
  for (const width of [1100, 820, 390]) {
    await send('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false });
    await sleep(200);
    check(`${width}px 页面完整呈现且无横向裁切`, await evaluate(`(()=>{const r=document.querySelector('.aha-sim-wrap').getBoundingClientRect();const view=document.querySelector('.view');return r.left>=0&&r.right<=innerWidth+1&&(!view||view.scrollWidth<=view.clientWidth+1);})()`));
    await shot(`width-${width}`);
  }
  await evaluate("document.querySelector('#aha-delete-team').click();document.querySelector('.gt-dialog-primary').click()");
  await wait("document.querySelector('#aha-library-note').textContent.includes('已删除')");
  check('删除队伍不影响角色配装', !!(await api('speed-plan', 'presets')).presets['1502']);
  savedTeam = null;
  check('无页面脚本错误', await evaluate('window.__errors.length===0'));
  if (offline) {
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1080, deviceScaleFactor: 1, mobile: false });
    await send('Network.enable');
    await send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 });
    await send('Page.navigate', { url: pathToFileURL(resolve(offline)).href });
    await wait("document.querySelector('#save-preset')");
    await evaluate("document.querySelector('[data-char=\"1502\"]').click()");
    await sleep(300);
    await evaluate("document.querySelector('#save-preset').click()");
    await wait("document.querySelector('#preset-note').textContent.includes('已保存')");
    await evaluate("document.querySelector('#open-team-simulator').click()");
    await wait("document.querySelectorAll('.aha-unit-card').length===4 && document.querySelector('.aha-ev-row')");
    await evaluate("document.querySelector('.unit-build[data-slot=\"3\"]').value='1502';document.querySelector('.unit-apply-build[data-slot=\"3\"]').click()");
    await wait("document.querySelector('.aha-build-source')");
    check('离线版可共享角色存档并模拟', await evaluate("!document.querySelector('#aha-library-note').classList.contains('is-error')"));
    await evaluate("document.querySelector('#aha-team-name').value='离线验收';document.querySelector('#aha-save-team').click()");
    await wait("document.querySelector('#aha-library-note').textContent==='队伍已保存。'");
    check('离线队伍写入 localStorage', await evaluate("Object.values(JSON.parse(localStorage.getItem('gt-aha-teams'))).some(t=>t.name==='离线验收')"));
    await evaluate("document.querySelector('#aha-team-list').scrollIntoView()");
    await wait("document.querySelectorAll('.aha-unit-identity img').length>=3 && [...document.querySelectorAll('.aha-unit-identity img')].every(i=>i.complete&&i.naturalWidth>0)");
    check('离线头像已内联且可显示', await evaluate("[...document.querySelectorAll('.aha-unit-identity img')].length>=3 && [...document.querySelectorAll('.aha-unit-identity img')].every(i=>i.src.startsWith('data:')&&i.naturalWidth>0)"));
    await evaluate("document.querySelector('#aha-team-name').value='';document.querySelector('#aha-save-team').click()");
    await wait("document.querySelector('#aha-library-note').classList.contains('is-error')");
    check('离线存档校验错误可读', await evaluate("document.querySelector('#aha-library-note').textContent.includes('队伍名称')"));
    await evaluate("document.querySelector('#aha-manage-builds').click()");
    check('离线版可返回角色配装页', await evaluate("!document.querySelector('#view').hidden"));
    await evaluate("document.querySelector('#open-team-simulator').click()");
    await shot('offline');
    await evaluate("document.querySelector('.gt-tab[data-view=\"view-herta\"]').click()");
    await wait("window.GT_HERTA_MOUNTED === true");
    check('离线版角色顶分模块成功挂载', await evaluate("!!document.querySelector('#view-herta .gt-feature-root') && !document.querySelector('#view-herta .gt-skeleton')"));
    await send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  }
  console.log(`[OK] ${checks} checks`);
} finally {
  if (savedTeam) await api('aha-speed', 'delete_team', { id: savedTeam });
  if (original) await api('speed-plan', 'save_preset', { characterId: '1502', ...original });
  else await api('speed-plan', 'delete_preset', { characterId: '1502' });
  if (originalPearl) await api('speed-plan', 'save_preset', { characterId: '1503', ...originalPearl });
  else await api('speed-plan', 'delete_preset', { characterId: '1503' });
  ws.close();
}
