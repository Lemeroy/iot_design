(() => {
  "use strict";

  const POLLING_MS = 5000;
  const views = {
    login: document.querySelector("#login-view"),
    connect: document.querySelector("#connect-view"),
    monitor: document.querySelector("#monitor-view"),
  };
  const statusMessage = document.querySelector("#status-message");
  const liveMessage = document.querySelector("#live-message");
  const focusTargets = {
    login: "#username",
    connect: "#device-id",
    monitor: "#refresh-button",
  };
  const fields = {
    device: document.querySelector("#connected-device"),
    online: document.querySelector("#online-state"),
    indicator: document.querySelector("#online-indicator"),
    receipt: document.querySelector("#receipt-time"),
    riskPanel: document.querySelector("#risk-panel"),
    riskTitle: document.querySelector("#risk-title"),
    riskCopy: document.querySelector("#risk-copy"),
    reasons: document.querySelector("#reason-list"),
    vetoes: document.querySelector("#veto-list"),
    advice: document.querySelector("#advice-text"),
    adviceSource: document.querySelector("#advice-source"),
    adviceTime: document.querySelector("#advice-time"),
  };
  const scoreFields = { face: "face", speech: "speech", tongue: "tongue", eye: "eye", csi: "csi", final: "final" };
  let pollTimer = null;
  let activeView = "login";

  function setStatus(message) { statusMessage.textContent = message; }

  function announce(message) { liveMessage.textContent = message; }

  function report(message) {
    setStatus(message);
    announce(message);
  }

  function showView(name) {
    activeView = name;
    Object.entries(views).forEach(([viewName, element]) => { element.hidden = viewName !== name; });
    const focusSelector = focusTargets[name];
    const target = focusSelector ? document.querySelector(focusSelector) : null;
    if (target) target.focus();
  }

  function formatTime(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "--";
    const milliseconds = value < 100000000000 ? value * 1000 : value;
    return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "medium", hour12: false }).format(new Date(milliseconds));
  }

  function makeList(element, values, emptyText) {
    element.replaceChildren();
    const entries = Array.isArray(values) && values.length ? values : [emptyText];
    entries.forEach((value) => {
      const item = document.createElement("li");
      item.textContent = String(value);
      element.append(item);
    });
  }

  function scoreValue(value) { return Number.isFinite(value) ? String(value) : "未接入"; }

  function levelContent(level) {
    const content = {
      normal: ["正常", "当前风险提示为正常，请继续留意身体变化。"],
      warning: ["警示", "当前出现风险提示，建议及时寻求医疗评估。"],
      danger: ["危险", "危险风险提示：请立即拨打 120 并寻求紧急医疗帮助。"],
      insufficient: ["数据不足", "当前数据不足，不能形成风险提示。"],
    };
    return content[level] || content.insufficient;
  }

  function renderDevice(data) {
    const scores = data && data.scores ? data.scores : {};
    Object.entries(scoreFields).forEach(([name, id]) => { document.querySelector(`#score-${id}`).textContent = scoreValue(scores[name]); });
    fields.device.textContent = data.device_id || "--";
    const online = data.online === true;
    fields.online.textContent = online ? "在线" : "离线";
    fields.indicator.className = `indicator ${online ? "online" : "offline"}`;
    fields.receipt.textContent = formatTime(data.received_at);
    const [title, copy] = levelContent(data.level);
    fields.riskPanel.className = `risk-panel level-${data.level || "insufficient"}`;
    fields.riskTitle.textContent = title;
    fields.riskCopy.textContent = copy;
    makeList(fields.reasons, data.reasons, "未接入");
    makeList(fields.vetoes, data.veto_by, "无");
    const advice = data.advice;
    fields.advice.textContent = advice && advice.advice_text ? advice.advice_text : "尚未收到建议。";
    fields.adviceSource.textContent = advice && advice.source ? advice.source : "--";
    fields.adviceTime.textContent = advice ? formatTime(advice.ts) : "--";
  }

  async function request(path, options = {}) {
    const response = await fetch(path, { credentials: "same-origin", headers: { "content-type": "application/json" }, ...options });
    let body = null;
    try { body = await response.json(); } catch (_) { /* A bounded status message is enough for an invalid response. */ }
    if (!response.ok) {
      const error = new Error(body && body.detail ? body.detail : "请求失败");
      error.status = response.status;
      throw error;
    }
    return body;
  }

  async function pollDevice() {
    if (activeView !== "monitor") return;
    try {
      const data = await request("/demo/api/device");
      renderDevice(data);
      setStatus("监测数据已更新");
    } catch (error) {
      if (error.status === 401) { showView("login"); report("会话已结束，请重新登录"); return; }
      if (error.status === 409) { showView("connect"); report("设备连接已断开"); return; }
      report("本次更新失败，将在 5 秒后自动重试");
    }
  }

  async function restoreSession() {
    try {
      const session = await request("/demo/api/session");
      if (session.device_id) {
        showView("monitor");
        await pollDevice();
      } else {
        showView("connect");
        report("请输入设备 ID 连接监测数据");
      }
    } catch (_) {
      showView("login");
      report("请登录后连接设备");
    }
  }

  document.querySelector("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await request("/demo/api/login", { method: "POST", body: JSON.stringify({ username: form.get("username"), password: form.get("password") }) });
      event.currentTarget.reset();
      showView("connect");
      report("登录成功，请连接设备");
    } catch (_) { report("登录失败，请检查用户名和密码"); }
  });

  document.querySelector("#connect-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const deviceId = new FormData(event.currentTarget).get("device_id");
    try {
      const session = await request("/demo/api/connect", { method: "POST", body: JSON.stringify({ device_id: deviceId }) });
      showView("monitor");
      fields.device.textContent = session.device_id;
      report("设备已连接，正在同步监测数据");
      await pollDevice();
    } catch (error) { report(error.status === 409 ? "设备当前离线" : "无法连接该设备"); }
  });

  document.querySelector("#refresh-button").addEventListener("click", pollDevice);
  document.querySelector("#disconnect-button").addEventListener("click", async () => {
    try { await request("/demo/api/disconnect", { method: "POST" }); showView("connect"); report("设备已断开"); }
    catch (_) { report("断开失败，请重试"); }
  });
  async function handleLogout() {
    try {
      await request("/demo/api/logout", { method: "POST" });
      showView("login");
      report("已退出登录");
    } catch (error) {
      if (error.status === 401) { showView("login"); report("会话已结束，请重新登录"); return; }
      report("退出失败，请重试");
    }
  }
  document.querySelectorAll("[data-logout]").forEach((button) => {
    button.addEventListener("click", handleLogout);
  });

  restoreSession();
  pollTimer = window.setInterval(pollDevice, 5000);
  window.addEventListener("beforeunload", () => window.clearInterval(pollTimer));
})();
