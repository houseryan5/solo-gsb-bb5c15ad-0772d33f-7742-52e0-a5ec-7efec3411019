/* 多评委评分校准 —— 原生 JS 前端，无任何框架依赖。 */
"use strict";

const $ = (sel) => document.querySelector(sel);

let result = null;
let saveTimers = new Map();

const els = {
  fileInput: $("#fileInput"),
  exportBtn: $("#exportBtn"),
  clearBtn: $("#clearBtn"),
  allCal: $("#allCal"),
  allRaw: $("#allRaw"),
  projectFilter: $("#projectFilter"),
  itemProjectFilter: $("#itemProjectFilter"),
  itemSearch: $("#itemSearch"),
  alert: $("#alert"),
  emptyState: $("#emptyState"),
  dashboard: $("#dashboard"),
  sessionInfo: $("#sessionInfo"),
};

function fmt(x, d = 2) {
  if (x === null || x === undefined || Number.isNaN(x)) return "-";
  return Number(x).toFixed(d);
}

function showAlert(msg, kind = "error") {
  els.alert.textContent = msg;
  els.alert.className = `alert ${kind}`;
  clearTimeout(showAlert._t);
  showAlert._t = setTimeout(() => els.alert.classList.add("hidden"), 5000);
}

async function api(url, options) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `请求失败（HTTP ${res.status}）`);
  }
  return data;
}

// ---------- 渲染 ----------

function renderAll(payload) {
  result = payload;
  if (!result) {
    els.emptyState.classList.remove("hidden");
    els.dashboard.classList.add("hidden");
    return;
  }
  els.emptyState.classList.add("hidden");
  els.dashboard.classList.remove("hidden");

  renderMetrics();
  renderReversals();
  renderJudges();
  renderProjectOptions();
  renderProjectTable();
  renderOverall();
  renderItemFilters();
  renderItems();
}

function renderMetrics() {
  const nRev = result.reversals.length;
  $("#metrics").innerHTML = `
    <div class="metric"><div class="num">${result.contestants.length}</div><div class="label">选手</div></div>
    <div class="metric"><div class="num">${result.judges.length}</div><div class="label">评委</div></div>
    <div class="metric"><div class="num">${result.projects.length}</div><div class="label">项目</div></div>
    <div class="metric"><div class="num">${result.n_items}</div><div class="label">评分项</div></div>
    <div class="metric ${nRev ? "warn" : ""}"><div class="num">${nRev}</div><div class="label">名次反转对</div></div>
    <div class="metric"><div class="num">${result.n_decisions}</div><div class="label">已保留原分</div></div>
  `;
  $("#reversalCount").textContent = nRev;
}

