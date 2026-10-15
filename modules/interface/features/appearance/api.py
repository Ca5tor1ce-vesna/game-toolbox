"""外观与排版：把主题设置存进 userdata，界面启动时读取并应用。

设计要点
--------
* **只允许改白名单里的东西**：颜色必须是合法色值、数字必须落在范围内、文字有长度上限。
  这些值最终会变成页面上的 CSS 变量与文本，不校验就等于让用户往自己页面里注入任意 CSS。
* 主题里**只存用户改过的键**（其余留给 style.css 的默认值），
  这样以后我改了默认配色，用户没动过的部分会自动跟着变新。
* 存成 userdata/interface/theme.json，升级工具箱时不会丢。
"""

from __future__ import annotations

import re
from typing import Any

from core.feature_api import api

THEME_FILE = "theme"

# 颜色键 → 界面上显示的名字（同时也决定允许的键，多一个都不收）
COLOR_KEYS: dict[str, str] = {
    "bg": "页面背景",
    "panel": "卡片背景",
    "panel2": "次级背景（输入框/表格）",
    "border": "边框",
    "text": "正文文字",
    "muted": "次要文字",
    "accent": "强调色（主）",
    "accent2": "强调色（次）",
    "good": "成功/达标",
    "warn": "提醒",
    "bad": "警告/差一点",
}

# 字体与排版键 → (中文名, 最小值, 最大值, 单位, 属于哪一组)
NUMBER_KEYS: dict[str, tuple[str, float, float, str, str]] = {
    "baseSize": ("基础字号", 11, 22, "px", "fonts"),
    "lineHeight": ("行高倍数", 1.1, 2.4, "", "fonts"),
    "radius": ("圆角", 0, 24, "px", "layout"),
    "sidebarWidth": ("侧边栏宽度", 180, 420, "px", "layout"),
    "viewPadding": ("内容区留白", 0, 40, "px", "layout"),
    "cardPadding": ("卡片内边距", 6, 32, "px", "layout"),
}

TEXT_KEYS: dict[str, str] = {
    "brand": "工具箱标题",
    "searchPlaceholder": "搜索框提示",
}

MAX_TEXT_LENGTH = 40
COLOR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
# 字体名允许：字母数字空格，以及中文、逗号、引号、连字符、下划线
FONT_PATTERN = re.compile(r"^[\w\s,\"'\-.\u4e00-\u9fff]{1,120}$")

# 界面上的默认值（和 app/style.css 的 :root 保持一致；改这里要同步改 CSS）
DEFAULTS: dict[str, Any] = {
    "colors": {
        "bg": "#0e1015",
        "panel": "#161922",
        "panel2": "#1c2029",
        "border": "#262b37",
        "text": "#e6e8ee",
        "muted": "#8f97a8",
        "accent": "#e8b84b",
        "accent2": "#7c6cf0",
        "good": "#4ade80",
        "warn": "#fbbf24",
        "bad": "#f87171",
    },
    "fonts": {
        "sans": '"Microsoft YaHei UI", "Segoe UI", system-ui, sans-serif',
        "mono": '"Cascadia Mono", "JetBrains Mono", Consolas, "Courier New", monospace',
        "baseSize": 14,
        "lineHeight": 1.6,
    },
    "layout": {
        "radius": 10,
        "sidebarWidth": 268,
        "viewPadding": 18,
        "cardPadding": 16,
    },
    "text": {
        "brand": "游戏实用工具箱",
        "searchPlaceholder": "搜索功能…（配速 / 抽卡 / 伤害）",
    },
}

# 界面上的字体候选（用户也可以直接手填）
FONT_CHOICES: list[dict[str, str]] = [
    {"label": "微软雅黑（默认）", "value": '"Microsoft YaHei UI", "Segoe UI", system-ui, sans-serif'},
    {"label": "思源黑体 / Noto Sans SC", "value": '"Noto Sans SC", "Source Han Sans SC", "Microsoft YaHei UI", sans-serif'},
    {"label": "系统 UI 无衬线", "value": 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'},
    {"label": "等宽（Consolas）", "value": '"Cascadia Mono", Consolas, "Courier New", monospace'},
    {"label": "衬线（宋体/明体）", "value": '"Songti SC", "SimSun", "Noto Serif SC", serif'},
]


def _clean_color(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not COLOR_PATTERN.match(value):
        return None
    # 统一成小写，短写展开成长写，方便前端预览
    if len(value) == 4:
        value = "#" + "".join(char * 2 for char in value[1:])
    return value.lower()


def _clean_number(key: str, value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    _, low, high, _, _ = NUMBER_KEYS[key]
    if number != number or number in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return max(low, min(high, number))


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().replace("\n", " ").replace("\r", " ")
    if not text:
        return None
    return text[:MAX_TEXT_LENGTH]


def _clean_font(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    font = value.strip()
    if not font or not FONT_PATTERN.match(font):
        return None
    return font[:120]


def sanitize(theme: Any) -> dict[str, Any]:
    """白名单清洗：只留下认识的键，且值合法。"""
    if not isinstance(theme, dict):
        return {}
    out: dict[str, Any] = {}

    colors_in = theme.get("colors")
    if isinstance(colors_in, dict):
        colors = {}
        for key in COLOR_KEYS:
            cleaned = _clean_color(colors_in.get(key))
            if cleaned:
                colors[key] = cleaned
        if colors:
            out["colors"] = colors

    fonts_in = theme.get("fonts")
    fonts: dict[str, Any] = {}
    if isinstance(fonts_in, dict):
        for key in ("sans", "mono"):
            cleaned = _clean_font(fonts_in.get(key))
            if cleaned:
                fonts[key] = cleaned
        for key in ("baseSize", "lineHeight"):
            cleaned = _clean_number(key, fonts_in.get(key))
            if cleaned is not None:
                fonts[key] = cleaned
    if fonts:
        out["fonts"] = fonts

    layout_in = theme.get("layout")
    layout: dict[str, Any] = {}
    if isinstance(layout_in, dict):
        for key in ("radius", "sidebarWidth", "viewPadding", "cardPadding"):
            cleaned = _clean_number(key, layout_in.get(key))
            if cleaned is not None:
                layout[key] = cleaned
    if layout:
        out["layout"] = layout

    text_in = theme.get("text")
    text: dict[str, str] = {}
    if isinstance(text_in, dict):
        for key in TEXT_KEYS:
            cleaned = _clean_text(text_in.get(key))
            if cleaned:
                text[key] = cleaned
    if text:
        out["text"] = text

    return out


@api("load")
def load(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """读当前主题：只返回用户改过的键，界面自己与默认值合并。"""
    theme = sanitize(ctx.user_data(THEME_FILE, {}) or {})
    return {"theme": theme, "defaults": DEFAULTS, "fontChoices": FONT_CHOICES, "labels": {
        "colors": COLOR_KEYS,
        "numbers": {key: value[0] for key, value in NUMBER_KEYS.items()},
        "numbersMeta": {
            key: {"label": value[0], "min": value[1], "max": value[2], "unit": value[3], "group": value[4]}
            for key, value in NUMBER_KEYS.items()
        },
        "text": TEXT_KEYS,
    }}


@api("save")
def save(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """保存主题（白名单清洗后再落盘）。"""
    theme = sanitize(payload.get("theme") or {})
    path = ctx.save_user_data(THEME_FILE, theme)
    return {"theme": theme, "saved": True, "path": path}


@api("reset")
def reset(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """恢复默认：清空用户主题文件。"""
    path = ctx.save_user_data(THEME_FILE, {})
    return {"theme": {}, "saved": True, "path": path}
