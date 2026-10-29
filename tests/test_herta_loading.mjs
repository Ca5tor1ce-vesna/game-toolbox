import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../modules/herta/features/records/ui.js', import.meta.url), 'utf8');
const { default: feature } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
let resolveLoad;
const pending = new Promise(resolve => { resolveLoad = resolve; });
const root = { innerHTML: '', querySelector: () => null };
const cleanup = await Promise.race([
  feature.mount(root, { call: () => pending }),
  new Promise((_, reject) => setTimeout(() => reject(Error('加载请求阻塞页面挂载')), 1000)),
]);
assert.match(root.innerHTML, /正在加载数据/);
assert.equal(typeof cleanup, 'function');
cleanup();
resolveLoad({ data: { targets: [] } });
await new Promise(resolve => setTimeout(resolve, 0));
assert.match(root.innerHTML, /正在加载数据/, '离开页面后，旧请求不应继续渲染');
console.log('[OK] 角色顶分后台加载不阻塞挂载，离开后忽略旧结果');
