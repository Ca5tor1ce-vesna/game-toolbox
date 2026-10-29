/** 侧栏交互验收；需独立服务与空白浏览器，服务使用临时 GT_USERDATA。 */
const [port = '8960', debug = '9437'] = process.argv.slice(2);
const base = `http://127.0.0.1:${port}`;
const targets = await (await fetch(`http://127.0.0.1:${debug}/json/list`)).json();
const target = targets.find(t => t.type === 'page' && (t.url === 'about:blank' || t.url.startsWith(base)));
if (!target) throw Error('请先启动隔离浏览器的空白页');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
let id = 0; const pending = new Map();
ws.onmessage = event => { const message = JSON.parse(event.data), p = pending.get(message.id); if (!p) return; pending.delete(message.id); message.error ? p.reject(Error(JSON.stringify(message.error))) : p.resolve(message.result); };
function send(method, params = {}) { return new Promise((resolve, reject) => { pending.set(++id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); }); }
async function evaluate(expression) { const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.text); return r.result.value; }
async function wait(expression) { for (let i = 0; i < 60; i++) { if (await evaluate(expression)) return; await new Promise(r => setTimeout(r, 150)); } throw Error('等待失败: ' + expression); }
function check(label, value) { if (!value) throw Error('[X] ' + label); console.log('[OK] ' + label); }
try {
  await send('Page.enable'); await send('Runtime.enable');
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `(() => {
    const active = new Map(), add = document.addEventListener.bind(document), remove = document.removeEventListener.bind(document);
    window.__documentListeners = active;
    document.addEventListener = (type, fn, options) => { if (!active.has(type)) active.set(type, new Set()); active.get(type).add(fn); return add(type, fn, options); };
    document.removeEventListener = (type, fn, options) => { active.get(type)?.delete(fn); return remove(type, fn, options); };
  })();` });
  await send('Page.navigate', { url: `${base}/` });
  await wait("document.querySelectorAll('.nav-feature').length > 0");
  check('欢迎页和侧栏显示三位代码贡献者', await evaluate("['.home-credits', '.sidebar-credits'].every(s => { const e = document.querySelector(s); return e && e.querySelectorAll('a').length === 3 && !e.textContent.includes('Yukiookami'); })"));
  check('默认侧栏展开', await evaluate("!!document.querySelector('#sidebar-toggle') && document.querySelector('#sidebar-toggle').getAttribute('aria-expanded') === 'true'"));
  await evaluate("document.querySelector('#sidebar-toggle').click()");
  check('侧栏收起', await evaluate("document.querySelector('#app').classList.contains('sidebar-is-collapsed')"));
  await evaluate("document.querySelector('.nav-feature').dispatchEvent(new MouseEvent('mouseover',{bubbles:true}))");
  check('悬停显示对应名称', await evaluate("!document.querySelector('#sidebar-tip').hidden && document.querySelector('#sidebar-tip').textContent === document.querySelector('.nav-feature .name').textContent"));
  await evaluate("document.querySelector('.nav-feature[data-feature=\"speed-plan\"]').click()");
  await wait("!!document.querySelector('#view .sp')");
  check('收起时图标可跳转', await evaluate("!!document.querySelector('#view .sp')"));
  check('光锥与遗器位于角色卡内', await evaluate("['#lightcone-picker','#fourPiece-picker','#ornamentA-picker'].every(s=>document.querySelector('[data-step=char] '+s))"));
  check('计算目标位于结果栏上方', await evaluate("!!document.querySelector('.sp-right [data-step=target]')"));
  check('角色选择弹窗入口', await evaluate("!!document.querySelector('#select-character') && !!document.querySelector('#character-dialog')"));
  await evaluate(`window.__designPlan = null; const originalFetch = window.fetch; window.fetch = async (...args) => { const response = await originalFetch(...args); try { const body = JSON.parse(args[1]?.body || '{}'); if (body.feature === 'speed-plan' && body.action === 'plan' && body.payload?.characterId === '1502') { const data = await response.clone().json(); window.__designPlan = data.result?.verdict?.currentSpeed ?? data.verdict?.currentSpeed ?? null; } } catch {} return response; };`);
  await evaluate("document.querySelector('#select-character').click()");
  check('角色弹窗打开', await evaluate("document.querySelector('#character-dialog').open"));
  check('角色选择头像清晰显示并使用圆角', await evaluate("(()=>{const i=document.querySelector('#character-dialog [data-char=\"1502\"] img');return i && i.getAttribute('src').includes('/modules/honkai-star-rail/assets/') && getComputedStyle(i).maskImage==='none' && getComputedStyle(i).borderRadius==='12px';})()"));
  check('角色搜索框聚焦无描边', await evaluate("(()=>{const i=document.querySelector('#char-search');const p=document.querySelector('.sp-dialog-search');return document.activeElement===i && getComputedStyle(i).outlineStyle==='none' && getComputedStyle(i).boxShadow==='none' && getComputedStyle(p).boxShadow==='none';})()"));
  await evaluate("document.querySelector('#character-dialog [data-char=\"1502\"]').click()");
  await wait("!document.querySelector('#character-dialog').open");
  check('选择角色后关闭弹窗', await evaluate("!document.querySelector('#character-dialog').open"));
  await wait("document.querySelector('#splash-meta')?.textContent.includes('爻光')");
  await wait("window.__designPlan !== null && document.querySelector('#hero-current').textContent === Number(window.__designPlan).toFixed(1)");
  check('选择角色后更新立绘与结果', await evaluate("document.querySelector('#splash').getAttribute('src') && document.querySelector('#hero-current').textContent !== '—'"));
  const before = await evaluate("document.querySelector('#hero-current').textContent");
  const start = Number(await evaluate("document.querySelector('#substat').value"));
  await evaluate("document.querySelector('[data-step-for=substat][data-dir=\"1\"]').click()");
  await wait(`Number(document.querySelector('#substat').value)===${start + 1} && document.querySelector('#hero-current').textContent!==${JSON.stringify(before)}`);
  check('数字框加减会更新输入与结果', true);
  await evaluate("document.querySelector('[data-step-for=substat][data-dir=\"-1\"]').click()");
  await wait(`document.querySelector('#hero-current').textContent===${JSON.stringify(before)}`);
  check('减回原值后结果复原', true);
  await evaluate("document.querySelector('#select-character').click(); document.querySelector('#character-dialog [data-char=\"1503\"]').click()");
  await wait("document.querySelector('.sp').dataset.theme==='pearl'");
  check('真珠使用珍珠配色，侧栏仍为粉色', await evaluate("getComputedStyle(document.querySelector('.sp')).getPropertyValue('--accent').trim()==='#54788f' && getComputedStyle(document.querySelector('#sidebar')).getPropertyValue('--accent').trim()!=='#54788f'"));
  await evaluate("document.querySelector('#select-character').click(); document.querySelector('#character-dialog [data-char=\"1502\"]').click()");
  await wait("document.querySelector('.sp').dataset.theme==='teal'");
  check('爻光使用青蓝配色', true);
  await evaluate("document.querySelector('#sidebar-toggle').click()");
  check('可重新展开', await evaluate("!document.querySelector('#app').classList.contains('sidebar-is-collapsed')"));
  await evaluate("document.querySelector('#home-button').click()");
  await wait("!!document.querySelector('.welcome')");
  const beforeListeners = await evaluate("['click','keydown'].map(type=>window.__documentListeners.get(type)?.size || 0)");
  for (let i = 0; i < 3; i++) {
    await evaluate("document.querySelector('.nav-feature[data-feature=\"speed-plan\"]').click()");
    await wait("document.querySelector('#hero-current')?.textContent !== '—' && !document.querySelector('.gt-feature-root.is-loading')");
    await evaluate("document.querySelector('#home-button').click()");
    await wait("!!document.querySelector('.welcome')");
  }
  check('反复切换后页面监听不会累积', await evaluate(`JSON.stringify(['click','keydown'].map(type=>window.__documentListeners.get(type)?.size || 0)) === ${JSON.stringify(JSON.stringify(beforeListeners))}`));
  await evaluate("document.querySelector('.nav-feature[data-feature=\"gacha\"]').click()");
  await wait("!!document.querySelector('.gacha-layout') && !document.querySelector('.gt-feature-root.is-loading')");
  check('抽卡页面显式声明侧栏布局', await evaluate("document.querySelector('#app').dataset.sidebarLayout === 'compact'"));
  for (const width of [1100, 820, 390]) {
    await send('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false });
    await new Promise(r => setTimeout(r, 200));
    check(`${width}px 抽卡页面布局无横向裁切`, await evaluate("(()=>{const r=document.querySelector('.gacha-layout').getBoundingClientRect();const view=document.querySelector('.view');return r.left>=0 && r.right<=innerWidth+1 && view.scrollWidth<=view.clientWidth+1;})()"));
  }
  await evaluate("document.querySelector('#home-button').click()");
  check('离开页面清理布局声明', await evaluate("!document.querySelector('#app').dataset.sidebarLayout"));
} finally { ws.close(); }
