本目录放配乐。路径写在 index.html 的 ASSETS.bgm / ASSETS.painting.audio。

  bgm.mp3  —— 馆内环境配乐，也是观画视图的配乐（一首共用）。已置入。
              1.03 MB / 90 秒 / 96 kbps 立体声。

⚠️ 两个 <audio> 都是 preload="none"，**页面加载时不会去取这个文件**：
   馆内那首在「观众第一次点击画面」时才开始下载（备好即起播、循环）；
   观画那首在「打开观画视图」时才下载。
   这是故意的 —— 线上带宽被限速（实测单流 20~60 KB/s），配乐若跟 8 个模型抢管子，
   会让加载遮罩晚解除好几分钟（实测同带宽下 478 秒 → 800 秒）。改回 preload="auto"
   就把这个优化抵消掉了，别改。

换成别的曲子：把新文件按同样的文件名放进本目录即可，不用改代码。
  换一首不同的观画配乐：把 ASSETS.painting.audio 改成一个新文件名，再把该文件也放进本目录。

—— 当前这首 ——
《高山流水》，古琴曲。母带 8.0 MB / 210 秒 / 320 kbps 立体声，
放在 ../../.workbuddy/_src/audio/（gitignore，不发布、不拖慢 GitHub Pages）。

本目录的 bgm.mp3 = 从母带**取前 90 秒、重编码成 96 kbps**：

    ffmpeg -i "../../.workbuddy/_src/audio/高山流水.mp3" -t 90 -map_metadata 0 \
           -c:a libmp3lame -b:a 96k -ac 2 -ar 44100 bgm.mp3

本机没有系统级 ffmpeg，用的是 imageio-ffmpeg 自带的那个
（`python -m pip install imageio-ffmpeg`，二进制在 Lib/site-packages/imageio_ffmpeg/binaries/）。

为什么不用「不重编码」的截断法：`tools/trim_mp3.py` 是零损失截断，但它保留原码率 ——
320 kbps 需要持续 40 KB/s 才播得动，而这条线路单流常只有 20~60 KB/s，会断续。
96 kbps 只要 12 KB/s，留足余量，体积也从 3.4 MB 降到 1.0 MB。
（trim_mp3.py 仍然有用：想保持原码率、只截短的时候用它。）
