#!/usr/bin/env python
"""打一个可以发给别人测试的包。

    python make_package.py

产出 `dist/game-toolbox-v<版本>.zip`：解压 → 双击 start.bat 就能用。
会自动排除缓存、用户数据、构建产物等不该进包的东西。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import re
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import __toolbox_name__, __version__  # noqa: E402

DIST_DIR = ROOT / "dist"
PACKAGE_NAME = f"game-toolbox-v{__version__}"

# 不进包的东西：缓存、用户数据、构建产物、编辑器/系统垃圾
EXCLUDE_DIRS = {
    # nanoka 是**构建期数据源**（335 个 JSON，8MB），运行时不读，别打进包
    "nanoka",
    "__pycache__", ".venv", "venv", "dist", "build", ".git", ".idea", ".vscode",
    "node_modules", "edge-profile", "userdata", ".asset-cache", "BrowserMetrics", ".pytest_cache",
    ".cache",  # tools/.cache 里是导入器的原始抓取数据（好几 MB），不进包
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log", ".zip", ".spec"}

# 只有「作者包」才写进使用说明：后门模块的存在不给别人看到
# 注意用 r""" —— 里面有 tools\dump_overrides.py 这种反斜杠路径，
# 普通字符串会触发 SyntaxWarning: invalid escape sequence '\d'。
ADMIN_USAGE_BLOCK = r"""
  界面（仅作者包包含，属于「后门」模块）
    [外观与排版] 可视化改配色 / 字体 / 字号 / 圆角 / 留白 / 侧边栏宽度 / 界面文字，
                 改完实时预览；预设（浅色、高对比、紧凑、大字）；主题可导出导入。
    [功能与文字] 改功能名 / 图标 / 说明，隐藏功能，调整侧边栏顺序。
    [文字替换]   把界面上的固定文案换成自己的说法（卡片标题、按钮、提示）。
    以上都写进 userdata/shell-overrides.json 与 userdata/interface/theme.json，
    升级不丢、也不会出现在发给别人的包里；助手可用 python tools\dump_overrides.py 读出全部改动。
"""

USAGE = r"""{name} v{version} —— 使用说明
{line}

【怎么打开】
  1. 把整个文件夹解压到任意位置（路径里别带奇怪符号就行）
  2. 双击 start.bat       → 桌面窗口版（关掉窗口，程序自动退出）
     双击 start-web.bat   → 网页版（用浏览器打开，服务常驻，Ctrl+C 退出）
     双击 手机打开.bat     → 手机版（把配速查询挂到局域网，打印手机能打开的地址）

【只想测配速查询，连 Python 都不想装？】
  双击「配速查询-网页版.html」（就在本文件夹里）——
  单文件、不需要服务、不需要 Python，浏览器直接开（手机也能开）。
  页面顶部会显示自检结果（与 Python 版逐项对拍），算得对不对一眼能看到。
  注意：这个单文件版本只有「配速查询」这一个功能。

【想在手机上用】
  双击 手机打开.bat → 手机连同一个 Wi-Fi，用浏览器打开窗口里显示的 http://192.168.x.x:8770
  （也可以把「配速查询-网页版.html」直接传到手机，用浏览器打开这个文件，效果一样）
  打不开时按顺序检查：同一个 Wi-Fi / Windows 防火墙弹窗选「允许访问」/ 电脑没休眠。

【需要什么】
  只要电脑上有 Python 3.10 或更高版本。
  没有第三方依赖，不需要 pip install 任何东西，断网也能用。
  启动脚本会自己找 Python；找不到会明确提示你。

【现在有什么】
  崩坏：星穹铁道
    [配速查询] 角色/光锥/星魂/遗器套装 → 各模式各 T 数各动数需要的速度（风套/翁瓦克/速度套装自动计入）
    [配速排轴] 速度阈值计算 / 阈值速查表 / 多角色行动顺序模拟
    [阿哈时刻配速] 原版工具逐字节原样嵌入（阿哈速度加权 / 阈值反推 / 队伍配速 / 行动值排轴）
    [抽卡规划] 期望抽数 / 概率分位 / 星琼成本 / 累计概率曲线 / 参数自检
{admin_block}
【游戏更新了怎么更新数据】
  python tools\import_hsr_data.py            （联网重抓，缓存在 tools\.cache）
  python tools\import_hsr_data.py --offline  （只用缓存重新生成）

【想验证算得对不对】
  双击 自检.bat，会跑 {test_count} 项测试：
    - 配速公式对拍公开攻略里的数值（134 / 200 / 167.33 / 140.67）
    - 抽卡模型对拍官方公布的综合概率（角色池 1.600%、光锥池 1.870%）
  终端里最后显示 OK 就是全过。
  网页版与 Python 版的一致性另外对拍（需要 node）：
    node tools\check_web_port.mjs
  想更狠一点（用 20 万次随机模拟交叉验证解析解）：
    在命令行里跑  python tests\verify_gacha_montecarlo.py 200000

【怎么加新功能】
  看 docs\EXTENDING.md，或者在程序里点左下角「扩展指南」。
  最快的办法是在项目目录里跑：
    python run.py new-feature honkai-star-rail <目录名> "<显示名>"
  加完点界面右上角「重新扫描」，不用重启。

【出问题了】
  - 端口被占用：程序会自动换成别的端口，窗口里显示的地址就是实际地址
  - 界面空白：按 F12 看控制台红字
  - 新加的功能没出现：点右上角「重新扫描」，再看左下角「模块状态」有没有警告
  - 窗口关不掉/进程残留：正常情况下关窗 25 秒内自动退出；也可以在任务管理器里结束 python.exe

打包时间：{built_at}
"""


