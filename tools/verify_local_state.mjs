/** 应用级持久化验收。只用于独立 GT_USERDATA 与临时浏览器。
 * node tools/verify_local_state.mjs <服务端口> <独立CDP端口> [HTML路径]
 */
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const [port='8961', debug='9437', html] = process.argv.slice(2), base=`http://127.0.0.1:${port}`;
const target=(await(await fetch(`http://127.0.0.1:${debug}/json/list`)).json()).find(t=>t.type==='page'&&(t.url==='about:blank'||t.url.startsWith(base)||t.url.startsWith('file:')));
if(!target) throw Error('未找到本任务临时浏览器的验收页面');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
let id=0, checks=0;
const pending=new Map();
ws.onmessage=e=>{const m=JSON.parse(e.data),p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}};
const send=(method,params={})=>new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});ws.send(JSON.stringify({id:key,method,params}));setTimeout(()=>{if(pending.delete(key))reject(Error(`${method} timeout`));},15000).unref();});
async function ev(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function wait(expression){for(let i=0;i<100;i++){if(await ev(expression))return;await sleep(100);}throw Error(`等待失败: ${expression}`);}
const check=(name,ok)=>{if(!ok)throw Error(`[X] ${name}`);checks++;console.log(`[OK] ${name}`);};
async function navigate(feature){await send('Page.navigate',{url:`${base}/?state-test=${Date.now()}#/${feature}`});await wait(`document.querySelector('#nav')&&!!window.GT_LOCAL_STATE`);}
async function clickNav(feature){await ev(`document.querySelector('.nav-feature[data-module="${feature.split('/')[0]}"][data-feature="${feature.split('/')[1]}"]').click()`);}
async function setInput(selector,value,event='input'){await ev(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('${event}',{bubbles:true}));})()`);}
async function stateFile(){return (await(await fetch(`${base}/api/ui-state`)).json()).entries;}
async function waitFile(key,test){for(let i=0;i<60;i++){const s=(await stateFile())[key];if(s&&test(s.value))return s.value;await sleep(100);}throw Error(`文件未保存: ${key}`);}
try{
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false});
  await navigate('honkai-star-rail/speed-plan');
  await wait(`document.querySelector('#substat')&&document.querySelector('#hero-current')?.textContent!=='—'`);
  await ev(`document.querySelector('[data-char="1505"]').click()`);
  await wait(`document.querySelector('[data-char="1505"]').getAttribute('aria-selected')==='true'`);
  await setInput('#substat','37.5');await setInput('#superimpose','3','change');await setInput('#eidolon','2','change');
  await setInput('#customAV','350');await setInput('#firstUltAction','3');await setInput('#preset-energy','123.5');
  await ev(`document.querySelector('.sp-tabs [data-tab="timeline"]').click()`);
  await waitFile('honkai-star-rail/speed-plan',s=>s.data.state.relic.substatSpeed===37.5&&s.data.state.superimpose===3&&s.data.aha.initialEnergy==='123.5');
  check('配速输入自动写入 userdata 状态文件',true);
  await clickNav('honkai-star-rail/aha-speed');await wait(`document.querySelector('#aha-team-name')&&document.querySelector('.aha-ev-row')`);
  await setInput('.unit-num[data-slot="0"][data-key="permFlat"]','57.25');await setInput('#cfg-maxAV','450');
  await setInput('#aha-team-name','未另存的编辑草稿');await ev(`document.querySelector('[data-filter="ultimate"]').click();document.querySelector('#aha-unit-0 .aha-advanced').open=true`);
  await waitFile('honkai-star-rail/aha-speed',s=>s.data.team[0].permFlat===57.25&&s.data.config.maxAV===450&&s.data.teamName==='未另存的编辑草稿');
  check('未命名保存的队伍编辑也自动落盘',true);
  await ev(`document.querySelector('.view').scrollTop=200;document.querySelector('#aha-timeline-list').scrollTop=180`);
  await sleep(200);
  const scrolls=await ev(`({page:document.querySelector('.view').scrollTop,axis:document.querySelector('#aha-timeline-list').scrollTop})`);
  await clickNav('honkai-star-rail/speed-plan');await wait(`document.querySelector('#substat')?.value==='37.5'`);
  check('切页恢复角色、装备档位、目标和补充参数',await ev(`document.querySelector('[data-char="1505"]').getAttribute('aria-selected')==='true'&&document.querySelector('#superimpose').value==='3'&&document.querySelector('#eidolon').value==='2'&&document.querySelector('#customAV').value==='350'&&document.querySelector('#firstUltAction').value==='3'&&document.querySelector('#preset-energy').value==='123.5'`));
  check('配速页签恢复',await ev(`document.querySelector('.sp-tabs .tab.active').dataset.tab==='timeline'`));
  await ev(`window.__fetchBeforeSaveTest=window.fetch;window.fetch=(url,options)=>String(url)==='/api/ui-state'&&options?.method==='POST'?Promise.reject(new Error('验收模拟写入失败')):window.__fetchBeforeSaveTest(url,options)`);
  await setInput('#substat','38.25');
  await wait(`document.querySelector('#local-save-status')?.classList.contains('is-error')`);
  check('写入失败显式提示，页面仍保留编辑',await ev(`document.querySelector('#substat').value==='38.25'&&document.querySelector('#local-save-status').textContent.includes('失败')`));
  await ev(`(async()=>{window.fetch=window.__fetchBeforeSaveTest;await window.GT_LOCAL_STATE.flush()})()`);
  await waitFile('honkai-star-rail/speed-plan',s=>s.data.state.relic.substatSpeed===38.25);
  check('恢复连接后可把保留的编辑补写到本机',true);
  await clickNav('honkai-star-rail/aha-speed');await wait(`document.querySelector('#aha-team-name')?.value==='未另存的编辑草稿'`);
  check('切页恢复队伍参数、筛选、折叠状态',await ev(`document.querySelector('.unit-num[data-slot="0"][data-key="permFlat"]').value==='57.25'&&document.querySelector('#cfg-maxAV').value==='450'&&document.querySelector('[data-filter="ultimate"]').classList.contains('is-active')&&document.querySelector('#aha-unit-0 .aha-advanced').open`));
  await wait(`document.querySelector('#aha-timeline-list').scrollTop===${scrolls.axis}`);
  check('页面与时间轴内部滚动位置恢复',await ev(`document.querySelector('.view').scrollTop===${scrolls.page}`));
  await ev(`window.GT_LOCAL_STATE.flush()`);
  // 清除专用浏览器的本源数据，模拟更换浏览器配置；服务文件不动。
  await send('Storage.clearDataForOrigin',{origin:base,storageTypes:'local_storage'});
  await navigate('honkai-star-rail/aha-speed');await wait(`document.querySelector('#cfg-maxAV')?.value==='450'`);
  check('清除浏览器缓存后仍从 userdata 恢复',await ev(`document.querySelector('#aha-team-name').value==='未另存的编辑草稿'&&document.querySelector('.unit-num[data-slot="0"][data-key="permFlat"]').value==='57.25'`));
  await navigate('honkai-star-rail/gacha');await wait(`document.querySelector('#pity')`);
  await setInput('#pity','23');await setInput('#copies','2');await setInput('#have','123');
  await ev(`document.querySelector('#guaranteed').checked=true;document.querySelector('#guaranteed').dispatchEvent(new Event('change',{bubbles:true}))`);
  await waitFile('honkai-star-rail/gacha',s=>s.forms['id:pity']==='23'&&s.forms['id:have']==='123');
  await navigate('honkai-star-rail/gacha');await wait(`document.querySelector('#pity')?.value==='23'`);
  check('抽卡规划输入和复选框恢复',await ev(`document.querySelector('#copies').value==='2'&&document.querySelector('#have').value==='123'&&document.querySelector('#guaranteed').checked`));
  await navigate('honkai-star-rail/speed');await wait(`document.querySelectorAll('#units-body tr').length>0`);
  await ev(`document.querySelector('#add-unit').click()`);await setInput('#units-body tr:last-child [data-k="name"]','自定义测试位');await setInput('#units-body tr:last-child [data-k="speed"]','177.7');await setInput('#cycles','5');
  await waitFile('honkai-star-rail/speed',s=>s.data.units.at(-1).speed===177.7);
  const unitCount=await ev(`document.querySelectorAll('#units-body tr').length`);
  await navigate('honkai-star-rail/speed');await wait(`document.querySelector('#units-body tr:last-child [data-k="speed"]')?.value==='177.7'`);
  check('普通配速排轴的增删单位及输入恢复',await ev(`document.querySelectorAll('#units-body tr').length===${unitCount}&&document.querySelector('#units-body tr:last-child [data-k="name"]').value==='自定义测试位'&&document.querySelector('#cycles').value==='5'`));
  await navigate('action-value/timeline');await wait(`document.querySelector('#av-flat')`);
  await setInput('#av-flat','61.25');await setInput('#av-rounds','6');await ev(`document.querySelector('[data-tab="energy"]').click()`);await wait(`document.querySelector('#av-err')`);await setInput('#av-err','27.4');
  await waitFile('action-value/timeline',s=>s.data.tab==='energy'&&s.data.speedFlat===61.25&&s.data.err===27.4);
  await navigate('action-value/timeline');await wait(`document.querySelector('#av-err')?.value==='27.4'`);
  check('行动值排轴页签与回能参数恢复',await ev(`document.querySelector('#av-flat').value==='61.25'&&document.querySelector('#av-rounds').value==='6'`));
  await navigate('interface/appearance');await wait(`document.querySelector('[data-number="baseSize"]')`);
  await setInput('[data-number="baseSize"]','16');
  await sleep(500);
  check('外观编辑自动写入原有主题文件',await ev(`(async()=>{const r=await(await fetch('/api/call',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({module:'interface',feature:'appearance',action:'load',payload:{}})})).json();return r.result.theme.fonts.baseSize===16})()`));
  await ev(`document.querySelector('#ap-reset').click()`);await sleep(500);
  await navigate('interface/appearance');await wait(`document.querySelector('[data-number="baseSize"]')`);
  check('恢复默认不会被旧自动草稿覆盖',await ev(`document.querySelector('[data-number="baseSize"]').value!=='16'`));
  await navigate('interface/nav');await wait(`document.querySelector('[data-name="honkai-star-rail/speed"]')`);
  await setInput('[data-name="honkai-star-rail/speed"]','自动保存测试');
  await wait(`(async()=>{const r=await(await fetch('/api/overrides')).json();return r.overrides.labels?.['honkai-star-rail/speed']?.name==='自动保存测试'})()`);
  check('导航编辑自动写入原有覆盖文件',true);
  await ev(`document.querySelector('#nav-reset').click()`);await sleep(400);
  await navigate('interface/texts');await wait(`document.querySelector('[data-key="shell.pick"]')`);
  await setInput('[data-key="shell.pick"]','自动文字测试');
  await wait(`(async()=>{const r=await(await fetch('/api/overrides')).json();return r.overrides.texts?.['shell.pick']==='自动文字测试'})()`);
  check('文案编辑自动写入原有覆盖文件',true);
  await ev(`document.querySelector('#tx-reset').click()`);await sleep(400);
  if(html){
    await send('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:0,uploadThroughput:0});
    const file=pathToFileURL(resolve(html)).href;
    await send('Page.navigate',{url:file});await wait(`document.querySelector('#substat')`);
    await ev(`document.querySelector('[data-view="view"]').click()`);await setInput('#substat','42.5');await setInput('#preset-energy','90');
    await ev(`document.querySelector('#open-team-simulator').click()`);await wait(`document.querySelector('#cfg-maxAV')`);await setInput('#cfg-maxAV','400');await setInput('#aha-team-name','离线自动草稿');
    await sleep(200);await send('Page.reload');await wait(`document.querySelector('#aha-team-name')?.value==='离线自动草稿'`);
    check('独立 HTML 刷新后恢复最后页面与队伍草稿',await ev(`!document.querySelector('#view-aha').hidden&&document.querySelector('#cfg-maxAV').value==='400'`));
    await ev(`document.querySelector('#aha-manage-builds').click()`);await wait(`document.querySelector('#substat')?.value==='42.5'`);
    check('独立 HTML 断网恢复未保存的配速编辑',await ev(`document.querySelector('#preset-energy').value==='90'`));
    await send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  }
  console.log(`[OK] ${checks} persistence checks`);
}finally{ws.close();}
