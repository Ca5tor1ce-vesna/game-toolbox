# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 配方：--onedir、无控制台、带图标。由 packaging/build_green.py 调用：
#     pyinstaller packaging/游戏工具箱.spec --distpath build/green-dist --workpath build/green-work
# 环境变量：
#     GT_ROOT   项目根目录（默认：本文件上一级）
#     GT_STAGE  已经整理好的资源目录（app / modules / docs / config.json，由 build_green.py 生成；
#               里面已经去掉了作者后门模块和构建期数据）
#     GT_VERSION_FILE  可选，Windows 版本信息资源文件
# 产物：<distpath>/游戏工具箱/游戏工具箱.exe + _internal/（PyInstaller 6 默认的内部目录）
import ast
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(os.environ.get("GT_ROOT") or Path(SPECPATH).parent).resolve()
STAGE = Path(os.environ.get("GT_STAGE") or ROOT / "build" / "green-stage").resolve()
ICON = str(ROOT / "packaging" / "toolbox.ico")
VERSION_FILE = os.environ.get("GT_VERSION_FILE") or None


def module_imports() -> list[str]:
    """功能目录里的 api.py 是运行时按文件加载的，PyInstaller 分析不到它们的 import，
    这里把它们用到的标准库模块列成 hiddenimports（不列的话 exe 里会 ModuleNotFoundError）。"""
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    found: set[str] = set()
    for path in (STAGE / "modules").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module]
            else:
                continue
            for name in names:
                if name.split(".")[0] in stdlib:
                    found.add(name)
    return sorted(found)


datas = [
    (str(STAGE / "app"), "app"),
    (str(STAGE / "modules"), "modules"),
    (str(STAGE / "docs"), "docs"),
    (str(STAGE / "config.json"), "."),
]

# 运行时 DLL：打包机的 Python 若是精简发行版（缺 ucrtbase / api-ms-win 转发 DLL），
# 打出来的 exe 会**依赖目标机器自己装好 UCRT** —— 换台机器就可能起不来。
# 官方 CI 版把这一整套一起打进去（实测比精简版多 45 个 DLL）。
# 把 DLL 放进 packaging/runtime/（可选），存在就一并打进去；不存在就按裸 PATH 处理。
RUNTIME_DIR = Path(os.environ.get("GT_RUNTIME") or (Path(SPECPATH) / "runtime"))
if RUNTIME_DIR.is_dir():
    datas.append((str(RUNTIME_DIR), "."))
    print(f"[spec] 附带运行时 DLL {len(list(RUNTIME_DIR.glob('*.dll')))} 个：{RUNTIME_DIR}")

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=collect_submodules("core") + module_imports(),
    excludes=["tkinter", "unittest", "pydoc", "test"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="游戏工具箱",
    icon=ICON,
    version=VERSION_FILE,
    console=False,
    debug=False,
    strip=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="游戏工具箱")
