# 扩展指南

这份文档回答一个问题：**以后想加东西，我该动哪个文件。**

核心只有一句话：**目录即插件。** 你往 `modules/` 里丢目录，工具箱就多东西；核心代码一行都不用改。

---

## 一、30 秒加一个新功能

在项目根目录打开命令行，跑：

```
python run.py new-feature honkai-star-rail damage "伤害计算" --icon ⚔️
```

它会生成三个文件：

```
modules/honkai-star-rail/features/damage/
├── feature.json     这个功能的名字、图标、排序、标签
├── api.py           后端逻辑（算数的地方）
└── ui.js            前端界面（长什么样）
```

然后回到工具箱界面，点右上角 **「↻ 重新扫描」**，左边就出现了。不用重启，不用改配置。

> 手感更直接的办法：直接复制 `features/speed/` 整个目录，改名成你的新功能，再把 `feature.json` 里的 `id` 改成目录名。**注意 `id` 必须和目录名一致**，否则调用会对不上。

---

## 二、一个功能由三部分组成

### 1. feature.json —— 自我介绍

```json
{
  "id": "damage",
  "name": "伤害计算",
  "icon": "⚔️",
  "order": 30,
  "description": "一句话说明这个工具干什么，搜索框和鼠标悬停都会用到。",
  "tags": ["伤害", "计算", "配队"]
}
```

* `id` **必须**和目录名一致。
* `order` 越小排越前，留空隙（10、20、30……）方便以后插队。
* `tags` 会参与侧边栏搜索。
* 可选字段：`ui`（默认 `ui.js`）、`api`（默认 `api.py`），改这两个名字才需要写。

### 2. api.py —— 后端，算数的地方

```python
from core.feature_api import api

@api("calculate")
def calculate(payload, ctx):
    atk = float(payload["atk"])
    return {"damage": atk * 2.5}
```

* `@api("名字")` 注册一个动作，前端就能用这个名字调它。
* `payload` 是前端传来的参数（一定是 dict）。
* 返回值必须能转成 JSON。
* `raise ValueError("...")` 抛出的错误会原样显示在界面上——所以**参数不合法时直接抛 `ValueError` 并写清楚人话**，比返回一个隐晦的结果好得多。
* 一个 api.py 里可以注册任意多个动作。

### 3. ui.js —— 前端，长什么样

```javascript
export default {
  async mount(root, ctx) {
    root.innerHTML = `<div class="card"><h2>伤害计算</h2>
      <input id="atk" class="input" /><button id="go" class="btn">算</button>
      <pre id="out" class="output"></pre></div>`;

    root.querySelector("#go").addEventListener("click", async () => {
      const res = await ctx.call("calculate", {
        atk: root.querySelector("#atk").value,
      });
      root.querySelector("#out").textContent = JSON.stringify(res, null, 2);
    });
  },
  unmount() {},   // 可选：清理定时器等
};
```

`ctx` 上有这些：

* `ctx.call(动作名, 参数)` —— 调后端 `api.py` 里的动作，返回 Promise。
* `ctx.data(数据名)` —— 读模块 `data/` 下的 JSON（用户覆盖层优先）。
* `ctx.moduleId` / `ctx.featureId` / `ctx.module` / `ctx.feature`
* `ctx.fmt` —— 格式化小工具：`fmt.num(v, 2)`、`fmt.int(v)`、`fmt.pct(v)`、`fmt.money(v)`

样式方面：`app/style.css` 里已经准备好一整套类名，直接用就能和工具箱风格一致：

* 容器：`card`、`stat-grid`、`stat`（配 `k` / `v`）
* 表单：`row`、`field`、`input`、`input narrow`、`input wide`、`btn`、`btn secondary`、`ghost`
* 表格：`<table class="data">`，数字列加 `class="num"`
* 其它：`muted`、`hint`、`pill`、`output`、`formula`、`tabs` / `tab`、`hidden`

功能专属的样式写在自己的 `style.css` 里（和 `ui.js` 同目录），加载功能时自动插进页面、切走时自动移除。

### 自动保存编辑状态

外壳给功能提供 `ctx.persistence`，桌面/服务版写入 userdata，单文件版使用同一份 `app/local-state.js` 写入浏览器。不要为新页面另建全局 localStorage 键。

