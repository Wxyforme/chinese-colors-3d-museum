"""从 MP3 里截一段出来（**帧对齐截断，不重编码**，所以零音质损失、无需 ffmpeg）。

用法：
    python -I tools/trim_mp3.py <输入.mp3> <输出.mp3> <起点秒> <时长秒>
例：
    python -I tools/trim_mp3.py "assets/audio/高山流水.mp3" "assets/audio/bgm.mp3" 0 90

为什么是「帧对齐」：MP3 是一条条独立可解码的帧首尾相接。只要在**帧边界**上切，
切出来的字节流本身就是一段合法 MP3，任何播放器/浏览器都能直接放 ——
不像重编码那样要把整段解成 PCM 再压回去（既掉音质、又得装 ffmpeg）。

保留源文件的 ID3v2 标签（标题/艺术家等）原样搬到输出，只是把音频帧截短。

⚠️ 为什么还要「修头帧」：LAME 编码的 MP3 第一帧通常不是音频，而是一个 Info/Xing 头帧，
   里面写着**整首曲子的帧数与字节数**，播放器拿它算总时长。只切字节不改它，播放器就会
   认为截出来的 90 秒有 210 秒长（进度条走不到头、总时长显示 3:30）。所以这里会把头帧里的
   帧数 / 字节数 / 跳转目录（TOC）和 LAME 标签里的「音乐总长」一并改成截断后的真实值。

体积参考：CBR 320kbps 立体声 ≈ 2.29 MB/分钟 —— 想再小只能重编码降码率。
"""
import io
import os
import sys

# MPEG 版本 → 采样率表；bitrate 索引 → kbps 表
SR_TAB = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}
BR_V1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
BR_V2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]


def parse(buf):
    """→ (id3v2 字节, [ (帧偏移, 帧长, 帧时长秒, 采样率) ... ])"""
    pos, tag = 0, b''
    if buf[:3] == b'ID3' and len(buf) > 10:
        size = ((buf[6] & 0x7F) << 21 | (buf[7] & 0x7F) << 14 |
                (buf[8] & 0x7F) << 7 | (buf[9] & 0x7F))
        pos, tag = 10 + size, buf[:10 + size]

    frames, i, n = [], pos, len(buf)
    while i < n - 4:
        if not (buf[i] == 0xFF and (buf[i + 1] & 0xE0) == 0xE0):
            i += 1                              # 没对齐上就往后挪一字节再试
            continue
        ver, layer = (buf[i + 1] >> 3) & 3, (buf[i + 1] >> 1) & 3
        if ver == 1 or layer != 1:              # 只认 MPEG1/2/2.5 Layer III
            i += 1
            continue
        bri, sri = (buf[i + 2] >> 4) & 0xF, (buf[i + 2] >> 2) & 3
        pad = (buf[i + 2] >> 1) & 1
        if bri in (0, 15) or sri == 3:
            i += 1
            continue
        br = (BR_V1 if ver == 3 else BR_V2)[bri]
        sr = SR_TAB[ver][sri]
        if br == 0:
            i += 1
            continue
        spf = 1152 if ver == 3 else 576         # Layer III 每帧采样数
        flen = (spf // 8) * br * 1000 // sr + pad
        if flen <= 4:
            i += 1
            continue
        frames.append((i, flen, spf / sr, sr))
        i += flen
    return tag, frames


def fix_head_frame(buf, head, tail, kept, total_audio):
    """截断后的第一帧若是 Info/Xing 头帧，就地把里面的长度信息改成真实值。
    返回 (是否改过, 该输出的字节)。"""
    off = head
    ver = (buf[off + 1] >> 3) & 3
    mono = (buf[off + 3] >> 6) == 3
    side = (17 if mono else 32) if ver == 3 else (9 if mono else 17)

    p = -1
    for magic in (b'Xing', b'Info'):        # 紧跟帧头 + 边信息，再往后就是魔数
        q = buf.find(magic, off + 4, off + 4 + side + 4)
        if q == off + 4 + side:
            p = q
            break
    if p < 0:
        return False, buf[head:tail]

    body = bytearray(buf[head:tail])
    q = p - head
    flags = int.from_bytes(body[q + 4:q + 8], 'big')
    n, old = q + 8, {}                       # 四个可选字段按位依次排布
    if flags & 1:
        old['帧数'] = int.from_bytes(body[n:n + 4], 'big')
        body[n:n + 4] = kept.to_bytes(4, 'big'); n += 4
    if flags & 2:
        old['字节'] = int.from_bytes(body[n:n + 4], 'big')
        body[n:n + 4] = total_audio.to_bytes(4, 'big'); n += 4
    if flags & 4:                            # 跳转目录：CBR 下按时间线性铺一遍即可
        for i in range(100):
            body[n + i] = round(255 * i / 100)
        n += 100
    if flags & 8:
        n += 4

    l = body.find(b'LAME', q, q + 200)       # LAME 标签偏移 27 处也是「音乐总长」
    if l >= 0 and l + 31 <= len(body):
        body[l + 27:l + 31] = total_audio.to_bytes(4, 'big')

    print('头帧已修：帧数 %s→%d，字节 %s→%d'
          % (old.get('帧数', '—'), kept, old.get('字节', '—'), total_audio))
    return True, bytes(body)


def main():
    if len(sys.argv) != 5:
        print(__doc__.strip())
        return 2
    src, dst = sys.argv[1], sys.argv[2]
    start, dur = float(sys.argv[3]), float(sys.argv[4])
    if start < 0 or dur <= 0:
        print('起点要 ≥ 0、时长要 > 0')
        return 2

    buf = io.open(src, 'rb').read()
    tag, frames = parse(buf)
    if not frames:
        print('没解析出任何 MP3 帧 —— 可能不是 Layer III，或文件损坏：', src)
        return 1

    total = sum(f[2] for f in frames)
    sr = frames[0][3]
    print('源  : %s  %.1f MB   %.1f 秒   %d Hz' %
          (os.path.basename(src), len(buf) / 1048576, total, sr))

    # 起点落在哪一帧
    t, i0 = 0.0, 0
    while i0 < len(frames) and t + frames[i0][2] <= start:
        t += frames[i0][2]
        i0 += 1
    if i0 >= len(frames):
        print('起点 %.1f 秒超出总时长 %.1f 秒' % (start, total))
        return 1

    # 从这一帧起凑够时长
    t, i1 = 0.0, i0
    while i1 < len(frames) and t < dur:
        t += frames[i1][2]
        i1 += 1

    got = sum(f[2] for f in frames[i0:i1])
    head, tail = frames[i0][0], frames[i1 - 1][0] + frames[i1 - 1][1]
    _, body = fix_head_frame(buf, head, tail, i1 - i0, tail - head)
    out = tag + body
    io.open(dst, 'wb').write(out)

    print('截取: 第 %d ~ %d 帧（共 %d 帧），起点 %.2f 秒，实际时长 %.2f 秒'
          % (i0, i1 - 1, i1 - i0, sum(f[2] for f in frames[:i0]), got))
    print('输出: %s  %.1f MB  （源 %.1f MB，压掉 %.0f%%）' %
          (os.path.basename(dst), len(out) / 1048576, len(buf) / 1048576,
           100 * (1 - len(out) / len(buf))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
