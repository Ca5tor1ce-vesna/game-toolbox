"""打包「可编辑源码包」与「回传包」。

    python tools/make_source_package.py                  # 发布用源码包（不含你的 userdata）
    python tools/make_source_package.py --with-userdata  # 回传包（含你的全部改动，发回给助手继续编辑）

源码包 = 能直接跑、能直接改的完整工程：
    core/ app/ modules/ tools/ tests/ run.py + 各种 .bat + README
不包含：构建产物（dist）、缓存（__pycache__ / tools/.cache / tools/nanoka）、你的 userdata。
需要重新生成数据时，tools/import_hsr_data.py 会自己把缓存拉回来。
"""

from __future__ import annotations

import argparse
import datetime
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 不进包的东西：构建产物 / 缓存 / 体积大且可重新下载的数据源
EXCLUDE_DIRS = {
    "dist", "build", "__pycache__", ".git", ".idea", ".vscode", ".pytest_cache",
    "node_modules", "venv", ".venv", "edge-profile", "nanoka", ".cache", "onefile",
    # userdata 里的这些是缓存/浏览器配置，回传时没必要带（体积大且无意义）
    ".asset-cache", "asset-cache", "BrowserMetrics",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".zip", ".spec"}

DOC = """游戏工具箱 —— 源码版（可在任何机器上运行、修改）

【怎么跑】
  需要 Python 3.8+（只用标准库，不用装任何第三方包）。
  双击 start.bat          → 独立窗口模式（推荐）
  双击 start-web.bat      → 只用浏览器打开
  双击 手机打开.bat        → 手机/平板访问（会显示局域网地址）
  双击 自检.bat            → 跑一遍自检（数据、算法、测试）

【怎么改】
  * 界面文字/配色：不用改代码 —— 程序里「界面」模块（外观与排版 / 功能与文字 / 文字替换）
    就能改，改动存在 userdata/，升级不丢。
  * 界面结构：modules/<模块>/features/<功能>/ui.js（前端）+ api.py（后端）
  * 算法：modules/honkai-star-rail/features/speed-plan/api.py（Python，权威实现）
        与同目录 web_api.js（浏览器实现，必须与 api.py 保持一致）
  * 数据：modules/honkai-star-rail/data/*.json
  * 改完跑一下：python tests\\test_toolbox.py   和   node tools\\check_web_port.mjs
    （后者校验"网页版实现与 Python 一致"，改了 api.py 一定要跑）

【怎么发回来给助手继续编辑】
  双击 打包回传.bat  → 会在 dist/ 生成 回传-日期时间.zip（**含你的 userdata**：
  外观主题、功能改名、文字替换、配速预设、你自己加的模块）
  把这个 zip 发回给助手即可，助手会在你的改动基础上继续。

【打正式包】
  python make_package.py        一次生成：用户包 + 作者包 + 单文件网页版
  python tools/build_exe.ps1    生成 exe（需要 PyInstaller）
"""


def build(out: Path, with_userdata: bool) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("源码版说明.txt", DOC)
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            parts = rel.parts
            if any(part in EXCLUDE_DIRS for part in parts[:-1]):
                continue
            if parts[0] == "userdata" and not with_userdata:
                continue
            if path.suffix.lower() in EXCLUDE_SUFFIXES:
                continue
            if any(part.startswith(".") for part in parts):
                continue
            if rel.as_posix() == "源码版说明.txt":
                continue  # 上面已经写过最新的一份，再写会在 zip 里出现重名条目
            zf.write(path, str(rel))
            count += 1
    return out, count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-userdata", action="store_true", help="把你的改动一起打包（回传用）")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    if args.out:
        out = Path(args.out)
    elif args.with_userdata:
        out = ROOT / "dist" / f"回传-{stamp}.zip"
    else:
        # 兜底版本号直接取 core.__version__，不再手写一个会过期的常量
        sys.path.insert(0, str(ROOT))
        from core import __version__ as version
        init = (ROOT / "core" / "__init__.py").read_text(encoding="utf-8")
        for line in init.splitlines():
            if "__version__" in line:
                version = line.split("=")[1].strip().strip('"')
                break
        out = ROOT / "dist" / f"游戏工具箱-源码版-v{version}.zip"

    out, count = build(out, args.with_userdata)
    size = out.stat().st_size / 1024
    kind = "回传包（含你的改动）" if args.with_userdata else "源码版（不含 userdata）"
    print(f"  {kind}：{out}")
    print(f"  {count} 个文件，{size:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
