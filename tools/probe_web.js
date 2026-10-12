// 用 CDP 驱动无头 Chrome 做交互验证（网页版侧边收条）
const http = require("http");
const { spawn } = require("child_process");
const WebSocket = globalThis.WebSocket;   // Node 22 已内置，无需 ws 依赖
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9334;
// 每次探测用全新 profile：避免上一次留下的 localStorage 影响「初始状态」判定
const PROF = (process.env.TEMP ? process.env.TEMP.replace(/\\/g, "/") : "C:/Windows/Temp")
  + "/cdpprof_moyu_" + Date.now();
const proc = spawn(CHROME, [`--remote-debugging-port=${PORT}`, "--headless=new",
  "--disable-gpu", "--no-first-run", `--user-data-dir=${PROF}`, "about:blank"],
  { stdio: "ignore" });
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const get = (p) => new Promise((res, rej) => {
  http.get({ host: "127.0.0.1", port: PORT, path: p }, r => {
    let d = ""; r.on("data", c => d += c); r.on("end", () => res(JSON.parse(d)));
  }).on("error", rej);
});

(async () => {
  let list = null;
  for (let i = 0; i < 60; i++) {
    try {
      const r = await get("/json/list");
      if (r && r.length) { list = r; break; }
    } catch (e) {}
    await sleep(300);
  }
  if (!list || !list.length) { console.error("无法连接无头 Chrome（端口被占或启动失败）"); proc.kill(); process.exit(1); }
  const wsUrl = list.find(t => t.type === "page").webSocketDebuggerUrl;
  const ws = new WebSocket(wsUrl);
  let id = 0; const pend = {};
  ws.addEventListener("message", ev0 => {
    const j = JSON.parse(ev0.data);
    if (j.id && pend[j.id]) { pend[j.id](j); delete pend[j.id]; }
  });
  const send = (method, params) => new Promise(r => { const i = ++id; pend[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
  await new Promise(r => ws.addEventListener("open", r));
  await send("Page.enable"); await send("Runtime.enable");

  const ev = (expr) => send("Runtime.evaluate", { expression: expr, returnByValue: true })
    .then(r => (r.result && r.result.result) ? r.result.result.value : null);

  const dir = process.cwd().split("\\").join("/");
  await send("Page.navigate", { url: "file:///" + dir + "/index.html" });
  await sleep(1800);

  console.log("--- 初始（应保持展开，不能自动收起）---");
  console.log("dockOn       =", await ev("window.__moyu.S.dockOn"));
  console.log("docked       =", await ev("window.__moyu.docked()"));
  console.log("宽度          =", await ev("window.__moyu.w()"));
  console.log("贴左边(left)  =", await ev("window.__moyu.win.getBoundingClientRect().left"));
  await sleep(1400);
  console.log("--- 空闲 1.4s 后（仍未碰过鼠标 -> 应保持展开）---");
  console.log("docked       =", await ev("window.__moyu.docked()"));
  console.log("有 docked 类  =", await ev('window.__moyu.win.classList.contains("docked")'));
  console.log("宽度          =", await ev("window.__moyu.w()"));
  console.log("hook 可见     =", await ev('getComputedStyle(document.getElementById("dockHook")).display'));
  console.log("窗口 opacity  =", await ev('getComputedStyle(window.__moyu.win).opacity'));

  const r = JSON.parse(await ev("JSON.stringify(window.__moyu.win.getBoundingClientRect())"));
  await send("Input.dispatchMouseEvent", { type: "mouseMoved",
    x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) });
  await sleep(500);
  console.log("--- 鼠标移入（激活 + 展开）---");
  console.log("armed        =", await ev("window.__moyu.armed ? window.__moyu.armed() : 'n/a'"));
  console.log("docked       =", await ev("window.__moyu.docked()"));
  console.log("宽度          =", await ev("window.__moyu.w()"));

  // 移到一个既不在窗口里、也不在左缘收条热区里的位置（屏幕右下方）
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 900, y: 640 });
  await sleep(200);
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 901, y: 641 });
  await sleep(1600);
  console.log("--- 鼠标移出 1.6s（已激活 -> 应再收起）---");
  console.log("docked       =", await ev("window.__moyu.docked()"));
  console.log("宽度          =", await ev("window.__moyu.w()"));
  console.log("贴左边(left)  =", await ev("window.__moyu.win.getBoundingClientRect().left"));
  console.log("hook 可见     =", await ev('getComputedStyle(document.getElementById("dockHook")).display'));

  // 鼠标碰一下左边那条细缝 -> 应重新展开
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 2, y: 300 });
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 3, y: 301 });
  await sleep(500);
  console.log("--- 鼠标碰左缘细缝（应重新展开）---");
  console.log("docked       =", await ev("window.__moyu.docked()"));
  console.log("宽度          =", await ev("window.__moyu.w()"));

  console.log("--- 按 E 关闭收条 ---");
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "e", code: "KeyE", windowsVirtualKeyCode: 69 });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: "e", code: "KeyE", windowsVirtualKeyCode: 69 });
  await sleep(300);
  console.log("dockOn       =", await ev("window.__moyu.S.dockOn"));
  console.log("docked       =", await ev("window.__moyu.docked()"));
  console.log("宽度          =", await ev("window.__moyu.w()"));
  console.log("hook 可见     =", await ev('getComputedStyle(document.getElementById("dockHook")).display'));

  ws.close(); proc.kill(); process.exit(0);
})().catch(e => { console.error("ERR", e.message); try { proc.kill(); } catch (_) {} process.exit(1); });
