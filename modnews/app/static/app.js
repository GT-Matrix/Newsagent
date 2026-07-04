const state = {
  selectedTaskId: null,
  autoRefreshTimer: null,
  eventSource: null,
  maxFeedItems: 80,
};

document.addEventListener("DOMContentLoaded", () => {
  bindTabs();
  bindActions();
  connectEvents();
  refreshAll();
  setAutoRefresh(true);
});

function bindTabs() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((panel) => panel.classList.remove("active"));
      button.classList.add("active");
      document.querySelector(`.panel[data-panel="${button.dataset.tab}"]`).classList.add("active");
    });
  });
}

function bindActions() {
  document.getElementById("refresh-all").addEventListener("click", refreshAll);
  document.getElementById("clear-event-feed").addEventListener("click", () => renderEventFeed([]));
  document.getElementById("auto-refresh").addEventListener("change", (event) => {
    setAutoRefresh(Boolean(event.target.checked));
  });
  document.getElementById("drain-queue").addEventListener("click", async () => {
    await postJson("/api/queue/drain", {});
    await refreshQueue();
  });
  document.getElementById("clear-cache").addEventListener("click", async () => {
    await postJson("/api/cache/clear", { llm: true, embedding: true });
    await refreshArtifacts();
  });
  document.getElementById("restore-builtins").addEventListener("click", async () => {
    await postJson("/api/source-config/restore-builtins", {});
    await refreshConfig();
  });
  document.getElementById("queue-filter").addEventListener("change", refreshQueue);
  document.getElementById("run-form").addEventListener("submit", submitRun);
  document.getElementById("report-form").addEventListener("submit", submitReport);
}

function setAutoRefresh(enabled) {
  if (state.autoRefreshTimer) {
    clearInterval(state.autoRefreshTimer);
    state.autoRefreshTimer = null;
  }
  if (enabled) {
    state.autoRefreshTimer = setInterval(refreshAll, 5000);
  }
}

async function refreshAll() {
  await Promise.all([
    refreshOverview(),
    refreshRuns(),
    refreshQueue(),
    refreshWeb(),
    refreshConfig(),
    refreshArtifacts(),
  ]);
  document.getElementById("last-updated").textContent = `最近刷新 ${new Date().toLocaleTimeString()}`;
}

async function refreshOverview() {
  const [statePayload, queueStatus] = await Promise.all([
    getJson("/api/state"),
    getJson("/api/queue/status"),
  ]);
  const events = Array.isArray(statePayload.events) ? statePayload.events : [];
  const outputs = statePayload.outputs || {};
  const counts = queueStatus.counts || {};
  const cards = [
    ["事件总数", events.length],
    ["queued", counts.queued || 0],
    ["running", counts.running || 0],
    ["blocked", counts.blocked || 0],
    ["failed", counts.failed || 0],
    ["输出文件", Object.values(outputs).filter((item) => item && item.exists).length],
  ];
  document.getElementById("summary-cards").innerHTML = cards.map(([label, value]) => (
    `<article class="card"><span class="muted">${escapeHtml(String(label))}</span><strong>${escapeHtml(String(value))}</strong></article>`
  )).join("");
  renderEventFeed(events.slice(-20).reverse());
  const queueItems = await getQueueItems("");
  document.getElementById("recent-tasks").innerHTML = queueItems.slice(0, 8).map(renderTaskSummaryItem).join("") || empty("暂无任务");
}

async function refreshRuns() {
  const payload = await getJson("/api/runs");
  const items = Array.isArray(payload.items) ? payload.items : [];
  document.getElementById("runs-list").innerHTML = items.map(renderRunItem).join("") || empty("暂无运行记录");
  bindRunActions();
}

