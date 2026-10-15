"""脚手架：一条命令生成新游戏模块 / 新功能。

    python run.py new-module genshin "原神" --icon 🌏
    python run.py new-feature honkai-star-rail damage "伤害计算" --icon ⚔️

生成的东西立刻可用：重启（或点界面里的「重新扫描」）就能看到。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config

MODULE_MANIFEST = """{
  "id": "__ID__",
  "name": "__NAME__",
  "icon": "__ICON__",
  "version": "0.1.0",
  "gameVersion": "",
  "description": "__DESCRIPTION__",
  "tags": [],
  "accent": "",
  "data": {}
}
"""

FEATURE_JSON = """{
  "id": "__ID__",
  "name": "__NAME__",
  "icon": "__ICON__",
  "order": __ORDER__,
  "description": "__DESCRIPTION__",
  "tags": []
}
"""

FEATURE_API = '''"""__NAME__ —— 后端动作。

每个 @api("名字") 就会变成一个可以从界面调用的动作：
前端 `ctx.call("hello", {name: "开拓者"})` → 这里的 hello(payload, ctx)。
"""

from core.feature_api import api


@api("hello")
def hello(payload, ctx):
    """最小示例：把传进来的名字回显出去。"""
    name = str(payload.get("name") or "开拓者")
    return {
        "message": f"你好，{name}！",
        "module": ctx.module_id,
        "feature": ctx.feature_id,
    }


@api("save_note")
def save_note(payload, ctx):
    """写用户数据的示例：存到 userdata/<模块>/<功能>.json，升级代码不会丢。"""
    note = str(payload.get("note") or "")
    ctx.save_user_data("__ID__", {"note": note})
    return {"saved": note}


@api("load_note")
def load_note(payload, ctx):
    data = ctx.user_data("__ID__") or {}
    return {"note": data.get("note", "")}
'''

FEATURE_UI = """/* __NAME__ —— 前端界面。
 *
 * 约定：export default 一个对象，提供 mount(root, ctx)。
 *   root —— 已经属于这个功能的容器元素，随便写。
 *   ctx.call(动作名, 参数) —— 调后端 api.py 里的动作。
 *   ctx.data(数据名) —— 读模块 data/ 下的数据（用户覆盖层优先）。
 */

export default {
  title: "__NAME__",

  async mount(root, ctx) {
    root.innerHTML = `
      <div class="card">
        <h2>__ICON__ __NAME__</h2>
        <p class="muted">这是脚手架生成的示例功能，改 <code>modules/__MODULE__/features/__ID__/ui.js</code> 即可。</p>
        <div class="row">
          <input id="name" class="input" placeholder="输入名字" />
          <button id="go" class="btn">调用后端</button>
        </div>
        <pre id="out" class="output">（还没有结果）</pre>
      </div>
    `;

    const out = root.querySelector("#out");
    root.querySelector("#go").addEventListener("click", async () => {
      out.textContent = "调用中…";
      try {
        const result = await ctx.call("hello", {
          name: root.querySelector("#name").value || "开拓者",
        });
        out.textContent = JSON.stringify(result, null, 2);
      } catch (err) {
        out.textContent = "出错了：" + err.message;
      }
    });
  },

  unmount() {},
};
"""


def _write(path: Path, content: str, force: bool, created: list[str]) -> None:
    if path.exists() and not force:
        raise SystemExit(f"已存在，未覆盖：{path}（要覆盖就加 --force）")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    created.append(str(path))


def new_module(
    module_id: str,
    name: str,
    icon: str = "🎮",
    description: str = "",
    force: bool = False,
) -> list[str]:
    created: list[str] = []
    module_dir = config.MODULES_DIR / module_id
    if module_dir.exists() and not force:
        raise SystemExit(f"模块已存在：{module_dir}（要覆盖就加 --force）")
    manifest = (
        MODULE_MANIFEST.replace("__ID__", module_id)
        .replace("__NAME__", name)
        .replace("__ICON__", icon)
        .replace("__DESCRIPTION__", description or f"{name} 的工具集")
    )
    _write(module_dir / "manifest.json", manifest, force, created)
    (module_dir / "data").mkdir(parents=True, exist_ok=True)
    (module_dir / "features").mkdir(parents=True, exist_ok=True)
    created.append(str(module_dir / "data"))
    created.append(str(module_dir / "features"))
    return created


def new_feature(
    module_id: str,
    feature_id: str,
    name: str,
    icon: str = "🧩",
    description: str = "",
    order: int = 100,
    force: bool = False,
) -> list[str]:
    created: list[str] = []
    module_dir = config.MODULES_DIR / module_id
    if not (module_dir / "manifest.json").is_file():
        raise SystemExit(f"模块不存在或缺少 manifest.json：{module_dir}")

    feature_dir = module_dir / "features" / feature_id
    replacements: dict[str, str] = {
        "__ID__": feature_id,
        "__NAME__": name,
        "__ICON__": icon,
        "__ORDER__": str(order),
        "__DESCRIPTION__": description or f"{name}",
        "__MODULE__": module_id,
    }

    def render(template: str) -> str:
        out = template
        for key, value in replacements.items():
            out = out.replace(key, value)
        return out

    _write(feature_dir / "feature.json", render(FEATURE_JSON), force, created)
    _write(feature_dir / "api.py", render(FEATURE_API), force, created)
    _write(feature_dir / "ui.js", render(FEATURE_UI), force, created)
    return created


def describe_module(module_dir: Path) -> dict[str, Any]:
    """给 `run.py new-feature` 用：读一下模块信息，确认目录是活的。"""
    manifest = json.loads((module_dir / "manifest.json").read_text(encoding="utf-8"))
    return {"id": manifest.get("id", module_dir.name), "name": manifest.get("name", "")}
