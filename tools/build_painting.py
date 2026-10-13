"""把《月曼清游图》册十二开拼成两张展陈图。

用法：python -I tools/build_painting.py <十二开的目录> <输出目录>

产出（尺寸按 index.html 里两处画布的**像素尺寸原样**，贴上去一像素不缩放）：
  painting.jpg        2160 × 930  = 1440 × 620 的 1.5 倍  → 内厅主展墙画心（也作观画视图的大图）
  painting-wall.jpg   2048 × 470  = 序厅喷绘长墙的画心区   → 十二开横排长卷

两处画布都按「铺满」贴图，所以输出必须与画布同比例，否则会被二次裁切。

十二开的文件名按月份序号给：01.jpg ~ 12.jpg（正月…十二月）。
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

# 装裱底色 —— 取自十二开扫描件四边的中位色（约 210,178,148），比画心浅一档
MOUNT = (206, 176, 146)
MOUNT_EDGE = (188, 156, 124)

# 主展墙：6 列 × 2 行，正好是 2.3226:1（1440:620）
GRID_W, GRID_H, COLS, ROWS = 2160, 930, 6, 2
GRID_M, GRID_GAP = 18, 12

# 序厅长墙：十二开横排，画心区 4.357:1（2048:470）
WALL_W, WALL_H, WALL_M, WALL_GAP = 2048, 470, 16, 6


def mount_bg(w, h):
    """素色绢地：上深下浅的竖向渐变，模拟旧裱绫的褪色方向。"""
    bg = Image.new('RGB', (w, h))
    d = ImageDraw.Draw(bg)
    for y in range(h):
        k = min(1.0, y / max(1, h - 1) * 3)
        d.line([(0, y), (w, y)],
               fill=tuple(int(MOUNT_EDGE[i] + (MOUNT[i] - MOUNT_EDGE[i]) * k) for i in range(3)))
    return bg


def cover_fill(src, cw, ch):
    """按「铺满」缩放裁切 —— 与 index.html 里 canvas 贴图的算式同口径。"""
    iw, ih = src.size
    s = max(cw / iw, ch / ih)
    if s > 1.02:                       # 低分辨率的几开要放大，事后补一次锐化
        src = src.resize((round(iw * s), round(ih * s)), Image.LANCZOS)
        src = src.filter(ImageFilter.UnsharpMask(radius=1.6, percent=68, threshold=3))
        iw, ih = src.size
    else:
        src = src.resize((max(cw, round(iw * s)), max(ch, round(ih * s))), Image.LANCZOS)
        iw, ih = src.size
    left = (iw - cw) // 2
    top = (ih - ch) // 2
    return src.crop((left, top, left + cw, top + ch))


def build_grid(leaves, out):
    cw = (GRID_W - 2 * GRID_M - (COLS - 1) * GRID_GAP) // COLS
    ch = (GRID_H - 2 * GRID_M - (ROWS - 1) * GRID_GAP) // ROWS
    canvas = mount_bg(GRID_W, GRID_H)
    for i, im in enumerate(leaves):
        if im is None:
            continue
        r, c = divmod(i, COLS)
        x = GRID_M + c * (cw + GRID_GAP)
        y = GRID_M + r * (ch + GRID_GAP)
        canvas.paste(cover_fill(im, cw, ch), (x, y))
        ImageDraw.Draw(canvas).rectangle([x - 1, y - 1, x + cw, y + ch], outline=(150, 118, 88))
    canvas.save(out, 'JPEG', quality=88, optimize=True, subsampling=1, progressive=True)
    print('%-20s %d×%d  %dKB  （每开 %d×%d）' % (os.path.basename(out), GRID_W, GRID_H,
                                             os.path.getsize(out) // 1024, cw, ch))


def build_wall(leaves, out):
    cw = (WALL_W - 2 * WALL_M - 11 * WALL_GAP) // 12
    ch = round(cw / ((GRID_W - 2 * GRID_M - 5 * GRID_GAP) / COLS
                     / ((GRID_H - 2 * GRID_M - GRID_GAP) / ROWS)))
    y0 = (WALL_H - ch) // 2
    canvas = mount_bg(WALL_W, WALL_H)
    for i, im in enumerate(leaves):
        if im is None:
            continue
        x = WALL_M + i * (cw + WALL_GAP)
        canvas.paste(cover_fill(im, cw, ch), (x, y0))
        ImageDraw.Draw(canvas).rectangle([x - 1, y0 - 1, x + cw, y0 + ch], outline=(150, 118, 88))
    canvas.save(out, 'JPEG', quality=88, optimize=True, subsampling=1, progressive=True)
    print('%-20s %d×%d  %dKB  （每开 %d×%d，上下各有 %dpx 绫边）' % (
        os.path.basename(out), WALL_W, WALL_H, os.path.getsize(out) // 1024, cw, ch, y0))


def main(src_dir, out_dir):
    leaves = []
    for i in range(1, 13):
        p = os.path.join(src_dir, '%02d.jpg' % i)
        leaves.append(Image.open(p).convert('RGB') if os.path.exists(p) else None)
        if leaves[-1] is None:
            print('  ⚠ 缺 %s' % p)
    os.makedirs(out_dir, exist_ok=True)
    build_grid(leaves, os.path.join(out_dir, 'painting.jpg'))
    build_wall(leaves, os.path.join(out_dir, 'painting-wall.jpg'))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