async function refreshQueue() {
  const filter = document.getElementById("queue-filter").value;
  const items = await getQueueItems(filter);
  const body = document.getElementById("queue-body");
  body.innerHTML = items.map((task) => `
    <tr data-task-id="${escapeAttr(task.id)}">
      <td>${escapeHtml(task.id)}</td>
      <td>${escapeHtml(task.type || "")}</td>
      <td>${escapeHtml(task.step_id || "")}</td>
      <td><span class="pill state-${escapeAttr(task.state || "unknown")}">${escapeHtml(task.state || "")}</span></td>
      <td>${escapeHtml(task.pipeline_run_id || "-")}</td>
      <td class="toolbar">
        <button class="button small queue-detail-btn" data-task-id="${escapeAttr(task.id)}" type="button">详情</button>
        <button class="button small queue-retry-btn" data-task-id="${escapeAttr(task.id)}" type="button">重试</button>
        <button class="button small queue-skip-btn" data-task-id="${escapeAttr(task.id)}" type="button">跳过</button>
        <button class="button small danger queue-cancel-btn" data-task-id="${escapeAttr(task.id)}" type="button">取消</button>
      </td>
    </tr>
  `).join("");
  bindQueueActions();
  if (state.selectedTaskId) {
    await showTaskDetail(state.selectedTaskId);
  }
}

async function refreshWeb() {
  const [extractorsPayload, jobsPayload, repairPayload] = await Promise.all([
    getJson("/api/extractors"),
    getJson("/api/web-jobs"),
    getJson("/api/repair-tasks"),
  ]);
  const extractors = Array.isArray(extractorsPayload.items) ? extractorsPayload.items : [];
  const jobs = Array.isArray(jobsPayload.items) ? jobsPayload.items : [];
  const repairs = Array.isArray(repairPayload.items) ? repairPayload.items : [];

  document.getElementById("extractors-list").innerHTML = extractors.map((item) => `
    <div class="list-item">
      <div class="list-item-head">
        <strong>${escapeHtml(item.source_id || item.id || "-")}</strong>
        <span class="pill">${escapeHtml(item.enabled ? "enabled" : "disabled")}</span>
      </div>
      <div class="muted">${escapeHtml(item.path || item.extractor_path || "")}</div>
      <div class="toolbar">
        <button class="button small extractor-toggle-btn" data-source-id="${escapeAttr(item.source_id || item.id)}" data-enabled="${String(!item.enabled)}" type="button">${item.enabled ? "禁用" : "启用"}</button>
        <button class="button small extractor-run-btn" data-source-id="${escapeAttr(item.source_id || item.id)}" type="button">运行</button>
      </div>
    </div>
  `).join("") || empty("暂无 extractor");

  document.getElementById("web-jobs-list").innerHTML = jobs.slice(0, 30).map((item) => `
    <div class="list-item">
      <div class="list-item-head">
        <strong>${escapeHtml(item.id || "-")}</strong>
        <span class="pill state-${escapeAttr(item.state || "unknown")}">${escapeHtml(item.state || "")}</span>
      </div>
      <div class="muted">${escapeHtml(item.source_id || "")} · ${escapeHtml(item.failure_reason || item.status_reason || "")}</div>
    </div>
  `).join("") || empty("暂无 web job");

  document.getElementById("repair-list").innerHTML = repairs.slice(0, 30).map((item) => `
    <div class="list-item">
      <div class="list-item-head">
        <strong>${escapeHtml(item.id || "-")}</strong>
        <span class="pill">${escapeHtml(item.state || "")}</span>
      </div>
      <div class="muted">${escapeHtml(item.source_id || "")} · ${escapeHtml(item.reason || "")}</div>
    </div>
  `).join("") || empty("暂无 repair task");

  bindWebActions();
}

async function refreshConfig() {
  const payload = await getJson("/api/runtime-config");
  const steps = payload.steps || {};
  const classification = payload.classification || {};
  const paths = payload.paths || {};
  const sources = payload.sources || {};

  renderStepsForm(steps);
  renderClassificationForm(classification);
  document.getElementById("paths-list").innerHTML = Object.entries(paths).map(([key, value]) => kvRow(key, String(value || ""))).join("") || empty("暂无路径信息");
  document.getElementById("sources-list").innerHTML = renderSources(sources);
  bindConfigActions();
}