def should_skip(path: Path) -> bool:
    """哪些文件不进包。

    注意：**不能**简单地"排除所有 . 或 _ 开头的路径"——那会把 `__init__.py`
    一起排除掉，包解开后 `from core import ...` 直接失败、程序起不来（踩过）。
    所以分开判断：
      * 以 . 开头的：缓存、.git、._tmp 这类，一律不要；
      * 以 _ 开头的：只有**目录**才排除（临时目录、私有目录），文件名不管。
    """
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    parts = path.parts
    for index, part in enumerate(parts):
        if part in EXCLUDE_DIRS:
            return True
        if part.startswith("."):
            return True
        is_last = index == len(parts) - 1
        if not is_last and part.startswith("_"):
            return True
    return False


def admin_only_module_dirs() -> set[str]:
    """找出标了 adminOnly 的模块目录（「后门」模块，不进用户包）。"""
    names: set[str] = set()
    modules_dir = ROOT / "modules"
    if not modules_dir.is_dir():
        return names
    for manifest in modules_dir.glob("*/manifest.json"):
        try:
            meta = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(meta, dict) and meta.get("adminOnly"):
            names.add(manifest.parent.name)
    return names


def collect_files(exclude_admin: bool = False) -> list[Path]:
    """收集要进包的文件。userdata 不进包（那是用户数据）。

    exclude_admin=True 时**整个后门模块都不会被打进去** ——
    这样发给别人的包里连文件都没有，对方就算知道配置项也开不出来。
    """
    blocked = admin_only_module_dirs() if exclude_admin else set()
    files: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if should_skip(rel):
            continue
        if rel.parts[0] == "userdata":
            continue  # 用户数据（含图片缓存、配速预设、外观主题）不打包
        if len(rel.parts) >= 2 and rel.parts[0] == "modules" and rel.parts[1] in blocked:
            continue
        files.append(rel)
    return files


def build_web_version(with_theme: bool = True, out_name: str | None = None) -> Path | None:
    """顺手生成「配速查询」单文件网页版，并放进包里。

    * with_theme=False 用于**用户包**：不把作者自己的外观主题内联进去（别人拿到的是默认外观）。
    * 网页版的算法是 web_api.js（与 Python 版逐项对拍过），没有就跳过。
    """
    api_js = ROOT / "modules" / "honkai-star-rail" / "features" / "speed-plan" / "web_api.js"
    if not api_js.is_file():
        return None
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import make_web_standalone  # type: ignore

        return make_web_standalone.build(with_theme=with_theme, out_name=out_name)
    except Exception as exc:  # 网页版失败不该挡住打包
        print(f"（网页版没生成成功，跳过：{exc}）")
        return None


