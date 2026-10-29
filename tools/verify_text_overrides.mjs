/** 文字覆盖回归。只连接本任务的隔离服务与浏览器；不修改持久化设置。 */
const [port = '8961', debug = '9437'] = process.argv.slice(2);
const base = `http://127.0.0.1:${port}`;
const targets = await (await fetch(`http://127.0.0.1:${debug}/json/list`)).json();
const target = targets.find(t => t.type === 'page' && (t.url === 'about:blank' || t.url.startsWith(base)));
if (!target) throw Error('请先启动隔离浏览器的空白页');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
let id = 0; const pending = new Map();
ws.onmessage = event => { const m = JSON.parse(event.data), p = pending.get(m.id); if (!p) return; pending.delete(m.id); m.error ? p.reject(Error(JSON.stringify(m.error))) : p.resolve(m.result); };
const send = (method, params = {}) => new Promise((resolve, reject) => { pending.set(++id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
async function evaluate(expression) { const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.text); return r.result.value; }
async function wait(expression) { for (let i = 0; i < 80; i++) { if (await evaluate(expression)) return; await new Promise(r => setTimeout(r, 100)); } throw Error(`等待失败：${expression}`); }
try {
  await send('Page.enable'); await send('Runtime.enable');
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `(() => {
    const nativeObserver = window.MutationObserver;
    window.__overrideObserverCalls = 0;
    window.MutationObserver = class extends nativeObserver {
      constructor(cb) { super((records, observer) => { window.__overrideObserverCalls++; if (window.__overrideObserverCalls > 50) { observer.disconnect(); return; } cb(records, observer); }); }
    };
    const original = window.fetch;
    window.fetch = (...args) => {
      if (String(args[0]).includes('/api/overrides')) return Promise.resolve(new Response(JSON.stringify({ok:true,overrides:{texts:{'shell.pick':'测试标题','speed-plan.step.character':'测试角色'}}}), {headers:{'Content-Type':'application/json'}}));
      if (String(args[0]).includes('/api/ui-state') && (!args[1]?.method || args[1].method === 'GET')) return Promise.resolve(new Response(JSON.stringify({ok:true,storageId:'text-override-isolated',entries:{}}), {headers:{'Content-Type':'application/json'}}));
      return original(...args);
    };
  })();` });
  await send('Page.navigate', { url: `${base}/?text-override-test=1` });
  await wait("document.querySelector('#crumb')?.textContent === '测试标题' && document.querySelector('.nav-feature[data-feature=\"speed-plan\"]')");
  await new Promise(r => setTimeout(r, 200));
  if (await evaluate('window.__overrideObserverCalls > 50')) throw Error('文字覆盖触发重复更新');
  await evaluate("document.querySelector('.nav-feature[data-feature=\"speed-plan\"]').click()");
  await wait("document.querySelector('[data-text=\"speed-plan.step.character\"]')?.textContent === '测试角色'");
  await new Promise(r => setTimeout(r, 200));
  if (await evaluate('window.__overrideObserverCalls > 50')) throw Error('动态页面文字覆盖触发重复更新');
  console.log('[OK] 外壳与动态页面文字覆盖生效，监听不会反复触发');
} finally { ws.close(); }
