// Thin client for the Family Tree API.
// Override at runtime with ?api=http://host:port  (handy when ports differ).

const params = new URLSearchParams(location.search);
export const API_BASE = params.get("api") || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const res = await fetch(API_BASE + path, { credentials: "include", ...options });
  if (res.status === 401) {
    document.dispatchEvent(new CustomEvent("needs-login"));
    throw new Error("Login required");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch { /* non-JSON body */ }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  tree(rootId = null, mode = "full") {
    if (rootId == null) return request("/tree");
    return request(`/tree/person/${rootId}?mode=${mode}`);
  },
  persons() {
    return request("/persons?limit=1000");
  },
  personEvents(id) {
    return request(`/persons/${id}/events`);
  },
  relationship(a, b) {
    return request(`/tree/relationship/${a}/${b}`);
  },
  importGedcom(file) {
    const body = new FormData();
    body.append("file", file);
    return request("/gedcom/import", { method: "POST", body });
  },
  loadSample() {
    return request("/gedcom/sample", { method: "POST" });
  },
  personMedia(id) {
    return request(`/persons/${id}/media`);
  },
  addMedia(id, payload) {
    return request(`/persons/${id}/media`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  exportUrl(version = "5.5.1") {
    return `${API_BASE}/gedcom/export?version=${version}`;
  },
  login(password) {
    return request("/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
  },
  uploadMedia(id, file, { is_primary = false } = {}) {
    const body = new FormData();
    body.append("file", file);
    body.append("is_primary", String(is_primary));
    return request(`/persons/${id}/media/upload`, { method: "POST", body });
  },
};