def write_zip(
    zip_path: Path,
    files: list[Path],
    web_page: Path | None,
    usage_text: str,
    admin: bool,
) -> dict[str, object]:
    """打一个包。admin=False 时把 config.json 里的后门关掉（连模块文件都不在包里）。"""
    config_rel = Path("config.json")
    config_text = None
    if config_rel in files:
        try:
            cfg = json.loads((ROOT / config_rel).read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
        if isinstance(cfg, dict):
            cfg["admin"] = bool(admin)
            config_text = json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in files:
            if config_text is not None and rel == config_rel:
                # 写一份改过 admin 开关的配置进去，不动项目里的 config.json
                zf.writestr(f"{PACKAGE_NAME}/{rel.as_posix()}", config_text)
                continue
            zf.write(ROOT / rel, f"{PACKAGE_NAME}/{rel.as_posix()}")
        if web_page and web_page.is_file():
            # 单文件网页版放包根目录：双击就能用，不需要 Python
            zf.writestr(f"{PACKAGE_NAME}/配速查询-网页版.html", web_page.read_bytes())
        # 空目录也要在（解压后能直接写数据）
        zf.writestr(
            f"{PACKAGE_NAME}/userdata/放你自己的数据在这里.txt",
            "这个目录存的是你的数据（存档、偏好等）。\n升级工具箱时整体替换代码目录，这个目录保留就不会丢数据。\n",
        )
        zf.writestr(f"{PACKAGE_NAME}/使用说明.txt", usage_text)

    data = zip_path.read_bytes()
    return {
        "path": zip_path,
        "kb": len(data) / 1024,
        "sha256": hashlib.sha256(data).hexdigest(),
        "files": len(files) + (1 if web_page and web_page.is_file() else 0) + 2,
    }


def count_tests() -> int:
    """自检的测试条数按源码现数（旧版写死 142，加了测试就对不上）。"""
    text = (ROOT / "tests" / "test_toolbox.py").read_text(encoding="utf-8")
    return len(re.findall(r"^    def test_", text, flags=re.M))


def main() -> int:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    built_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    admin_block = ADMIN_USAGE_BLOCK if any(
        (ROOT / "modules" / name / "manifest.json").is_file()
        for name in admin_only_module_dirs()
    ) else ""

    def usage(admin: bool) -> str:
        return USAGE.format(
            name=__toolbox_name__,
            version=__version__,
            line="=" * 46,
            built_at=built_at,
            admin_block=admin_block if admin else "",
            test_count=count_tests(),
        )

    print(f"打包 {PACKAGE_NAME}（用户包 + 作者包） …")

    # ---------- ① 作者包：带后门模块，作者自己用 ----------
    admin_page = build_web_version(with_theme=True, out_name="_admin-page.html")
    admin_files = collect_files(exclude_admin=False)
    admin_zip = DIST_DIR / f"{PACKAGE_NAME}-admin.zip"
    admin_info = write_zip(admin_zip, admin_files, admin_page, usage(True), admin=True)

    # ---------- ② 用户包：不含后门模块，config 里 admin=false ----------
    user_page = build_web_version(with_theme=False, out_name="_user-page.html")
    user_files = collect_files(exclude_admin=True)
    user_zip = DIST_DIR / f"{PACKAGE_NAME}.zip"
    user_info = write_zip(user_zip, user_files, user_page, usage(False), admin=False)

    # ---------- ③ 顺手刷新「-latest」包 ----------
    # tools/install_local.ps1 装的就是 dist\game-toolbox-admin-latest.zip 这两个固定名字。
    # 以前要手工复制，忘了就会「打包成功、装上去还是旧版本」——这里直接同步掉。
    latest_pairs = (
        (user_zip, DIST_DIR / "game-toolbox-latest.zip"),
        (admin_zip, DIST_DIR / "game-toolbox-admin-latest.zip"),
    )
    print()
    for source, target in latest_pairs:
        shutil.copyfile(source, target)
        print(f"🔄 已刷新：{target.name}（{target.stat().st_size / 1024:.1f} KB）")

    # 临时网页文件清掉
    for temp in (admin_page, user_page):
        if temp and temp.is_file() and temp.name.startswith("_"):
            temp.unlink(missing_ok=True)

    print()
    print(f"✅ 用户包（发给别人）：{user_info['path']}")
    print(f"   大小 {user_info['kb']:.1f} KB · 文件数 {user_info['files']} · SHA256 {user_info['sha256']}")
    print(f"   不含后门模块：{'、'.join(sorted(admin_only_module_dirs())) or '（无）'}；config.json 里 admin=false")
    print()
    print(f"✅ 作者包（你自己用）：{admin_info['path']}")
    print(f"   大小 {admin_info['kb']:.1f} KB · 文件数 {admin_info['files']} · SHA256 {admin_info['sha256']}")
    print(f"   含后门模块，config.json 里 admin=true；网页版内联了你的外观主题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
