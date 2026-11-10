/**
 * 乐选优品 · 悬浮客服组件（小乐）
 *
 * 为什么要嵌到商城页面里，而不是单独一个页面：
 * 1. 用户已经登录了，不该再登一次 → token 直接读商城存在 sessionStorage 里的那个
 * 2. 页面在 18080，接口走 nginx 的 /api 反代到网关 8080，同源，不涉及跨域
 * 3. 客服是"随时能叫出来"的东西，应该是个悬浮球，不该打断用户浏览
 */
(function () {
  "use strict";

  const API = "/api";                          // nginx: /api/xxx -> 网关 /xxx
  const TOKEN_KEY = "token";                   // 商城的 axios 拦截器就读这个
  const CONV_KEY = "ai_conversation_id";        // 会话 id，刷新页面还能续上

  const TOOL_LABEL = {
    search_items: "搜索商品",
    query_my_orders: "查询订单",
    get_order_detail: "查订单详情",
    search_knowledge: "查售后政策",
    create_ticket: "创建工单",
  };

  let convId = sessionStorage.getItem(CONV_KEY) || null;
  let busy = false;

  // ==================== 样式 ====================
  const CSS = `
  .lx-ball {
    position: fixed; right: 24px; bottom: 24px; z-index: 9998;
    width: 58px; height: 58px; border-radius: 50%; border: none;
    background: linear-gradient(135deg, #4f7cff, #6f5cff);
    color: #fff; font-size: 13px; cursor: pointer;
    box-shadow: 0 6px 20px rgba(79, 124, 255, .45);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    line-height: 1.1; font-family: -apple-system, "Microsoft YaHei", sans-serif;
  }
  .lx-ball span:first-child { font-size: 18px; }

  .lx-panel {
    position: fixed; right: 24px; bottom: 94px; z-index: 9999;
    width: 360px; height: 540px; max-height: 78vh;
    background: #fff; border-radius: 16px; overflow: hidden;
    box-shadow: 0 12px 40px rgba(0, 0, 0, .18);
    display: flex; flex-direction: column;
    font-family: -apple-system, "Microsoft YaHei", sans-serif;
  }
  .lx-panel.lx-hidden { display: none; }

  .lx-head {
    padding: 12px 14px; color: #fff;
    background: linear-gradient(135deg, #4f7cff, #6f5cff);
    display: flex; align-items: center; gap: 10px;
  }
  .lx-head .lx-logo {
    width: 30px; height: 30px; border-radius: 50%;
    background: rgba(255,255,255,.24); display: grid; place-items: center; font-size: 13px;
  }
  .lx-head h3 { margin: 0; font-size: 14px; font-weight: 600; }
  .lx-head p { margin: 1px 0 0; font-size: 11px; opacity: .85; }
  .lx-close {
    margin-left: auto; background: none; border: none; color: #fff;
    font-size: 18px; cursor: pointer; opacity: .85; line-height: 1;
  }

  .lx-body {
    flex: 1; overflow-y: auto; padding: 12px; background: #fafbfc;
    display: flex; flex-direction: column; gap: 10px;
  }

  .lx-row { display: flex; gap: 8px; align-items: flex-start; }
  .lx-row.user { flex-direction: row-reverse; }
  .lx-avatar {
    width: 26px; height: 26px; border-radius: 50%; flex: 0 0 26px;
    display: grid; place-items: center; font-size: 11px; color: #fff;
  }
  .lx-row.assistant .lx-avatar { background: #6f5cff; }
  .lx-row.user .lx-avatar { background: #9aa4b8; }

  .lx-bubble {
    max-width: 76%; padding: 9px 12px; border-radius: 12px;
    font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word;
  }
  .lx-row.assistant .lx-bubble { background: #fff; border: 1px solid #eceef2; border-top-left-radius: 4px; }
  .lx-row.user .lx-bubble { background: #4f7cff; color: #fff; border-top-right-radius: 4px; }

  .lx-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
  .lx-chip { font-size: 10px; color: #5b6b8f; background: #eef2fb; border-radius: 20px; padding: 2px 8px; }

  .lx-dots span {
    display: inline-block; width: 5px; height: 5px; margin-right: 3px;
    border-radius: 50%; background: #b3bccd; animation: lxBlink 1.2s infinite;
  }
  .lx-dots span:nth-child(2) { animation-delay: .2s; }
  .lx-dots span:nth-child(3) { animation-delay: .4s; }
  @keyframes lxBlink { 0%,60%,100% { opacity: .25; } 30% { opacity: 1; } }

  .lx-confirm {
    border: 1px solid #ffd8a8; background: #fffaf2; border-radius: 12px;
    padding: 10px 12px; max-width: 78%; margin-left: 34px;
  }
  .lx-confirm .lx-title { font-size: 12px; color: #b26a00; font-weight: 600; margin-bottom: 5px; }
  .lx-confirm .lx-summary { font-size: 13px; color: #333; line-height: 1.6; }
  .lx-confirm .lx-actions { display: flex; gap: 8px; margin-top: 9px; }
  .lx-confirm button {
    flex: 1; padding: 7px; border-radius: 8px; font-size: 12px; cursor: pointer;
    border: 1px solid transparent;
  }
  .lx-confirm .lx-ok { background: #4f7cff; color: #fff; }
  .lx-confirm .lx-no { background: #fff; color: #666; border-color: #dcdfe6; }

  .lx-foot { border-top: 1px solid #eceef2; padding: 9px 10px; background: #fff; }
  .lx-input { display: flex; gap: 7px; align-items: flex-end; }
  .lx-input textarea {
    flex: 1; resize: none; border: 1px solid #e3e5ea; border-radius: 9px;
    padding: 8px 10px; font-size: 13px; font-family: inherit; outline: none; max-height: 76px;
  }
  .lx-input textarea:focus { border-color: #4f7cff; }
  .lx-input button {
    width: 50px; height: 36px; border: none; border-radius: 9px;
    background: #4f7cff; color: #fff; font-size: 13px; cursor: pointer;
  }
  .lx-input button:disabled { background: #b9c4e2; cursor: default; }
  .lx-hint { font-size: 11px; color: #e0455a; margin-top: 5px; min-height: 14px; }
  `;

  // ==================== 网络 ====================
  async function api(path, body) {
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) throw new Error("请先登录商城账号");

    const res = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": token },
      body: JSON.stringify(body || {}),
    });

    let data = null;
    try { data = await res.json(); } catch (_) {}

    if (!res.ok) {
      if (res.status === 401) {
        sessionStorage.removeItem(TOKEN_KEY);
        throw new Error("登录已过期，请重新登录");
      }
      throw new Error((data && data.detail) || "服务开小差了，稍后再试");
    }
    return data;
  }

  // ==================== DOM 小工具 ====================
  const $ = (id) => document.getElementById(id);
  const body = () => $("lx-body");

  function addMsg(role, text) {
    const row = document.createElement("div");
    row.className = "lx-row " + role;

    const avatar = document.createElement("div");
    avatar.className = "lx-avatar";
    avatar.textContent = role === "user" ? "我" : "乐";

    const bubble = document.createElement("div");
    bubble.className = "lx-bubble";

    const content = document.createElement("div");
    content.textContent = text || "";
    bubble.appendChild(content);

    row.append(avatar, bubble);
    body().appendChild(row);
    scrollDown();
    return content;
  }

  function scrollDown() {
    const b = body();
    b.scrollTop = b.scrollHeight;
  }

  function typewriter(node, text, speed) {
    return new Promise((resolve) => {
      node.textContent = "";
      let i = 0;
      const timer = setInterval(() => {
        node.textContent += text[i] || "";
        i++;
        scrollDown();
        if (i >= text.length) { clearInterval(timer); resolve(); }
      }, speed || 18);
    });
  }

  function thinking() {
    const content = addMsg("assistant", "");
    content.innerHTML = '<span class="lx-dots"><span></span><span></span><span></span></span>';
    const row = content.closest(".lx-row");
    return { close: () => row.remove() };
  }

  function showChips(node, trace) {
    if (!trace || !trace.length) return;
    const names = [...new Set(trace.filter((t) => t.tool).map((t) => TOOL_LABEL[t.tool] || t.tool))];
    if (!names.length) return;
    const box = document.createElement("div");
    box.className = "lx-chips";
    names.forEach((n) => {
      const chip = document.createElement("span");
      chip.className = "lx-chip";
      chip.textContent = "⚙ " + n;
      box.appendChild(chip);
    });
    node.closest(".lx-bubble").appendChild(box);
  }

  function showConfirm(info) {
    const card = document.createElement("div");
    card.className = "lx-confirm";
    card.innerHTML =
      '<div class="lx-title"></div><div class="lx-summary"></div>' +
      '<div class="lx-actions"><button class="lx-ok">确认</button><button class="lx-no">取消</button></div>';
    card.querySelector(".lx-title").textContent = info.title || "需要确认";
    card.querySelector(".lx-summary").textContent = info.summary || "";
    card.querySelector(".lx-ok").onclick = () => { card.remove(); decide(true); };
    card.querySelector(".lx-no").onclick = () => { card.remove(); decide(false); };
    body().appendChild(card);
    scrollDown();
  }

  // ==================== 主流程 ====================
  async function send() {
    if (busy) return;
    const box = $("lx-input");
    const text = box.value.trim();
    if (!text) return;

    if (!sessionStorage.getItem(TOKEN_KEY)) {
      addMsg("assistant", "你还没登录哦，登录后就能帮你查订单、办售后啦～");
      return;
    }

    addMsg("user", text);
    box.value = "";
    $("lx-hint").textContent = "";
    busy = true;
    $("lx-send").disabled = true;
    const dots = thinking();

    try {
      const data = await api("/ai/chat", { message: text, conversation_id: convId });
      convId = data.conversation_id;
      sessionStorage.setItem(CONV_KEY, convId);
      dots.close();

      if (data.status === "need_confirm") {
        const el = addMsg("assistant", "");
        await typewriter(el, "这个操作需要你确认一下：");
        showConfirm(data.confirm);
        showChips(el, data.trace);
      } else {
        const el = addMsg("assistant", "");
        await typewriter(el, data.answer || "（这条我没答上来）");
        showChips(el, data.trace);
      }
    } catch (e) {
      dots.close();
      $("lx-hint").textContent = e.message;
    } finally {
      busy = false;
      $("lx-send").disabled = false;
      box.focus();
    }
  }

  async function decide(approved) {
    const dots = thinking();
    try {
      const data = await api("/ai/chat/confirm", { conversation_id: convId, approved: approved });
      dots.close();
      const el = addMsg("assistant", "");
      await typewriter(el, data.answer || "好的");
    } catch (e) {
      dots.close();
      $("lx-hint").textContent = e.message;
    }
  }

  // ==================== 初始化 ====================
  function build() {
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);

    const ball = document.createElement("button");
    ball.className = "lx-ball";
    ball.innerHTML = "<span>乐</span><span>客服</span>";
    ball.onclick = () => {
      const panel = $("lx-panel");
      panel.classList.toggle("lx-hidden");
      if (!panel.classList.contains("lx-hidden") && !panel.dataset.greeted) {
        panel.dataset.greeted = "1";
        addMsg("assistant", "你好，我是小乐～商品、订单、退换货都可以问我。");
      }
    };

    const panel = document.createElement("div");
    panel.className = "lx-panel lx-hidden";
    panel.id = "lx-panel";
    panel.innerHTML =
      '<div class="lx-head">' +
        '<div class="lx-logo">乐</div>' +
        "<div><h3>小乐 · 智能客服</h3><p>乐选优品</p></div>" +
        '<button class="lx-close" title="关闭">×</button>' +
      "</div>" +
      '<div class="lx-body" id="lx-body"></div>' +
      '<div class="lx-foot">' +
        '<div class="lx-input">' +
          '<textarea id="lx-input" rows="1" placeholder="比如：我的订单到哪了"></textarea>' +
          '<button id="lx-send">发送</button>' +
        "</div>" +
        '<div class="lx-hint" id="lx-hint"></div>' +
      "</div>";

    document.body.appendChild(ball);
    document.body.appendChild(panel);

    panel.querySelector(".lx-close").onclick = () => panel.classList.add("lx-hidden");
    $("lx-send").onclick = send;
    $("lx-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
