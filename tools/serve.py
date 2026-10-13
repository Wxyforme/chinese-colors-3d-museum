#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""传统古色 · 3D 博物馆 —— 本地静态服务器（带 no-cache 头）。

为什么不能直接用 `python -m http.server`：
  它不发 Cache-Control，浏览器于是启用「启发式缓存」——把「Last-Modified 距今时长的 10%」
  当作新鲜期。改完 index.html 后即使刷新、甚至重启浏览器，也可能一直在吃旧缓存，
  看起来就像「改了代码没生效」。本脚本重写 end_headers() 补上 no-store，
  改完直接刷新浏览器即可看到。

用法：
  python tools/serve.py [端口]        # 默认 8899，只绑 127.0.0.1
（由根目录的 启动服务器.bat 调用，一般不需要手动跑。）

退出码：端口被占用时打印一行可读提示并以 1 退出，而不是抛一长串 traceback。
"""
import functools
import os
import socket
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# 以「本文件所在目录的上级」为站点根 —— 双击 .bat 时工作目录可能是任意位置
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8899
if len(sys.argv) > 1:
    try:
        PORT = int(sys.argv[1])
    except ValueError:
        sys.stderr.write('端口必须是数字，收到：%r\n' % (sys.argv[1],))
        sys.exit(2)
HOST = '127.0.0.1'


def _setup_stdio():
    """让本脚本的中文输出对齐**控制台当前代码页**。

    否则会出现这种坑：`启动服务器.bat` 里 `chcp 936` 把控制台设成 GBK，
    而 Python 的 stdio 编码并不跟着走 —— 它取 locale / LANG / PYTHONUTF8。
    实测从 Git Bash（带 `LANG=en_US.UTF-8`）双击 .bat 时，Python 按 UTF-8 吐出中文，
    控制台按 GBK 解读 → 窗口里全是「绔欑偣鏍圭洰褰」这种乱码。
    直接照着控制台的代码页写，两种启动方式都不会乱。
    """
    if os.name != 'nt':
        return
    try:
        import ctypes
        cp = ctypes.windll.kernel32.GetConsoleOutputCP()
    except Exception:
        return
    if not cp:
        return          # 没有控制台（如 pythonw 启动）→ 保持 Python 默认的 UTF-8
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='cp%d' % cp, errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


class NoCacheHandler(SimpleHTTPRequestHandler):
    """静态文件 + 强制不缓存。"""

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, fmt, *args):
        # 默认会把每一行都带上日期，本地调试用不上；保留状态码与路径即可
        sys.stderr.write('  %s\n' % (fmt % args))


def main():
    _setup_stdio()

    # Windows 上 SO_REUSEADDR 会让两个进程同时绑定同一端口，导致「旧服务器还在跑、
    # 新服务器以为起来了」—— 这里先显式探测一次，把冲突摆到明面上。
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((HOST, PORT))
    except OSError:
        sys.stderr.write(
            '\n  [x] 端口 %d 已被占用 —— 多半是上一次的服务器窗口还开着。\n'
            '      关掉那个黑色窗口（或 taskkill 占用进程）后重试。\n'
            '      查占用：netstat -ano | findstr ":%d" | findstr LISTENING\n\n'
            % (PORT, PORT))
        sys.exit(1)
    finally:
        probe.close()

    handler = functools.partial(NoCacheHandler, directory=ROOT)
    httpd = ThreadingHTTPServer((HOST, PORT), handler)
    sys.stderr.write('\n  站点根目录：%s\n' % ROOT)
    sys.stderr.write('  服务已启动：http://%s:%d/\n' % (HOST, PORT))
    sys.stderr.write('  按 Ctrl+C 或直接关闭本窗口即可停止。\n\n')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write('\n  已停止。\n')
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
