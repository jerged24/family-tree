// Thin client for the Family Tree API.
// Override at runtime with ?api=http://host:port  (handy when ports differ).

const params = new URLSearchParams(location.search);
// Default to same-origin ("" → relative paths like "/persons") so the SPA served
// by the backend works in production. The ?api= override still points elsewhere
// (used by the e2e fixture when ports differ).
export const API_BASE = params.get("api") || "";

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

function bodyJSON(method, path, payload) {
  return request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
const postJSON = (path, payload) => bodyJSON("POST", path, payload);
const patchJSON = (path, payload) => bodyJSON("PATCH", path, payload);

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
  personMemberships(id) {
    return request(`/persons/${id}/memberships`);
  },
  personAssociations(id) {
    return request(`/persons/${id}/associations`);
  },
  addAssociation(id, payload) {
    return postJSON(`/persons/${id}/associations`, payload);
  },
  deleteAssociation(assocId) {
    return request(`/associations/${assocId}`, { method: "DELETE" });
  },
  createPerson(payload) {
    return postJSON("/persons", payload);
  },
  updatePerson(id, payload) {
    return patchJSON(`/persons/${id}`, payload);
  },
  deletePerson(id) {
    return request(`/persons/${id}`, { method: "DELETE" });
  },
  createEvent(payload) {
    return postJSON("/events", payload);
  },
  updateEvent(id, payload) {
    return patchJSON(`/events/${id}`, payload);
  },
  deleteEvent(id) {
    return request(`/events/${id}`, { method: "DELETE" });
  },
  createFamily() {
    return postJSON("/families", {});
  },
  addMember(familyId, payload) {
    return postJSON(`/families/${familyId}/members`, payload);
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
  updateMedia(mediaId, payload) {
    return patchJSON(`/media/${mediaId}`, payload);
  },
  deleteMedia(mediaId) {
    return request(`/media/${mediaId}`, { method: "DELETE" });
  },
  exportUrl(version = "5.5.1", privacy = "none") {
    return `${API_BASE}/gedcom/export?version=${version}&privacy=${privacy}`;
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