- 复杂页面在 `mount` 中用 `ctx.persistence?.load()?.data` 恢复已知的输入字段，并设置 `this.getState = () => ({ ...需要记住的输入 })`。不要把目录、图片、API 输出或计算结果放进去。
- 外壳在挂载后统一绑定自动保存；普通表单没有 `getState` 时按控件保存。需要初次计算就使用恢复值的简单页面，应在计算前调用 `ctx.persistence?.restoreForms(root)`。动态单位列表等必须显式保存数据模型。
- 异步加载后主动改变输入时调用 `ctx.persistence?.capture()`；异步结果渲染后可调用 `ctx.persistence?.restoreUI(root)` 恢复内部滚动。`getState` 必须读到当前输入，不能依赖用户先失焦。
- 功能卸载要取消自身定时器并使旧请求失效；外壳负责解除保存监听并保存最后状态。恢复默认后调用 `ctx.persistence?.reset()`，避免自动恢复旧草稿。
- 单文件生成器也需给该功能提供同名 persistence scope，并在 mount 后绑定。桌面和单文件须分别验证切页、刷新、重开、保存失败和恢复默认；不要只验证界面看起来保留了数值。

跨功能读取存档时，优先复用存档所属功能的 API，不维护另一份角色库。配装计算可参考 `aha-speed/resolve_build` 对 `speed-plan/plan` 的调用：角色 ID 是存档的键，需要补进计算请求；不同模型的字段和公式不能直接照搬，尤其要检查行迹乘区、自动装备加成、累计拉条与开局拉条的区别。队伍快照应与角色存档分开，明确是否跟随角色后续修改。

验收响应式布局时，除检查 `scrollWidth` 外，还应核对实际内容的边界矩形：外壳的 `min-width` 配合 `overflow: hidden` 可能隐藏横向裁切。时间轴应逐条核对引擎返回的 AV、事件序号和说明，同 AV 事件保留引擎顺序。可参考 `tools/verify_team_ui.mjs`。

---

## 三、加一个新游戏

```
python run.py new-module genshin "原神" --icon 🌏
```

生成的 `manifest.json`：

```json
{
  "id": "genshin",
  "name": "原神",
  "icon": "🌏",
  "version": "0.1.0",
  "gameVersion": "6.0",
  "description": "原神工具集",
  "tags": ["原神"],
  "accent": "#4fc3f7"
}
```

`accent` 是这个模块的主题色（十六进制），以后界面会用它做强调色；`gameVersion` 用来说明数据对应哪个游戏版本，会显示在顶栏。

然后在这个模块里加功能：

```
python run.py new-feature genshin artifact "圣遗物评分" --icon 🏺
```

**重复利用已有数据**：新模块的 `api.py` 里可以自由 `import` 别的东西，也可以把公共逻辑抽到 `core/` 之外的自建包里（比如建一个 `shared/` 目录，然后 `sys.path` 里加根目录即可——`run.py` 已经把项目根目录加进了 `sys.path`）。

---

## 五、把现成的单文件 HTML 工具塞进来

手上已经有一个写好的 HTML 小工具（自己写的、别人给的都行），**不打算改它**，只想让它出现在工具箱里——照这个做：

1. 把那个 HTML **原样复制**到功能目录，比如 `features/aha-speed/original.html`。不要重排格式、不要"顺便修一下"。
2. `ui.js` 只用几行把它装进 iframe：

```javascript
export default {
  async mount(root, ctx) {
    const html = await (await fetch(`${ctx.feature.baseUrl}/original.html`)).text();
    root.innerHTML = `<iframe class="my-frame"></iframe>`;
    root.querySelector("iframe").setAttribute("srcdoc", html);
  },
};
```

3. `style.css` 给 iframe 一块高度：

```css
.my-frame { width: 100%; height: calc(100vh - 118px); border: 0; border-radius: 10px; }
```

4. 如果原工具引用了 CDN（比如 `<script src="https://cdn.tailwindcss.com">`），把那个 JS 下载到 `vendor/`，在 `mount` 里**只在内存副本上**替换 URL。磁盘上的原文件保持原样，断网也不会掉样式。
5. 在 `tests/` 里钉一个 SHA256 断言。这样以后谁想"顺手优化"原文件，测试会立刻变红。

