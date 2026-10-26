(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const bridge = window.AstrBotPluginPage || window.AstrBotPluginView;

  async function api(path, options) {
    if (!bridge) throw new Error("页面桥接未加载，请从 AstrBot 插件页打开");
    const method = String((options && options.method) || "GET").toUpperCase();
    let body = {};
    if (options && options.body) {
      try {
        body = JSON.parse(options.body);
      } catch (_) {
        body = {};
      }
    }
    let data;
    if (method === "GET") {
      data = await bridge.apiGet(path, {});
    } else {
      data = await bridge.apiPost(path, body);
    }
    if (!data || data.ok === false) {
      const message = (data && (data.message || data.error)) || "请求失败";
      throw new Error(String(message));
    }
    return data;
  }

  function toast(message, kind) {
    const el = $("em-toast");
    el.textContent = message;
    el.dataset.kind = kind || "ok";
    el.classList.add("show");
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => el.classList.remove("show"), 2600);
  }

  function hint(message, kind) {
    const el = $("em-hint");
    el.textContent = message;
    el.dataset.kind = kind || "";
  }

  function setText(id, value) {
    const el = $(id);
    if (el) el.textContent = value == null ? "-" : String(value);
  }

  function applyStatus(status) {
    setText("em-enabled", status.enabled ? "已启用" : "已停用");
    setText("em-market", status.station_only ? status.station_label : `星域 ${status.region_id}`);
    setText("em-cache", (status.stats && status.stats.cached_prices) || 0);
    setText("em-items-count", (status.stats && status.stats.items) || 0);
    $("em-field-enabled").checked = Boolean(status.enabled);
    $("em-field-commands").value = (status.commands || []).join(",");
    $("em-field-station-only").checked = Boolean(status.station_only);
    $("em-field-region").value = status.region_id;
    $("em-field-station").value = status.station_id;
    $("em-field-cache").value = status.cache_ttl;
    $("em-field-pages").value = status.max_pages;
    if (status.last_error) hint(`上次错误：${status.last_error}`, "bad");
    else hint("运行正常。", "ok");
  }

  async function loadStatus() {
    hint("正在读取插件状态…");
    try {
      applyStatus(await api("status"));
    } catch (error) {
      hint(`读取状态失败：${error.message}`, "bad");
    }
  }

  async function saveSettings(event) {
    event.preventDefault();
    const payload = {
      enabled: $("em-field-enabled").checked,
      command_names: $("em-field-commands").value.trim(),
      station_only: $("em-field-station-only").checked,
      region_id: Number($("em-field-region").value),
      station_id: Number($("em-field-station").value),
      cache_ttl: Number($("em-field-cache").value),
      max_pages: Number($("em-field-pages").value),
    };
    try {
      await api("settings/save", { method: "POST", body: JSON.stringify(payload) });
      toast("设置已保存");
      await loadStatus();
    } catch (error) {
      toast(`保存失败：${error.message}`, "bad");
    }
  }

  async function runTest(event) {
    event.preventDefault();
    const query = $("em-test-input").value.trim();
    if (!query) return;
    const out = $("em-test-result");
    out.textContent = "查询中…";
    try {
      const data = await api("test", { method: "POST", body: JSON.stringify({ query }) });
      out.textContent = data.reply || "（无结果）";
    } catch (error) {
      out.textContent = `查询失败：${error.message}`;
    }
  }

  async function clearCache() {
    if (!window.confirm("清空所有报价缓存？")) return;
    try {
      await api("cache/clear", { method: "POST", body: "{}" });
      toast("缓存已清空");
      await loadStatus();
    } catch (error) {
      toast(`清空失败：${error.message}`, "bad");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("em-settings").addEventListener("submit", saveSettings);
    $("em-test-form").addEventListener("submit", runTest);
    $("em-clear-cache").addEventListener("click", clearCache);
    $("em-refresh").addEventListener("click", loadStatus);
    $("em-save").addEventListener("click", () => $("em-settings").requestSubmit());
    (async () => {
      try {
        if (bridge && typeof bridge.ready === "function") await bridge.ready();
      } catch (_) {
        // The bridge may already be ready; continue with the API calls.
      }
      loadStatus();
    })();
  });
})();
