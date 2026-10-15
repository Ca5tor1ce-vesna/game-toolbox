"""模块与功能的自动发现。

目录即注册表：

    modules/
      <游戏>/
        manifest.json            必需：id / name / icon / version ...
        data/*.json              可选：这个游戏的数据（角色、卡池参数……）
        features/
          <功能>/
            feature.json         必需：id / name / icon / order ...
            api.py               可选：后端动作（@api 注册）
            ui.js                可选：前端界面（export default { mount })
            style.css            可选：这个功能自己的样式

扫描规则：目录名以 `.` 或 `_` 开头的会被忽略（方便放草稿和旧版本）。
任何一层出错都只记录到 errors，不影响其它模块加载。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config


@dataclass
class Feature:
    module_id: str
    module_folder: str
    folder: str
    id: str
    name: str
    icon: str = "•"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    order: int = 100
    ui_file: str = "ui.js"
    api_file: str = "api.py"
    dir: Path | None = None
    module_dir: Path | None = None

    @property
    def base_url(self) -> str:
        return f"/modules/{self.module_folder}/features/{self.folder}"

    def to_dict(self, actions: list[str] | None = None) -> dict[str, Any]:
        has_ui = bool(self.dir and (self.dir / self.ui_file).is_file())
        has_api = bool(self.dir and (self.dir / self.api_file).is_file())
        has_style = bool(self.dir and (self.dir / "style.css").is_file())
        return {
            "moduleId": self.module_id,
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
            "tags": list(self.tags),
            "order": self.order,
            "baseUrl": self.base_url,
            "uiUrl": f"{self.base_url}/{self.ui_file}" if has_ui else None,
            "styleUrl": f"{self.base_url}/style.css" if has_style else None,
            "hasUi": has_ui,
            "hasApi": has_api,
            "actions": list(actions or []),
        }


@dataclass
class Module:
    id: str
    folder: str
    name: str
    icon: str = "🎮"
    version: str = "0.0.0"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    accent: str = ""
    game_version: str = ""
    data_dir: Path | None = None
    dir: Path | None = None
    features: list[Feature] = field(default_factory=list)
    order: int = 100  # 侧边栏里的顺序，可被 userdata 的「外壳覆盖」改写

    def data_files(self) -> list[str]:
        if not self.data_dir or not self.data_dir.is_dir():
            return []
        return sorted(p.stem for p in self.data_dir.glob("*.json"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "folder": self.folder,
            "name": self.name,
            "icon": self.icon,
            "version": self.version,
            "gameVersion": self.game_version,
            "description": self.description,
            "tags": list(self.tags),
            "accent": self.accent,
            "dataFiles": self.data_files(),
            "features": [f.to_dict() for f in self.features],
        }


def _order(value: Any, errors: list[dict[str, Any]], where: Path) -> int:
    """order 写错（如 "top"）只记一条警告、按 100 排，不能让整个扫描失败。"""
    try:
        return int(value or 100)
    except (TypeError, ValueError):
        errors.append({"scope": where.name, "error": f"order 需要是整数，收到 {value!r}，按 100 处理"})
        return 100


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} 的顶层必须是一个 JSON 对象")
    return data


def _scan_features(module: Module, errors: list[dict[str, Any]]) -> None:
    assert module.dir is not None
    features_dir = module.dir / "features"
    if not features_dir.is_dir():
        return
    for fdir in sorted(p for p in features_dir.iterdir() if p.is_dir()):
        if fdir.name.startswith((".", "_")):
            continue
        meta_path = fdir / "feature.json"
        scope = f"{module.folder}/{fdir.name}"
        if not meta_path.is_file():
            errors.append({"scope": scope, "error": "缺少 feature.json，已跳过该目录"})
            continue
        try:
            meta = _read_json(meta_path)
        except Exception as exc:
            errors.append(
                {
                    "scope": scope,
                    "file": str(meta_path),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        raw_tags = meta.get("tags") or []
        # feature.json 里写了 "hidden": true 的功能不加载（作者包除外）——
        # 用来把没做完或不打算给用户看的功能藏起来。
        if meta.get("hidden") and not config.is_admin():
            continue

        feature = Feature(
            module_id=module.id,
            module_folder=module.folder,
            folder=fdir.name,
            id=str(meta.get("id") or fdir.name),
            name=str(meta.get("name") or fdir.name),
            icon=str(meta.get("icon") or "•"),
            description=str(meta.get("description") or ""),
            tags=[str(t) for t in raw_tags] if isinstance(raw_tags, list) else [],
            order=_order(meta.get("order"), errors, fdir),
            ui_file=str(meta.get("ui") or "ui.js"),
            api_file=str(meta.get("api") or "api.py"),
            dir=fdir,
            module_dir=module.dir,
        )
        if not (fdir / feature.ui_file).is_file() and not (fdir / feature.api_file).is_file():
            errors.append(
                {
                    "scope": scope,
                    "error": f"既没有 {feature.ui_file} 也没有 {feature.api_file}，界面会是空的",
                }
            )
        module.features.append(feature)
    module.features.sort(key=lambda f: (f.order, f.name))


def scan(root: Path | None = None) -> tuple[list[Module], list[dict[str, Any]]]:
    """扫描 modules/ 目录，返回 (模块列表, 错误列表)。"""
    root = Path(root) if root else config.MODULES_DIR
    modules: list[Module] = []
    errors: list[dict[str, Any]] = []

    if not root.is_dir():
        errors.append({"scope": "modules", "error": f"模块目录不存在：{root}"})
        return modules, errors

    for mdir in sorted(p for p in root.iterdir() if p.is_dir()):
        if mdir.name.startswith((".", "_")):
            continue
        manifest_path = mdir / "manifest.json"
        if not manifest_path.is_file():
            errors.append({"scope": mdir.name, "error": "缺少 manifest.json，已跳过该目录"})
            continue
        try:
            meta = _read_json(manifest_path)
        except Exception as exc:
            errors.append(
                {
                    "scope": mdir.name,
                    "file": str(manifest_path),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        # manifest 里标了 adminOnly 的模块只有「后门」打开时才出现（默认关，见 config.is_admin）。
        # 发给别人的包里这类模块**根本不会被打进去**，所以对方连开的办法都没有。
        if meta.get("adminOnly") and not config.is_admin():
            continue

        raw_tags = meta.get("tags") or []
        module = Module(
            id=str(meta.get("id") or mdir.name),
            folder=mdir.name,
            name=str(meta.get("name") or mdir.name),
            icon=str(meta.get("icon") or "🎮"),
            version=str(meta.get("version") or "0.0.0"),
            description=str(meta.get("description") or ""),
            tags=[str(t) for t in raw_tags] if isinstance(raw_tags, list) else [],
            accent=str(meta.get("accent") or ""),
            game_version=str(meta.get("gameVersion") or ""),
            data_dir=mdir / "data",
            dir=mdir,
        )
        _scan_features(module, errors)
        modules.append(module)

    return apply_overrides(modules), errors


def apply_overrides(modules: list[Module]) -> list[Module]:
    """把「外壳覆盖」应用到扫描结果上：功能改名 / 隐藏 / 调整顺序。

    覆盖文件：userdata/shell-overrides.json（由「界面 → 功能与文字」写入）。
    结构：
        {
          "labels": { "module:<模块id>": {"name": "...", "icon": "🚄"},
                      "<模块id>/<功能id>": {"name": "...", "icon": "🎯", "description": "..."} },
          "hidden": ["<模块id>/<功能id>", "module:<模块id>"],
          "order":  { "<模块id>/<功能id>": 5, "module:<模块id>": 2 }
        }
    只做「读」；文件缺失或字段不对都不报错（覆盖坏了也不能让程序起不来）。
    """
    overrides = config.load_overrides()
    labels = overrides.get("labels") if isinstance(overrides.get("labels"), dict) else {}
    hidden = set(overrides.get("hidden") or [])
    order = overrides.get("order") if isinstance(overrides.get("order"), dict) else {}

    kept: list[Module] = []
    for module in modules:
        module_key = f"module:{module.id}"
        if module_key in hidden:
            continue
        patch = labels.get(module_key) if isinstance(labels.get(module_key), dict) else {}
        if patch.get("name"):
            module.name = str(patch["name"])
        if patch.get("icon"):
            module.icon = str(patch["icon"])

        features: list[Feature] = []
        for feature in module.features:
            feature_key = f"{module.id}/{feature.id}"
            if feature_key in hidden:
                continue
            feature_patch = (
                labels.get(feature_key) if isinstance(labels.get(feature_key), dict) else {}
            )
            if feature_patch.get("name"):
                feature.name = str(feature_patch["name"])
            if feature_patch.get("icon"):
                feature.icon = str(feature_patch["icon"])
            if feature_patch.get("description"):
                feature.description = str(feature_patch["description"])
            if feature_key in order:
                try:
                    feature.order = int(order[feature_key])
                except (TypeError, ValueError):
                    pass
            features.append(feature)

        features.sort(key=lambda item: (item.order, item.name))
        module.features = features
        if module_key in order:
            try:
                module.order = int(order[module_key])
            except (TypeError, ValueError):
                pass
        if features:
            kept.append(module)

    kept.sort(key=lambda item: (item.order, item.name))
    return kept


def find(modules: list[Module], module_id: str) -> Module | None:
    for module in modules:
        if module.id == module_id or module.folder == module_id:
            return module
    return None
