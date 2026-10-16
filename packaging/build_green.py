#!/usr/bin/env python
"""绿色版（免安装）打包：产出 dist/游戏工具箱-v<版本>-绿色版.zip。

    python make_package.py --green          （等同于 python packaging/build_green.py）

zip 根目录：
    游戏工具箱.exe      PyInstaller --onedir 启动器（无控制台窗口，带图标）
    使用说明.html
    userdata/           空目录，用户数据都写在这里（升级时保留这个目录即可）
    _internal/          程序本体（Python 运行时 + app / modules / docs + 默认 config.json）

步骤：① 整理资源到 build/green-stage（用户包口径：去掉作者后门模块，admin=false）
      ② 跑 PyInstaller（packaging/游戏工具箱.spec）
      ③ 组装并压缩。
exe 只能在 Windows 上打（PyInstaller 不能交叉编译）。在 Linux/macOS 上运行时会打出本机可执行文件，
只用于冒烟检查目录结构，产物名带「-非Windows冒烟」，不要拿去发布。
需要：pip install pyinstaller（图标已提交在 packaging/toolbox.ico；重画用 make_icon.py，需要 Pillow）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import __version__  # noqa: E402

BUILD = ROOT / "build"
STAGE = BUILD / "green-stage"
WORK = BUILD / "green-work"
DISTPATH = BUILD / "green-dist"
APP_NAME = "游戏工具箱"
IS_WINDOWS = os.name == "nt"
ZIP_NAME = f"{APP_NAME}-v{__version__}-绿色版" + ("" if IS_WINDOWS else "-非Windows冒烟")
STAGE_TOP = ("app", "modules", "docs")


def stage_resources() -> list[str]:
    """把要进 _internal 的资源整理到 STAGE。沿用 make_package.py 的排除规则（用户包口径）。"""
    import make_package  # 项目根目录的打包脚本

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    copied = []
    for rel in make_package.collect_files(exclude_admin=True):
        if rel.parts[0] not in STAGE_TOP:
            continue
        target = STAGE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
        copied.append(rel.as_posix())
    # 默认配置：用户包口径（后门关闭）。exe 旁边放了 config.json 时以那份为准。
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg["admin"] = False
    (STAGE / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return copied


def version_parts() -> tuple[int, int, int, int]:
    """`__version__` → Windows 资源里那四段整数。

    版本号允许带后缀（`0.20.0beta`、`0.21.0-rc1` 这类），但文件属性的四段**必须是整数**，
    所以每段只取开头的数字：`0.20.0beta` → `(0, 20, 0, 0)`。之前这里直接 `int(x)`，
    一旦版本号带后缀，绿色版会打到一半才崩（`invalid literal for int(): '0beta'`）。
    """
    parts: list[int] = []
    for chunk in __version__.split("."):
        match = re.match(r"\d+", chunk.strip())
        parts.append(int(match.group(0)) if match else 0)
    return tuple((parts + [0, 0, 0, 0])[:4])  # type: ignore[return-value]


def write_version_file() -> Path:
    """Windows 资源里的版本号（文件属性 → 详细信息）。"""
    v = version_parts()
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('080404b0', [
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('ProductVersion', '{__version__}'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe')])]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    return path


def run_pyinstaller() -> Path:
    env = dict(os.environ, GT_ROOT=str(ROOT), GT_STAGE=str(STAGE))
    if IS_WINDOWS:
        env["GT_VERSION_FILE"] = str(write_version_file())
    if DISTPATH.exists():
        shutil.rmtree(DISTPATH)
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", str(DISTPATH), "--workpath", str(WORK), str(HERE / f"{APP_NAME}.spec"),
    ]
    print("运行：", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)
    out = DISTPATH / APP_NAME
    if not (out / "_internal").is_dir():
        raise SystemExit(f"PyInstaller 产物里没有 _internal：{out}")
    return out


def usage_html() -> str:
    template = (HERE / "使用说明.html").read_text(encoding="utf-8")
    return template.replace("{{version}}", __version__).replace(
        "{{built_at}}", datetime.now().strftime("%Y-%m-%d %H:%M")
    )


def assemble(app_dir: Path) -> Path:
    """按约定的根目录结构压缩。zip 根目录就是 exe / 使用说明 / userdata / _internal。"""
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    zip_path = dist / f"{ZIP_NAME}.zip"
    exe_name = f"{APP_NAME}.exe" if IS_WINDOWS else APP_NAME
    exe = app_dir / exe_name
    if not exe.is_file():
        raise SystemExit(f"找不到启动器：{exe}")
    now = datetime.now().timetuple()[:6]

    def entry(name: str, mode: int) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(name, date_time=now)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = mode << 16
        return info

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr(entry(exe_name, 0o100755), exe.read_bytes())
        for path in sorted((app_dir / "_internal").rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(app_dir).as_posix())
        zf.writestr(entry("使用说明.html", 0o100644), usage_html().encode("utf-8"))
        # 空目录（目录项：名字以 / 结尾，带目录属性；Windows 资源管理器解压也会建出来）
        empty = entry("userdata/", 0o40755)
        empty.external_attr |= 0x10
        zf.writestr(empty, b"")
    return zip_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-only", action="store_true", help="只整理资源（不跑 PyInstaller）")
    args = parser.parse_args(argv)
    files = stage_resources()
    print(f"① 资源已整理：{len(files)} 个文件 → {STAGE}")
    if args.stage_only:
        return 0
    app_dir = run_pyinstaller()
    print(f"② PyInstaller 完成：{app_dir}")
    zip_path = assemble(app_dir)
    size = zip_path.stat().st_size / 1024 / 1024
    # 别在这里用 GBK 编不出的字符（✅ ⚠ ✗ 这类）：中文 Windows 控制台默认 GBK，
    # 一 print 就 UnicodeEncodeError —— 包已经打完、脚本却以 1 退出，本机裸控制台打绿色版必中
    # （`make_package.py` 踩过同一个坑，改用 [OK]/[X]/[刷新] 这类写法）。
    print(f"③ [OK] {zip_path}（{size:.1f} MB）")
    if not IS_WINDOWS:
        print("   注意：这是非 Windows 冒烟产物，不是发布用的 exe。正式包请在 Windows 上打（见 .github/workflows/build.yml）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