function renderReversals() {
  const tbody = $("#reversalTable tbody");
  if (!result.reversals.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="color:var(--good)">校准前后无名次反转。</td></tr>`;
    return;
  }
  tbody.innerHTML = result.reversals.map((r) => `
    <tr>
      <td>${r.scope === "project" ? "项目内" : "总评"}</td>
      <td>${escapeHtml(r.project) || "—"}</td>
      <td>${escapeHtml(r.raw_leader)}</td>
      <td class="leader-swap">⇄</td>
      <td>${escapeHtml(r.calibrated_leader)}</td>
      <td>${fmt(r.raw_gap, 3)}</td>
      <td>${fmt(r.calibrated_gap, 3)}</td>
    </tr>
  `).join("");
}

function renderJudges() {
  const scaleLabel = { mad: "MAD", stdev: "标准差（MAD=0 退化）", none: "无差异" };
  $("#judgeTable tbody").innerHTML = result.judge_stats.map((s) => `
    <tr>
      <td>${escapeHtml(s.judge)}</td>
      <td>${s.n}</td>
      <td>${fmt(s.median, 2)}</td>
      <td>${fmt(s.mad, 3)}</td>
      <td>${fmt(s.mean, 2)}</td>
      <td>${fmt(s.std, 3)}</td>
      <td>${s.scale > 0 ? fmt(s.scale, 3) : "—"}</td>
      <td>${scaleLabel[s.scale_used] || s.scale_used}</td>
    </tr>
  `).join("");
}

function renderProjectOptions() {
  const prev = els.projectFilter.value;
  els.projectFilter.innerHTML = result.projects
    .map((p) => `<option value="${escapeAttr(p)}">${escapeHtml(p)}</option>`).join("");
  if (result.projects.includes(prev)) els.projectFilter.value = prev;
}

function rankDeltaHtml(rawRank, effRank) {
  if (rawRank === effRank) return `<span class="rank-same">${rawRank} =</span>`;
  if (effRank < rawRank)
    return `<span class="rank-up">${rawRank} → ${effRank} ▲${rawRank - effRank}</span>`;
  return `<span class="rank-down">${rawRank} → ${effRank} ▼${effRank - rawRank}</span>`;
}

function renderProjectTable() {
  const project = els.projectFilter.value || result.projects[0];
  const rows = (result.project_rows[project] || []).slice().sort(
    (a, b) => a.effective_rank - b.effective_rank
  );
  const reversalMembers = new Set(
    result.reversals
      .filter((r) => r.scope === "project" && r.project === project)
      .flatMap((r) => [r.contestant_a, r.contestant_b])
  );
  $("#projectTable tbody").innerHTML = rows.map((r) => `
    <tr class="${reversalMembers.has(r.contestant) ? "reversal" : ""}">
      <td><strong>${r.effective_rank}</strong></td>
      <td>${escapeHtml(r.contestant)}</td>
      <td>${r.n_judges}</td>
      <td>${fmt(r.raw_score, 3)}</td>
      <td>${r.raw_rank}</td>
      <td>${fmt(r.calibrated_score, 3)}</td>
      <td>${r.calibrated_rank}</td>
      <td><strong>${fmt(r.effective_score, 3)}</strong></td>
      <td>${rankDeltaHtml(r.raw_rank, r.effective_rank)}</td>
    </tr>
  `).join("");
}

function renderOverall() {
  const rows = result.overall_rows.slice().sort((a, b) => a.effective_rank - b.effective_rank);
  const members = new Set(
    result.reversals
      .filter((r) => r.scope === "overall")
      .flatMap((r) => [r.contestant_a, r.contestant_b])
  );
  $("#overallTable tbody").innerHTML = rows.map((r) => `
    <tr class="${members.has(r.contestant) ? "reversal" : ""}">
      <td><strong>${r.effective_rank}</strong></td>
      <td>${escapeHtml(r.contestant)}</td>
      <td>${r.n_projects}</td>
      <td>${fmt(r.raw_total, 3)}</td>
      <td>${r.raw_rank}</td>
      <td>${fmt(r.calibrated_total, 3)}</td>
      <td>${r.calibrated_rank}</td>
      <td><strong>${fmt(r.effective_total, 3)}</strong></td>
      <td>${rankDeltaHtml(r.raw_rank, r.effective_rank)}</td>
    </tr>
  `).join("");
}

function renderItemFilters() {
  const prev = els.itemProjectFilter.value;
  els.itemProjectFilter.innerHTML =
    `<option value="">全部项目</option>` +
    result.projects
      .map((p) => `<option value="${escapeAttr(p)}">${escapeHtml(p)}</option>`).join("");
  if (result.projects.includes(prev)) els.itemProjectFilter.value = prev;
}

function renderItems() {
  const pf = els.itemProjectFilter.value;
  const q = els.itemSearch.value.trim().toLowerCase();
  const projectOrder = Object.fromEntries(result.projects.map((p, i) => [p, i]));
  const items = result.items
    .filter((it) => !pf || it.project === pf)
    .filter((it) => !q || it.contestant.toLowerCase().includes(q) || it.judge.toLowerCase().includes(q))
    .sort((a, b) =>
      projectOrder[a.project] - projectOrder[b.project] ||
      a.contestant.localeCompare(b.contestant, "zh") ||
      a.judge.localeCompare(b.judge, "zh")
    );

  $("#itemsTable tbody").innerHTML = items.map((it) => `
    <tr data-id="${escapeAttr(it.id)}">
      <td>${escapeHtml(it.contestant)}</td>
      <td>${escapeHtml(it.project)}</td>
      <td>${escapeHtml(it.judge)}</td>
      <td>${fmt(it.raw_score, 2)}</td>
      <td>${fmt(it.robust_z, 3)}</td>
      <td>${fmt(it.calibrated_score, 2)}</td>
      <td><strong>${fmt(it.effective_score, 2)}</strong></td>
      <td>
        <div class="mode-toggle">
          <button class="${it.mode === "calibrated" ? "active-cal" : ""}" data-mode="calibrated">校准分</button>
          <button class="${it.mode === "raw" ? "active-raw" : ""}" data-mode="raw">原分</button>
        </div>
      </td>
      <td class="reason-cell">
        <input type="text" class="reason-input" placeholder="填写采用理由（审计留痕）"
          value="${escapeAttr(it.reason)}" />
      </td>
    </tr>
  `).join("");
}

// ---------- 交互 ----------

async function applyResult(data) {
  renderAll(data.result);
}

async function saveDecision(id, mode, reason) {
  try {
    const data = await api("/api/decisions", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisions: { [id]: { mode, reason } } }),
    });
    renderAll(data.result);
  } catch (err) {
    showAlert(err.message);
  }
}

async function bulkSet(mode) {
  try {
    const data = await api("/api/decisions/bulk", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    renderAll(data.result);
    showAlert(mode === "raw" ? "已全部保留原分。" : "已全部采用校准分。", "ok");
  } catch (err) {
    showAlert(err.message);
  }
}

$("#itemsTable tbody").addEventListener("click", (e) => {
  const btn = e.target.closest(".mode-toggle button");
  if (!btn) return;
  const tr = e.target.closest("tr");
  const id = tr.dataset.id;
  const mode = btn.dataset.mode;
  const reasonInput = tr.querySelector(".reason-input");
  saveDecision(id, mode, reasonInput.value);
});

$("#itemsTable tbody").addEventListener("input", (e) => {
  if (!e.target.classList.contains("reason-input")) return;
  const tr = e.target.closest("tr");
  const id = tr.dataset.id;
  const reason = e.target.value;
  // 找到当前模式
  const cur = result.items.find((it) => it.id === id);
  clearTimeout(saveTimers.get(id));
  const focused = document.activeElement === e.target;
  const cursor = e.target.selectionStart;
  saveTimers.set(
    id,
    setTimeout(async () => {
      try {
        const data = await api("/api/decisions", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decisions: { [id]: { mode: cur.mode, reason } } }),
        });
        renderAll(data.result);
        if (focused) {
          const input = document.querySelector(`tr[data-id="${cssEscape(id)}"] .reason-input`);
          if (input) {
            input.focus();
            const pos = Math.min(cursor ?? reason.length, input.value.length);
            input.setSelectionRange(pos, pos);
          }
        }
      } catch (err) {
        showAlert(err.message);
      }
    }, 400)
  );
});

els.itemProjectFilter.addEventListener("change", renderItems);
els.itemSearch.addEventListener("input", renderItems);
els.projectFilter.addEventListener("change", renderProjectTable);
els.allCal.addEventListener("click", () => bulkSet("calibrated"));
els.allRaw.addEventListener("click", () => bulkSet("raw"));

els.fileInput.addEventListener("change", async () => {
  const file = els.fileInput.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const data = await api("/api/upload", { method: "POST", body: fd });
    renderAll(data.result);
    els.sessionInfo.textContent = `文件：${file.name} · ${data.result.n_items} 条评分 · ${new Date().toLocaleString()}`;
    showAlert("上传并校准完成。", "ok");
  } catch (err) {
    showAlert(err.message);
  } finally {
    els.fileInput.value = "";
  }
});

els.clearBtn.addEventListener("click", async () => {
  if (!confirm("确定清空当前会话？已上传数据与所有裁决理由将从数据卷永久删除。")) return;
  try {
    await api("/api/session", { method: "DELETE" });
    result = null;
    renderAll(null);
    els.sessionInfo.textContent = "尚未上传数据";
    showAlert("会话已清空。", "ok");
  } catch (err) {
    showAlert(err.message);
  }
});

els.exportBtn.addEventListener("click", () => {
  if (!result) {
    showAlert("暂无数据，请先上传 CSV。");
    return;
  }
  window.location.href = "/api/export";
});

// ---------- 工具 ----------

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}
function escapeAttr(s) {
  return escapeHtml(s);
}
function cssEscape(s) {
  return window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/(["\\])/g, "\\$1");
}

// ---------- 初始化 ----------

(async function init() {
  try {
    const state = await api("/api/state");
    if (state.has_data) {
      renderAll(state.result);
      els.sessionInfo.textContent =
        `文件：${state.filename || "-"} · ${state.result.n_items} 条评分 · 上传于 ${state.uploaded_at || "-"}`;
    } else {
      renderAll(null);
    }
  } catch (err) {
    showAlert(err.message);
    renderAll(null);
  }
})();