现成例子就是 `features/aha-speed/`：原文件 24293 字节、SHA256 有测试盯着，工具箱里的显示与原文件单独打开**逐像素一致**（179 万像素 0 差异）。

---

## 六、数据怎么放、怎么更新

模块的 `data/` 放这个游戏的数据，两个来源叠加：

1. `modules/<模块>/data/<名字>.json` —— 模块自带，跟着代码走。
2. `userdata/<模块>/<名字>.json` —— 你的覆盖层，优先。升级代码不会覆盖它。

读数据用 `ctx.data("名字")`（自动叠加）；想绕过覆盖层读原始数据用 `ctx.raw_data("名字")`。

写用户数据（存档、配置、你选的方案之类）：

```python
@api("save_loadout")
def save_loadout(payload, ctx):
    ctx.save_user_data("loadouts", payload)
    return {"ok": True}

@api("load_loadouts")
def load_loadouts(payload, ctx):
    return {"loadouts": ctx.user_data("loadouts") or {}}
```

**判断数据要不要单独放文件的简单标准**：会随游戏版本变的东西（概率、数值、角色表）放 `data/`；逻辑常数（公式里的 10000）也放 `data/`，这样改数值不用碰代码。

崩铁模块里的正面例子：`data/gacha_pools.json` 里存了卡池参数，还有一个 `officialOverallRate` 字段和界面上的「参数自检」配合——**游戏一旦改概率，自检会立刻报警**，不用等人发现算错了。

---

## 七、设置与外壳

`config.json`：

* `port` / `autoPort` —— 端口，被占用时是否自动往后找。
* `shell` —— `edge`（桌面窗口）、`browser`（默认浏览器）、`none`（不打开）。
* `window.width` / `window.height` —— 桌面窗口初始尺寸。
* `watchdogSeconds` —— 桌面窗口模式下，多久没收到心跳就退出。想让它常驻就调大或设成 0。

命令行覆盖：`python run.py --port 9000 --shell browser --no-watchdog`。

想换成真正的原生壳（Electron / pywebview / 打包成 exe）——只改 `core/launcher.py` 里的 `open_window`。**其余代码一行都不用动**，因为外壳只负责"打开一个 URL"。

---

## 八、调试技巧

* **浏览器 F12** 是最有用的工具：`ui.js` 的报错、接口返回、网络请求都在 Console / Network 里。
* 浏览器直接访问 **`/api/registry`**，能看到当前扫到了哪些模块、每个功能注册了哪些动作、有没有加载错误。
* 手动调后端（开发时很好用）：

```
POST /api/call
{"module":"honkai-star-rail","feature":"speed","action":"threshold","payload":{"cycles":1,"actions":2}}
```

* 后端改完 `api.py` 要重启服务（Python 模块不会热更新）；前端改完 `ui.js` **只要刷新页面**。
* 加了新目录，点界面右上角「↻ 重新扫描」等价于重新扫描 + 重新导入所有 `api.py`。
* 界面左下角「🩺 模块状态」会列出所有加载警告（比如 `feature.json` 写错、`api.py` 有语法错误），**加完功能先看一眼这里**。

---

## 九、几条约定（能省掉以后的痛苦）

* 目录名用**小写英文 + 连字符**（`speed`、`gacha`、`damage-calc`），避免空格和中文——它就是 URL 的一部分。
* 以 `.` 或 `_` 开头的目录会被扫描器忽略，适合放草稿、旧版本、备份。
* 一个功能目录里，`feature.json` 是必需的；`api.py` 和 `ui.js` 至少有一个，否则界面上是个空壳。
* 一个功能的动作名不要重复；跨功能的调用请通过接口组合，不要互相 import `ui.js`。
* 数值类的功能**尽量在 `tests/` 里留一条对拍测试**（拿公开资料里的数字当标准答案）。工具箱算错了比没有更糟。
* 写功能时把"这个数字哪来的"写进 `data/` 的 `meta.source` 字段。半年后你会感谢自己。

---

## 十、备份建议

要备份的东西只有两样：

1. `modules/` —— 你写的所有功能。
2. `userdata/` —— 你的数据。

`core/`、`app/` 属于工具箱本体，升级时整体替换即可。所以**别把自己的功能写进 `core/`**，那样以后升级会打架。
