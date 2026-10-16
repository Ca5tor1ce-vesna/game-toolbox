"""发布产物体检：扫 dist/ 里的每个 zip（以及任何残留的 exe 目录），
把**不该发出去的私密条目**找出来。

    python tools/audit_package.py                 # 扫 dist/
    python tools/audit_package.py <zip|目录> ...  # 指定产物
    python tools/audit_package.py --no-fail       # 只报告，不因命中而返回非 0

为什么需要它（旧树 `tools/pack_exe.py` 的职能，在新树换了形态）：
  0.16.x 的 exe 会把浏览器配置写到 `<exe目录>\\_internal\\userdata\\`（History / Cookies /
  Login Data），那时候用 Compress-Archive 整目录打包，**把用户的浏览记录一起发了出去**。
  pack_exe.py 就是为那次事故写的：先清 userdata、再排除、最后自检敏感条目。

  0.17.2 已经从根上改掉了：
    * `core/config.py` 打包后把 userdata 定位到 **exe 旁边**（`sys.executable` 的上一级），
      不再往 `_internal\\userdata` 写；
    * `packaging/build_green.py` 只把 `app / modules / docs` 整理进 `_internal`（白名单），
      `userdata/` 是写进 zip 的**空目录项**；
    * `make_package.py` 的 `EXCLUDE_DIRS` 显式排除 `userdata / edge-profile / .asset-cache`。
  → 所以 **pack_exe.py 不需要移植**，它的「清洁动作」在新树里已经是结构性的了。

  但「打完之后再验一遍」这件事仍然值得留着：排除规则是手写的，谁改漏一行都不会有人发现。
  这个脚本就是那道**发布前最后一眼**，也是 CI 里可以加的一步。

判定口径（名字用 `SENSITIVE`，路径段用 `EXCLUDE_PARTS`）：
  * 私密条目（VIOLATION）：userdata 里的真实文件、edge-profile、Cookies / Login Data /
    History / Web Data / Local State、.asset-cache、BrowserMetrics、*.log/*.pma/*.db。
  * 有意为之（EXPECTED）：包根那个 `userdata/放你自己的数据在这里.txt` 占位说明。
  * 需要人看一眼（REVIEW）：`回传-*.zip` —— 那是你主动把自己的 userdata 打包发回给助手的，
    名字就摆在那儿；它里面的 userdata 按「有意为之」算（不会让体检失败），
    但**别**误当发布包发出去。为了安全，回传包里出现 `edge-profile` / `Cookies` /
    `Login Data` 这类**浏览器**痕迹仍然照样报为私密条目 —— 浏览器记录没必要回传。

退出码：0 = 没发现私密条目；1 = 有（会逐条列出来）。

输出一律用 **GBK 编得出的字符**（`[OK] [X] [!] [i] [注意]`，中文字符本身 GBK 都有）：
中文 Windows 的控制台默认是 GBK，`✅ ❌ ⚠ ✓ ✗ 🔄` 这类**一 print 就抛
`UnicodeEncodeError`**（`make_package.py` 就这么崩过）。别在输出里加这类字符。
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

# 这些**文件名**出现在发布包里一定有问题
SENSITIVE_NAMES = {
    "cookies", "cookies-journal", "login data", "login data for account",
    "history", "history-journal", "web data", "web data-journal",
    "local state", "top sites", "shortcuts", "favicons", "quota manager",
    "affiliation database", "autofill", "autofillai", "visits",
}
# 这些**路径段**出现在发布包里一定有问题（userdata 整目录不算 —— 见 EXPECTED 规则）
EXCLUDE_PARTS = {
    "edge-profile", ".asset-cache", "browsermetrics", "gpucache",
    "shadercache", "grshadercache", "dawncache", "code cache",
    "local storage", "session storage", "service worker",
}
# 名字里像私密的文件后缀（浏览器配置文件、日志、崩溃转储）
SENSITIVE_SUFFIXES = {".log", ".pma", ".tmp", ".dat"}
# 误报白名单：工具箱/官方文档里合法提到这些词的文件名
NAME_ALLOWLIST = re.compile(
    r"(^|/)(uninstall\.ps1|install_exe\.ps1|build_green\.py|pack_exe\.py|"
    r"audit_package\.py|test_toolbox\.py|使用说明\.html|源码版说明\.txt|README\.md)$",
    re.IGNORECASE,
)
# 包根那个刻意放的占位说明（zip 里 userdata 目录要保持存在）
PLACEHOLDER_ALLOWLIST = re.compile(r"(^|/)userdata/[^/]*\.txt$", re.IGNORECASE)
# 有意包含 userdata 的产物（回传包）
RETURN_PACKAGE = re.compile(r"回传[-_].*\.zip$")


def classify(name: str, is_return_package: bool = False) -> tuple[str, str]:
    """给产物里的一个条目定性。

    返回 ("ok"|"expected"|"violation", 原因)。
    `is_return_package=True` 时 userdata 下的东西按**有意为之**算 ——
    回传包本来就是"把我的 userdata 打包发回给助手"。
    """
    entry = name.replace("\\", "/")
    parts = [p for p in entry.split("/") if p]
    basename = parts[-1].lower() if parts else ""

    # 0) 白名单：文档/脚本里出现这些词是正常的
    if NAME_ALLOWLIST.search(entry):
        return "ok", ""
    # 1) 包根的 userdata 占位说明：有意为之（zip 里那层 userdata/ 要保持存在）。
    #    位置不限深度：<包名>/userdata/xxx.txt 与 <包名>/userdata/xxx.txt 之外的
    #    userdata/<子目录>/xxx.txt 都不会命中 [^/]* 这一段。
    if PLACEHOLDER_ALLOWLIST.search(entry):
        return "expected", "userdata 目录占位说明"
    # 2) 浏览器配置目录 / 敏感名字：**先于** userdata 判定。
    #    这样即使是回传包，`userdata/edge-profile/...`、`Cookies` 这类浏览器记录也照样报出来
    #    （回传包只需要你的主题/预设/自定义角色，不需要浏览记录）。
    for part in parts[:-1]:
        if part.lower() in EXCLUDE_PARTS:
            return "violation", f"浏览器配置目录 {part}"
    for part in parts:
        if part.lower() in SENSITIVE_NAMES:
            return "violation", f"敏感名字 {part}"
    # 3) userdata 下的真实文件：回传包按设计含它，普通发布包则是漏了排除规则
    if any(part.lower() == "userdata" for part in parts[:-1]):
        if is_return_package:
            return "expected", "回传包：你的 userdata（按设计）"
        return "violation", "userdata 里的真实数据"
    # 4) 敏感后缀（日志/崩溃转储/缓存）
    suffix = Path(basename).suffix.lower()
    if suffix in SENSITIVE_SUFFIXES:
        return "violation", f"疑似日志/缓存 {basename}"
    return "ok", ""


def audit_zip(path: Path) -> list[tuple[str, str, str]]:
    """扫一个 zip，返回 [(条目, 定性, 原因), ...]（只含 expected / violation）。"""
    is_return = bool(RETURN_PACKAGE.search(path.name))
    findings: list[tuple[str, str, str]] = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue  # 目录项
            verdict, reason = classify(name, is_return)
            if verdict != "ok":
                findings.append((name, verdict, reason))
    return findings


def audit_dir(path: Path) -> list[tuple[str, str, str]]:
    """扫一个目录（PyInstaller 产物 / 解压出来的包）。"""
    is_return = bool(RETURN_PACKAGE.search(path.name))
    findings: list[tuple[str, str, str]] = []
    for item in sorted(path.rglob("*")):
        if not item.is_file() or "__pycache__" in item.parts:
            continue
        rel = item.relative_to(path).as_posix()
        verdict, reason = classify(rel, is_return)
        if verdict != "ok":
            findings.append((rel, verdict, reason))
    return findings


def targets(argv: list[str]) -> list[Path]:
    if argv:
        found = [Path(a) for a in argv]
        missing = [p for p in found if not p.exists()]
        if missing:
            raise SystemExit("找不到：" + "、".join(str(p) for p in missing))
        return found
    if not DIST.is_dir():
        raise SystemExit(f"没有 {DIST}：先打一次包（python make_package.py）再来体检")
    items = [p for p in sorted(DIST.iterdir()) if p.suffix.lower() == ".zip" or p.is_dir()]
    # dist/shots 是验收截图，不是发布产物
    return [p for p in items if p.name != "shots"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", help="要体检的 zip 或目录（默认扫 dist/）")
    parser.add_argument("--no-fail", action="store_true", help="只报告，命中也不返回非 0")
    args = parser.parse_args(argv)

    todo = targets(args.paths)
    if not todo:
        print("dist/ 里还没有 zip —— 先 python make_package.py（或 --green）打一份再来。")
        return 0

    violations: list[tuple[Path, str, str]] = []
    expected: list[tuple[Path, str, str]] = []
    reviews: list[Path] = []

    print("发布产物体检")
    print("=" * 60)
    for path in todo:
        artifact = path.name
        total_bytes = 0
        if path.is_dir():
            findings = audit_dir(path)
            files = [f for f in path.rglob("*") if f.is_file()]
            count = len(files)
            total_bytes = sum(f.stat().st_size for f in files)   # 目录条目本身是 0 字节，得自己累加
            kind = "目录"
        elif path.suffix.lower() == ".zip":
            findings = audit_zip(path)
            with zipfile.ZipFile(path) as zf:
                count = len([n for n in zf.namelist() if not n.endswith("/")])
            total_bytes = path.stat().st_size
            kind = "zip"
        else:
            print(f"  跳过（不认识）{artifact}")
            continue

        size = total_bytes / 1024 / 1024
        is_return = bool(RETURN_PACKAGE.search(artifact))
        if is_return:
            reviews.append(path)
        print(f"\n{artifact}  [{kind}]  {size:.2f} MB / {count} 个文件")
        if is_return:
            print("  [注意] 这是「回传包」：按设计就含你的 userdata，只该发回给助手，别当发布包发出去")

        bad = [f for f in findings if f[1] == "violation"]
        exp = [f for f in findings if f[1] == "expected"]
        if not findings:
            print("  [干净] 没有私密条目")
        for name, verdict, reason in findings[:20]:
            mark = "[!]" if verdict == "violation" else "[i]"
            print(f"  {mark} {name}  （{reason}）")
        if len(findings) > 20:
            print(f"  … 还有 {len(findings) - 20} 条")
        violations.extend((path, n, r) for n, v, r in bad)
        expected.extend((path, n, r) for n, v, r in exp)

    print("\n" + "=" * 60)
    if expected:
        reasons = sorted({reason for _, _, reason in expected})
        print(f"[i] 有意为之 {len(expected)} 条：{'；'.join(reasons)}")
    if reviews:
        print(f"[注意] 需要人看一眼 {len(reviews)} 个回传包：" + "、".join(p.name for p in reviews))
    if violations:
        print(f"[X] 发现 {len(violations)} 条私密条目 —— 这些产物不能发给别人：")
        for path, name, reason in violations[:30]:
            print(f"   {path.name} :: {name}  （{reason}）")
        return 0 if args.no_fail else 1
    print("[OK] 全部干净：发布产物里没有 userdata / 浏览器配置 / Cookies 之类的东西")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
