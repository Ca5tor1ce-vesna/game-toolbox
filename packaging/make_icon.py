"""用代码画工具箱图标（速度表 / 时钟），输出多尺寸 .ico 和一张 256px 的 png。

    python packaging/make_icon.py

只依赖 Pillow。图案：深色圆角方块底 + 金色表盘刻度 + 指针 + 左侧三道速度线。
先在 1024px 上画，再按每个尺寸单独缩小（小尺寸加粗线条，免得糊成一团）。
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
SIZES = [16, 24, 32, 48, 64, 128, 256]

BG_TOP = (30, 34, 48)
BG_BOTTOM = (14, 16, 22)
GOLD = (232, 184, 75)
VIOLET = (124, 108, 240)
WHITE = (236, 238, 244)


def draw(size: int = 1024, bold: float = 1.0) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # 圆角方块 + 竖向渐变
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        color = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)) + (255,)
        gd.line([(0, y), (s, y)], fill=color)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    cx, cy, r = s * 0.56, s * 0.56, s * 0.34

    # 表盘外圈（270° 弧，左下留口）
    w = max(2, int(s * 0.055 * bold))
    d.arc([cx - r, cy - r, cx + r, cy + r], start=135, end=405, fill=GOLD, width=w)

    # 刻度
    for i in range(9):
        a = math.radians(135 + i * 270 / 8)
        inner = r * (0.70 if i % 2 == 0 else 0.78)
        outer = r * 0.88
        tw = max(1, int(s * (0.03 if i % 2 == 0 else 0.018) * bold))
        d.line(
            [(cx + inner * math.cos(a), cy + inner * math.sin(a)), (cx + outer * math.cos(a), cy + outer * math.sin(a))],
            fill=WHITE if i < 7 else GOLD,
            width=tw,
        )

    # 指针（指向高速区）+ 轴心
    a = math.radians(135 + 270 * 0.78)
    nl = r * 0.78
    nw = max(2, int(s * 0.045 * bold))
    d.line([(cx, cy), (cx + nl * math.cos(a), cy + nl * math.sin(a))], fill=GOLD, width=nw)
    hub = s * 0.06 * max(1.0, bold * 0.9)
    d.ellipse([cx - hub, cy - hub, cx + hub, cy + hub], fill=WHITE)

    # 左边三道速度线
    lw = max(2, int(s * 0.04 * bold))
    for k, (y, length) in enumerate([(0.30, 0.20), (0.42, 0.14), (0.54, 0.09)]):
        x0 = s * 0.10
        d.line([(x0, s * y), (x0 + s * length, s * y)], fill=VIOLET if k else GOLD, width=lw)
        d.ellipse([x0 - lw / 2, s * y - lw / 2, x0 + lw / 2, s * y + lw / 2], fill=VIOLET if k else GOLD)
    return img


def render(size: int) -> Image.Image:
    # 小尺寸线条加粗；先在 8 倍尺寸上画再缩小，边缘更顺
    bold = 1.0 if size >= 64 else (1.4 if size >= 32 else 1.8)
    big = draw(size * 8 if size < 128 else 1024, bold=bold)
    small = big.resize((size, size), Image.LANCZOS)
    if size <= 32:
        small = small.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=1))
    return small


def main() -> None:
    images = [render(size) for size in SIZES]
    ico = HERE / "toolbox.ico"
    images[-1].save(ico, format="ICO", sizes=[(n, n) for n in SIZES], append_images=images[:-1])
    images[-1].save(HERE / "toolbox-256.png")
    # 预览图：所有尺寸排一排
    sheet = Image.new("RGBA", (sum(SIZES) + 8 * (len(SIZES) + 1), 256 + 16), (40, 40, 40, 255))
    x = 8
    for im in images:
        sheet.paste(im, (x, 8 + 256 - im.height), im)
        x += im.width + 8
    sheet.save(HERE / "icon-preview.png")
    print(f"已生成 {ico}（{', '.join(str(n) for n in SIZES)} px）")


if __name__ == "__main__":
    main()
