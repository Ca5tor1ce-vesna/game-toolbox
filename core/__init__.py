"""游戏实用工具箱 —— 核心包。

设计目标只有一个：**加新功能不要动核心代码**。

* 想加一个游戏：在 `modules/` 下建一个目录，写 `manifest.json`。
* 想给某个游戏加一个工具：在它的 `features/` 下建一个目录，写 `feature.json`。
* 后端逻辑放功能目录的 `api.py`（用 `@api("动作名")` 注册），前端放 `ui.js`。
* 服务启动时自动扫描，界面自动出现，无需注册、无需改配置。

详见 `docs/EXTENDING.md`。
"""

__version__ = "0.20.2beta"
__toolbox_name__ = "b站：@syllo椭圆"
