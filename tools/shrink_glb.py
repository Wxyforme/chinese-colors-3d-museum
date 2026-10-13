"""把 .glb 内嵌的 4096² PNG baseColorTexture 重编码成 1024² JPEG，重写 BIN 块。

用法：python -I tools/shrink_glb.py [-q 92] [-s 1024] assets/models/*.glb

为什么：GitHub Pages 对本站大文件限速到约 35KB/s，15MB 的 GLB 下 3 分钟只走 6.3MB，
访客会在「加载页收起」后看到一个缺器物的展厅。体积 99% 在贴图上，网格 3 万面只有约 0.7MB。
展厅内器物归一化后最大边长 1.15 世界单位、视距 2.4 单位以上，1024² 远超实际可见分辨率。

只动 images[].bufferView 指向的那一段字节：其余 bufferView 原样搬运，
accessor → bufferView 的索引不变，故网格与三角形数逐字节不变。
"""
import argparse
import io
import json
import struct
import sys

from PIL import Image

JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


def parse(data):
    magic, ver, _ = struct.unpack('<4sII', data[:12])
    assert magic == b'glTF' and ver == 2, '不是 glTF 2.0 二进制'
    js, bin_, off = None, b'', 12
    while off < len(data):
        ln, ty = struct.unpack('<II', data[off:off + 8])
        body = data[off + 8:off + 8 + ln]
        if ty == JSON_CHUNK:
            js = json.loads(body)
        elif ty == BIN_CHUNK:
            bin_ = body
        off += 8 + ln
    return js, bin_


def pack(js, bin_):
    jb = json.dumps(js, separators=(',', ':')).encode()
    jb += b' ' * (-len(jb) % 4)
    bb = bin_ + b'\x00' * (-len(bin_) % 4)
    total = 12 + 8 + len(jb) + (8 + len(bb) if bb else 0)
    out = struct.pack('<4sII', b'glTF', 2, total)
    out += struct.pack('<II', len(jb), JSON_CHUNK) + jb
    if bb:
        out += struct.pack('<II', len(bb), BIN_CHUNK) + bb
    return out


def shrink(path, size, quality, apply):
    raw = open(path, 'rb').read()
    js, bin_ = parse(raw)
    img_views = {im['bufferView']: im for im in js.get('images', []) if 'bufferView' in im}
    if not img_views:
        print('%-11s 无内嵌贴图，跳过' % path.split('/')[-1])
        return None

    before = sum(js['bufferViews'][k]['byteLength'] for k in img_views)
    new_views, new_bin = [], bytearray()
    for i, bv in enumerate(js['bufferViews']):
        src = bin_[bv.get('byteOffset', 0): bv.get('byteOffset', 0) + bv['byteLength']]
        if i in img_views:
            im = Image.open(io.BytesIO(src)).convert('RGB')
            orig_size = im.size
            if max(orig_size) > size:
                im = im.resize((size, size), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, 'JPEG', quality=quality, optimize=True, subsampling=0)
            src = buf.getvalue()
            img_views[i]['mimeType'] = 'image/jpeg'
        while len(new_bin) % 4:
            new_bin += b'\x00'
        new_views.append(dict(bv, byteOffset=len(new_bin), byteLength=len(src)))
        new_bin += src

    js['bufferViews'] = new_views
    js['buffers'][0]['byteLength'] = len(new_bin)
    out = pack(js, bytes(new_bin))

    if apply:
        with open(path, 'wb') as fh:
            fh.write(out)

    after = sum(new_views[k]['byteLength'] for k in img_views)
    print('%-11s 贴图 %.1fMB -> %.0fKB   文件 %.1fMB -> %.1fMB%s' % (
        path.split('/')[-1], before / 1048576, after / 1024,
        len(raw) / 1048576, len(out) / 1048576, '' if apply else '  [dry-run]'))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('-s', '--size', type=int, default=1024)
    ap.add_argument('-q', '--quality', type=int, default=92)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    for p in a.paths:
        shrink(p, a.size, a.quality, not a.dry_run)


if __name__ == '__main__':
    main()