async function refreshArtifacts() {
  const [outputs, cache, checkpointsPayload] = await Promise.all([
    getJson("/api/outputs"),
    getJson("/api/cache"),
    getJson("/api/checkpoints"),
  ]);
  document.getElementById("outputs-list").innerHTML = Object.entries(outputs).map(([key, value]) => renderOutputRow(key, value)).join("");
  document.getElementById("cache-list").innerHTML = Object.entries(cache).map(([key, value]) => kvRow(key, typeof value === "object" ? JSON.stringify(value) : String(value))).join("");
  const checkpoints = Array.isArray(checkpointsPayload.items) ? checkpointsPayload.items : [];
  document.getElementById("checkpoints-list").innerHTML = checkpoints.slice(-40).reverse().map((item) => `
    <div class="list-item">
      <div class="list-item-head">
        <strong>${escapeHtml(item.step_id || "-")}</strong>
        <span class="pill">${escapeHtml(item.run_id || "-")}</span>
      </div>
      <div class="muted">${escapeHtml(item.path || "")}</div>
      <div class="toolbar">
        <button class="button small checkpoint-publish-btn" data-path="${escapeAttr(item.path || "")}" type="button">发布到 output</button>
      </div>
    </div>
  `).join("") || empty("暂无 checkpoint");
  bindCheckpointActions();
}

function renderStepsForm(steps) {
  const host = document.getElementById("steps-form");
  host.innerHTML = Object.entries(steps).map(([stepId, config]) => {
    const fields = Object.entries(config || {}).map(([key, value]) => {
      if (typeof value === "boolean") {
        return `<label class="inline"><input data-step-id="${escapeAttr(stepId)}" data-key="${escapeAttr(key)}" type="checkbox" ${value ? "checked" : ""}>${escapeHtml(key)}</label>`;
      }
      return `<label>${escapeHtml(`${stepId}.${key}`)}<input data-step-id="${escapeAttr(stepId)}" data-key="${escapeAttr(key)}" value="${escapeAttr(Array.isArray(value) ? value.join(",") : String(value ?? ""))}"></label>`;
    }).join("");
    return `<div class="list-item">${fields}<div class="actions"><button class="button small step-save-btn" data-step-id="${escapeAttr(stepId)}" type="button">保存 ${escapeHtml(stepId)}</button></div></div>`;
  }).join("") || empty("暂无步骤配置");
}

function renderClassificationForm(config) {
  const host = document.getElementById("classification-form");
  host.innerHTML = Object.entries(config).map(([key, value]) => {
    if (typeof value === "boolean") {
      return `<label class="inline"><input data-classification-key="${escapeAttr(key)}" type="checkbox" ${value ? "checked" : ""}>${escapeHtml(key)}</label>`;
    }
    return `<label>${escapeHtml(key)}<input data-classification-key="${escapeAttr(key)}" value="${escapeAttr(String(value ?? ""))}"></label>`;
  }).join("") + `<div class="actions"><button id="classification-save" class="button small primary" type="button">保存 classification</button></div>`;
}

function renderSources(sources) {
  const rows = [];
  const rss = Array.isArray(sources.rss) ? sources.rss.map((row) => ({ ...row, source_type: "rss" })) : [];
  const newsnow = sources.newsnow && typeof sources.newsnow === "object"
    ? Object.entries(sources.newsnow).map(([id, row]) => ({ id, ...(row || {}), source_type: "newsnow" }))
    : [];
  const siteLists = sources.site_lists && typeof sources.site_lists === "object"
    ? Object.entries(sources.site_lists).map(([id, row]) => ({ id, ...(row || {}), source_type: "site_lists" }))
    : [];
  [...rss, ...newsnow, ...siteLists].forEach((item) => {
    rows.push(`
      <div class="list-item">
        <div class="list-item-head">
          <strong>${escapeHtml(item.id || "-")}</strong>
          <span class="pill">${escapeHtml(item.source_type || "")}</span>
        </div>
        <div class="muted">${escapeHtml(item.name || "")} · ${escapeHtml(item.url || item.home || "")}</div>
        <div class="toolbar">
          <button class="button small source-toggle-btn" data-source-type="${escapeAttr(item.source_type)}" data-source-id="${escapeAttr(item.id)}" data-enabled="${String(!item.enabled)}" type="button">${item.enabled ? "禁用" : "启用"}</button>
        </div>
      </div>
    `);
  });
  return rows.join("") || empty("暂无数据源");
}

function renderOutputRow(key, value) {
  const extra = [];
  if (value && value.count !== undefined) {
    extra.push(`count=${value.count}`);
  }
  if (value && value.size_bytes !== undefined) {
    extra.push(`size=${value.size_bytes}`);
  }
  return kvRow(key, `${value && value.path ? value.path : "-"}${extra.length ? ` (${extra.join(", ")})` : ""}`);
}

