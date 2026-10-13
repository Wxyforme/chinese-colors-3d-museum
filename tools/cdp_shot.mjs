/* 用 Chrome DevTools Protocol 驱动无头 Edge 截图 —— 比 `--screenshot` + `--virtual-time-budget`
   可靠得多：那个是「等虚拟时间跑完就拍」，而博物馆页面的 setAnimationLoop 永远不空闲，
   软件渲染下每帧又极慢，往往等不到出图就被拖死。

   这里改成「轮询一个表达式，为真了再拍」，拍摄时机由页面状态决定。

   用法：
     node tools/cdp_shot.mjs <url> <输出png> [就绪表达式] [超时秒] [摆位表达式]
   例：
     node tools/cdp_shot.mjs http://127.0.0.1:8899/index.html shot.png "window.__ready===true" 120
     CDP_VIEWPORT=1400x900 node tools/cdp_shot.mjs <url> out.png "window.__hook.ready()" 150 "window.__hook.look(0,1.7,32, 0,1.7,0)"

   ⚠️ 视口要用环境变量 CDP_VIEWPORT=宽x高 显式设，**别指望浏览器那边的 `--window-size`**：
      `--headless=new` 下它经常不生效，实测会拿到 500×320 的视口，出图又小又糊。
      这里走 Emulation.setDeviceMetricsOverride，稳。
   ⚠️ 环境变量 CDP_PORT 可改调试端口（默认 9222）；多个人/多个 agent 同时截图时各用一个端口。

   前置：另开一个窗口跑
     msedge --headless=new --remote-debugging-port=9222 --window-size=1400,900 about:blank
*/
const [, , url, out, readyExpr = 'true', timeoutS = '90', setupExpr = ''] = process.argv;
const PORT = process.env.CDP_PORT || 9222;
const VIEWPORT = (process.env.CDP_VIEWPORT || '').split('x').map(Number);
const DEADLINE = Date.now() + Number(timeoutS) * 1000;

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function target() {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      const page = list.find(t => t.type === 'page');
      if (page) return page.webSocketDebuggerUrl;
    } catch { /* 还没起来 */ }
    await sleep(500);
  }
  throw new Error('连不上 CDP 端口 ' + PORT);
}

const ws = new WebSocket(await target());
let id = 0;
const pending = new Map();

ws.addEventListener('message', ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === 'Runtime.consoleAPICalled') {
    const t = (m.params.args || []).map(a => a.value ?? a.description ?? '').join(' ');
    if (t) console.log('  [page]', t.slice(0, 300));
  }
  if (m.method === 'Runtime.exceptionThrown') {
    console.log('  [错误]', (m.params.exceptionDetails?.exception?.description || '').slice(0, 400));
  }
});
await new Promise(r => ws.addEventListener('open', r));

const send = (method, params = {}) => new Promise(res => {
  const n = ++id;
  pending.set(n, res);
  ws.send(JSON.stringify({ id: n, method, params }));
});

await send('Page.enable');
await send('Runtime.enable');
if (VIEWPORT.length === 2 && VIEWPORT.every(Number.isFinite)) {
  await send('Emulation.setDeviceMetricsOverride',
    { width: VIEWPORT[0], height: VIEWPORT[1], deviceScaleFactor: 1, mobile: false });
  console.log(`  视口 ${VIEWPORT[0]}×${VIEWPORT[1]}`);
}
await send('Page.navigate', { url });

let ok = false;
while (Date.now() < DEADLINE) {
  await sleep(1200);
  const r = await send('Runtime.evaluate', { expression: `!!(${readyExpr})`, returnByValue: true });
  if (r.result?.result?.value === true) { ok = true; break; }
}
console.log(ok ? '  就绪，截图…' : '  ⚠ 超时，仍按当前状态截图');

if (setupExpr) {
  const s = await send('Runtime.evaluate', { expression: setupExpr, returnByValue: true, awaitPromise: true });
  if (s.result?.exceptionDetails) console.log('  [摆位错误]', JSON.stringify(s.result.exceptionDetails).slice(0, 300));
  /* 摆完机位要留几帧让它真的画出来 —— 软件渲染很慢 */
  await sleep(Number(process.env.SHOT_SETTLE_MS || 4000));
}

const shot = await send('Page.captureScreenshot', { format: 'png' });
const { writeFileSync } = await import('node:fs');
writeFileSync(out, Buffer.from(shot.result.data, 'base64'));
console.log('  已保存', out, `(${Math.round(Buffer.from(shot.result.data, 'base64').length / 1024)}KB)`);
ws.close();
process.exit(ok ? 0 : 1);
