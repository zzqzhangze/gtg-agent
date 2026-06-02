// ── State ──
let editingId = null;
const API = {
  listServers:      () => fetch("/mcp/servers").then(r => r.json()),
  createServer:     (data) => fetch("/mcp/servers", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)}).then(r => {if(!r.ok)throw r; return r.json()}),
  updateServer:     (id, data) => fetch(`/mcp/servers/${id}`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)}).then(r => {if(!r.ok)throw r; return r.json()}),
  deleteServer:     (id) => fetch(`/mcp/servers/${id}`, {method:"DELETE"}).then(r => {if(!r.ok)throw r; return r.json()}),
  testServer:       (id) => fetch(`/mcp/servers/${id}/test`, {method:"POST"}).then(r => {if(!r.ok)throw r; return r.json()}),
  syncServer:       (id) => fetch(`/mcp/servers/${id}/sync`, {method:"POST"}).then(r => {if(!r.ok)throw r; return r.json()}),
  listTools:        (sid) => fetch(`/mcp/tools${sid ? `?server_id=${sid}` : ""}`).then(r => r.json()),
  toggleTool:       (id, enabled) => fetch(`/mcp/tools/${id}`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({enabled})}).then(r => {if(!r.ok)throw r; return r.json()}),
};

// ── Messages ──
function msg(text, type="error") {
  const el = document.getElementById("messages");
  el.innerHTML = `<div class="${type}-msg">${text}</div>`;
  setTimeout(() => el.innerHTML = "", 5000);
}

// ── Servers ──
async function loadServers() {
  try {
    const servers = await API.listServers();
    const tbody = document.getElementById("server-list");
    if (servers.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">暂无 MCP Server，点击上方按钮添加</td></tr>';
    } else {
      tbody.innerHTML = servers.map(s => {
        const status = s.tool_count !== undefined ? `<span class="badge badge-on">${s.tool_count} tools</span>` : '<span class="badge badge-off">未同步</span>';
        return `<tr>
          <td><strong>${esc(s.name)}</strong></td>
          <td style="font-size:0.8rem;color:var(--text-dim)">${esc(s.url)}</td>
          <td>${s.timeout}s</td>
          <td>${status}</td>
          <td class="actions">
            <button class="btn btn-outline btn-sm" onclick="editServer('${s.id}')">编辑</button>
            <button class="btn btn-outline btn-sm" onclick="testServer('${s.id}')">测试</button>
            <button class="btn btn-outline btn-sm" onclick="syncServer('${s.id}')">同步</button>
            <button class="btn btn-danger btn-sm" onclick="deleteServer('${s.id}')">删除</button>
          </td>
        </tr>`;
      }).join("");
    }
    loadTools();
  } catch (e) {
    document.getElementById("server-list").innerHTML = '<tr><td colspan="5" class="empty">加载失败</td></tr>';
  }
}

async function testServer(id) {
  const btn = event.target; btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
  try {
    const r = await API.testServer(id);
    msg(`连接成功，发现 ${r.tools_count} 个工具: ${r.tools.join(", ")}`, "success");
  } catch (e) {
    const text = e.statusText || "连接失败";
    msg(`测试失败: ${text}`);
  } finally { btn.disabled = false; btn.textContent = "测试"; }
}

async function syncServer(id) {
  const btn = event.target; btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
  try {
    const r = await API.syncServer(id);
    msg(`同步成功，导入 ${r.tools_count} 个工具`, "success");
    loadServers();
  } catch (e) {
    msg(`同步失败`);
  } finally { btn.disabled = false; btn.textContent = "同步"; }
}

async function deleteServer(id) {
  if (!confirm("确定删除这个 MCP Server？关联的工具也会被删除。")) return;
  try {
    await API.deleteServer(id);
    msg("已删除", "success");
    loadServers();
  } catch (e) {
    msg("删除失败");
  }
}

// ── Dialog ──
function showAddDialog() {
  editingId = null;
  document.getElementById("dialog-title").textContent = "添加 MCP Server";
  document.getElementById("f-name").value = "";
  document.getElementById("f-url").value = "";
  document.getElementById("f-timeout").value = "60";
  document.getElementById("dialog-save").textContent = "添加";
  document.getElementById("dialog").style.display = "flex";
}

function editServer(id) {
  editingId = id;
  const row = document.querySelector(`#server-list tr td`); // find the row...
  // simpler: refetch
  API.listServers().then(servers => {
    const s = servers.find(x => x.id === id);
    if (!s) return;
    document.getElementById("dialog-title").textContent = "编辑 MCP Server";
    document.getElementById("f-name").value = s.name;
    document.getElementById("f-url").value = s.url;
    document.getElementById("f-timeout").value = s.timeout;
    document.getElementById("dialog-save").textContent = "保存";
    document.getElementById("dialog").style.display = "flex";
  });
}

function closeDialog() {
  document.getElementById("dialog").style.display = "none";
}

async function saveServer() {
  const data = {
    name: document.getElementById("f-name").value.trim(),
    url: document.getElementById("f-url").value.trim(),
    timeout: parseInt(document.getElementById("f-timeout").value) || 60,
  };
  if (!data.name || !data.url) { msg("名称和 URL 不能为空"); return; }

  const btn = document.getElementById("dialog-save");
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
  try {
    if (editingId) {
      await API.updateServer(editingId, data);
      msg("更新成功", "success");
    } else {
      await API.createServer(data);
      msg("添加成功", "success");
    }
    closeDialog();
    loadServers();
  } catch (e) {
    msg("保存失败");
  } finally { btn.disabled = false; btn.textContent = editingId ? "保存" : "添加"; }
}

// ── Tools ──
async function loadTools() {
  try {
    const tools = await API.listTools();
    const tbody = document.getElementById("tool-list");
    document.getElementById("tool-count").textContent = `(${tools.length})`;
    if (tools.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty">请先添加并同步 MCP Server</td></tr>';
    } else {
      tbody.innerHTML = tools.map(t => {
        const desc = t.description ? esc(t.description.substring(0, 80) + (t.description.length > 80 ? "..." : "")) : "-";
        return `<tr>
          <td style="font-size:0.8rem;color:var(--text-dim)">${esc(t.server_name || "")}</td>
          <td><code style="background:var(--bg);padding:2px 6px;border-radius:4px;font-size:0.85rem">${esc(t.name)}</code></td>
          <td style="font-size:0.85rem">${desc}</td>
          <td><label class="toggle"><input type="checkbox" ${t.enabled ? "checked" : ""} onchange="toggleTool('${t.id}', this.checked)"><span class="badge ${t.enabled ? 'badge-on' : 'badge-off'}">${t.enabled ? "启用" : "禁用"}</span></label></td>
        </tr>`;
      }).join("");
    }
  } catch (e) {
    document.getElementById("tool-list").innerHTML = '<tr><td colspan="4" class="empty">加载失败</td></tr>';
  }
}

async function toggleTool(id, enabled) {
  try {
    await API.toggleTool(id, enabled);
  } catch (e) {
    msg("切换失败");
    loadTools();
  }
}

// ── Utils ──
function esc(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// ── Init ──
loadServers();
