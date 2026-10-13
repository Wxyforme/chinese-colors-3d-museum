"""量 GLB 的世界包围盒 / 三角形数 / 内嵌贴图 —— 给 index.html 的 CASE_SPEC.lift 取值用。

用法：python -I tools/glb_info.py assets/models/*.glb

包围盒是**真读顶点缓冲**算出来的（不用访问器里的 min/max —— 那个只证明 JSON 没坏，
证明不了 BIN 块没被写坏），再按节点层级的 TRS 换算到世界空间。
Blender 导出的根节点带 X 轴 90° 四元数，所以访问器坐标不是最终朝向，必须换算。

顺带体检每个 bufferView / accessor 的字节区间是否落在 buffer 内 —— 重写过 BIN 块之后必跑。
"""
import io
import json
import struct
import sys

COMPONENT = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2), 5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def read_glb(path):
    data = open(path, 'rb').read()
    assert data[:4] == b'glTF', path
    off, js, bins = 12, None, b''
    while off < len(data):
        ln, ty = struct.unpack('<II', data[off:off + 8])
        body = data[off + 8:off + 8 + ln]
        if ty == 0x4E4F534A:
            js = json.loads(body)
        elif ty == 0x004E4942:
            bins = body
        off += 8 + ln
    assert js is not None, '没有 JSON 块'
    return js, bins


def accessor_values(js, bins, idx):
    """把 accessor 读成 [[分量...], ...]，按 byteStride 走。"""
    acc = js['accessors'][idx]
    bv = js['bufferViews'][acc['bufferView']]
    fmt, size = COMPONENT[acc['componentType']]
    n = NCOMP[acc['type']]
    stride = bv.get('byteStride') or size * n
    base = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
    out = []
    for i in range(acc['count']):
        o = base + i * stride
        out.append(struct.unpack_from('<' + fmt * n, bins, o))
    return out


def mat_mul(a, b):
    return [sum(a[i * 4 + k] * b[k * 4 + j] for k in range(4)) for i in range(4) for j in range(4)]


def trs_matrix(node):
    t = node.get('translation', [0, 0, 0])
    r = node.get('rotation', [0, 0, 0, 1])
    s = node.get('scale', [1, 1, 1])
    x, y, z, w = r
    rot = [
        1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0,
        2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0,
        2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0,
        0, 0, 0, 1,
    ]
    m = [rot[i] * (s[i % 4] if i % 4 < 3 else 1) for i in range(16)]
    m[3], m[7], m[11] = t[0], t[1], t[2]
    return m


def xform(m, p):
    x, y, z = p
    return [m[0] * x + m[4] * y + m[8] * z + m[12],
            m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14]]


def check_ranges(js, bins):
    """accessor 的字节区间必须落在自己的 bufferView 里，bufferView 必须落在 buffer 里。"""
    problems = []
    for i, bv in enumerate(js['bufferViews']):
        if bv.get('byteOffset', 0) + bv['byteLength'] > len(bins):
            problems.append('bufferView[%d] 越界' % i)
    for i, acc in enumerate(js['accessors']):
        bv = js['bufferViews'][acc['bufferView']]
        fmt, size = COMPONENT[acc['componentType']]
        need = acc.get('byteOffset', 0) + (acc['count'] - 1) * (bv.get('byteStride') or size * NCOMP[acc['type']]) + size * NCOMP[acc['type']]
        if need > bv['byteLength']:
            problems.append('accessor[%d] 超出 bufferView' % i)
    return problems


def report(path):
    js, bins = read_glb(path)
    lo, hi, tris = [1e9] * 3, [-1e9] * 3, 0

    def walk(idx, parent):
        nonlocal tris
        node = js['nodes'][idx]
        m = mat_mul(parent, trs_matrix(node))
        if 'mesh' in node:
            for prim in js['meshes'][node['mesh']]['primitives']:
                for p in accessor_values(js, bins, prim['attributes']['POSITION']):
                    w = xform(m, p)
                    for k in range(3):
                        lo[k], hi[k] = min(lo[k], w[k]), max(hi[k], w[k])
                tris += js['accessors'][prim['indices']]['count'] // 3
        for c in node.get('children', []):
            walk(c, m)

    ident = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    for n in js['scenes'][js.get('scene', 0)]['nodes']:
        walk(n, ident)

    size = [hi[k] - lo[k] for k in range(3)]
    imgs = []
    for im in js.get('images', []):
        bv = js['bufferViews'][im['bufferView']]
        tag = im.get('mimeType', '?').split('/')[-1]
        try:  # 真解一次，确认贴图字节没被写坏
            from PIL import Image
            w, h = Image.open(io.BytesIO(bins[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']])).size
            tag += ' %dx%d' % (w, h)
        except Exception as exc:
            tag += ' 解析失败:%s' % exc
        imgs.append('%s %dKB' % (tag, bv['byteLength'] // 1024))

    bad = check_ranges(js, bins)
    print('%-11s %.3f x %.3f x %.3f  面 %d  %s%s' % (
        path.split('/')[-1][:-4], size[0], size[1], size[2], tris, ', '.join(imgs),
        '  ⚠ ' + '；'.join(bad) if bad else '  OK'))
    return not bad


if __name__ == '__main__':
    ok = all([report(p) for p in sys.argv[1:]])
    sys.exit(0 if ok else 1)