function renderRunItem(item) {
  return `
    <div class="list-item">
      <div class="list-item-head">
        <strong>${escapeHtml(item.run_id || "-")}</strong>
        <span class="pill state-${escapeAttr(item.state || "unknown")}">${escapeHtml(item.state || "")}</span>
      </div>
      <div class="muted">${escapeHtml(item.updated_at || "")}</div>
      <div class="toolbar">
        <button class="button small run-resume-btn" data-run-id="${escapeAttr(item.run_id)}" type="button">继续</button>
        <button class="button small danger run-cancel-btn" data-run-id="${escapeAttr(item.run_id)}" type="button">取消</button>
      </div>
    </div>
  `;
}

function renderTaskSummaryItem(task) {
  return `
    <div class="list-item">
      <div class="list-item-head">
        <strong>${escapeHtml(task.id || "-")}</strong>
        <span class="pill state-${escapeAttr(task.state || "unknown")}">${escapeHtml(task.state || "")}</span>
      </div>
      <div class="muted">${escapeHtml(task.type || "")}</div>
    </div>
  `;
}

function renderEventFeed(events) {
  const host = document.getElementById("event-feed");
  host.innerHTML = events.map((event) => `
    <div class="list-item">
      <div class="list-item-head">
        <strong>${escapeHtml(event.type || "event")}</strong>
        <span class="muted">${escapeHtml(formatTime(event.timestamp))}</span>
      </div>
      <div>${escapeHtml(JSON.stringify(event.data || {}, null, 2))}</div>
    </div>
  `).join("") || empty("暂无事件");
}

function bindRunActions() {
  document.querySelectorAll(".run-resume-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      await postJson(`/api/runs/${encodeURIComponent(button.dataset.runId)}/resume`, {});
      await refreshRuns();
      await refreshQueue();
    });
  });
  document.querySelectorAll(".run-cancel-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      await postJson(`/api/runs/${encodeURIComponent(button.dataset.runId)}/cancel`, { reason: "cancelled from web console" });
      await refreshRuns();
      await refreshQueue();
    });
  });
}

function bindQueueActions() {
  document.querySelectorAll(".queue-detail-btn").forEach((button) => {
    button.addEventListener("click", () => showTaskDetail(button.dataset.taskId));
  });
  document.querySelectorAll(".queue-retry-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      await postJson(`/api/queue/${encodeURIComponent(button.dataset.taskId)}/retry`, {});
      await refreshQueue();
    });
  });
  document.querySelectorAll(".queue-skip-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      await postJson(`/api/queue/${encodeURIComponent(button.dataset.taskId)}/skip`, { reason: "skipped from web console" });
      await refreshQueue();
    });
  });
  document.querySelectorAll(".queue-cancel-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      await postJson(`/api/queue/${encodeURIComponent(button.dataset.taskId)}/cancel`, { reason: "cancelled from web console" });
      await refreshQueue();
    });
  });
}

function bindWebActions() {
  document.querySelectorAll(".extractor-toggle-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      await fetchJson(`/api/extractors/${encodeURIComponent(button.dataset.sourceId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: button.dataset.enabled === "true" }),
      });
      await refreshWeb();
    });
  });
  document.querySelectorAll(".extractor-run-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      await postJson(`/api/web-sources/${encodeURIComponent(button.dataset.sourceId)}/run`, {});
      await refreshWeb();
      await refreshQueue();
    });
  });
}

function bindConfigActions() {
  document.querySelectorAll(".step-save-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      const stepId = button.dataset.stepId;
      const patch = {};
      document.querySelectorAll(`[data-step-id="${cssEscape(stepId)}"]`).forEach((field) => {
        patch[field.dataset.key] = parseFieldValue(field);
      });
      await fetchJson(`/api/runtime-config/steps/${encodeURIComponent(stepId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      await refreshConfig();
    });
  });
  const classificationSave = document.getElementById("classification-save");
  if (classificationSave) {
    classificationSave.addEventListener("click", async () => {
      const patch = {};
      document.querySelectorAll("[data-classification-key]").forEach((field) => {
        patch[field.dataset.classificationKey] = parseFieldValue(field);
      });
      await fetchJson("/api/runtime-config/classification", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      await refreshConfig();
    });
  }
  document.querySelectorAll(".source-toggle-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      const enabled = button.dataset.enabled === "true";
      const sourceType = button.dataset.sourceType;
      const sourceId = button.dataset.sourceId;
      let url = "";
      if (sourceType === "rss") {
        url = `/api/source-config/rss/${encodeURIComponent(sourceId)}`;
        await fetchJson(url, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: sourceId, enabled }),
        });
      } else if (sourceType === "newsnow") {
        url = `/api/source-config/newsnow/${encodeURIComponent(sourceId)}`;
        await fetchJson(url, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled }),
        });
      } else if (sourceType === "site_lists") {
        url = `/api/source-config/site-lists/${encodeURIComponent(sourceId)}`;
        await fetchJson(url, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled }),
        });
      }
      await refreshConfig();
    });
  });
}

function bindCheckpointActions() {
  document.querySelectorAll(".checkpoint-publish-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      await postJson("/api/checkpoints/publish", { checkpoint_path: button.dataset.path });
      await refreshArtifacts();
    });
  });
}

async function showTaskDetail(taskId) {
  state.selectedTaskId = taskId;
  const payload = await getJson(`/api/queue/${encodeURIComponent(taskId)}`);
  const result = {
    task: payload,
    result: payload.result,
    logs: payload.logs,
  };
  document.getElementById("queue-detail").textContent = JSON.stringify(result, null, 2);
}

async function submitRun(event) {
  event.preventDefault();
  const form = new FormData(event.target);
  const payload = {
    run_id: form.get("run_id") || undefined,
    only: parseCsv(form.get("only")),
    disable_classification: form.get("disable_classification") === "on",
    background: form.get("background") === "on",
  };
  await postJson("/api/run", payload);
  event.target.reset();
  event.target.querySelector('input[name="background"]').checked = true;
  await refreshRuns();
  await refreshQueue();
}

async function submitReport(event) {
  event.preventDefault();
  const form = new FormData(event.target);
  const payload = {
    input: form.get("input") || undefined,
    output_dir: form.get("output_dir") || undefined,
    date: form.get("date") || undefined,
  };
  await postJson("/api/report/generate", payload);
  await refreshArtifacts();
}

function connectEvents() {
  try {
    state.eventSource = new EventSource("/api/events");
    state.eventSource.addEventListener("replay", refreshOverview);
    state.eventSource.onmessage = refreshOverview;
  } catch (_error) {
    showToast("SSE 连接失败，改用轮询刷新");
  }
}

async function getQueueItems(filter) {
  const suffix = filter ? `?state=${encodeURIComponent(filter)}` : "";
  const payload = await getJson(`/api/queue${suffix}`);
  return Array.isArray(payload.items) ? payload.items : [];
}

async function getJson(url) {
  return fetchJson(url, { method: "GET" });
}

async function postJson(url, payload) {
  return fetchJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  let payload = {};
  try {
    payload = await response.json();
  } catch (_error) {
    payload = {};
  }
  if (!response.ok || payload.ok === false) {
    const message = payload.error || `request failed: ${response.status}`;
    showToast(message, true);
    throw new Error(message);
  }
  return payload;
}

function parseFieldValue(field) {
  if (field.type === "checkbox") {
    return field.checked;
  }
  const raw = String(field.value || "").trim();
  if (raw === "") {
    return "";
  }
  if (raw.includes(",") && !raw.startsWith("{") && !raw.startsWith("[")) {
    return parseCsv(raw);
  }
  if (raw === "true" || raw === "false") {
    return raw === "true";
  }
  if (!Number.isNaN(Number(raw)) && raw !== "") {
    return Number(raw);
  }
  return raw;
}

function parseCsv(raw) {
  const value = Array.isArray(raw) ? raw.join(",") : String(raw || "");
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function kvRow(key, value) {
  return `<div class="kv-row"><strong>${escapeHtml(key)}</strong><div>${escapeHtml(value)}</div></div>`;
}

function empty(text) {
  return `<div class="muted">${escapeHtml(text)}</div>`;
}

function formatTime(value) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value * 1000 || value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleTimeString();
}

function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  toast.style.color = isError ? "var(--danger)" : "var(--accent)";
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), 2500);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function cssEscape(value) {
  return String(value).replaceAll('"', '\\"');
}
