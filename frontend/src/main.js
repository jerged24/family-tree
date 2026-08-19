import { api } from "./api.js";
import { TreeView } from "./tree.js";

const loginOverlay = document.getElementById("login-overlay");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");

document.addEventListener("needs-login", () => {
  loginOverlay.hidden = false;
});

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.textContent = "";
  try {
    await api.login(document.getElementById("login-password").value);
    loginOverlay.hidden = true;
    loadTree();
  } catch {
    loginError.textContent = "Incorrect password.";
  }
});

const els = {
  svg: document.getElementById("tree-svg"),
  status: document.getElementById("status"),
  empty: document.getElementById("empty-state"),
  detail: document.getElementById("detail"),
  analysis: document.getElementById("analysis"),
  slotA: document.getElementById("slot-a"),
  slotB: document.getElementById("slot-b"),
  importInput: document.getElementById("import-input"),
  sampleBtn: document.getElementById("sample-btn"),
  exportBtn: document.getElementById("export-btn"),
  reloadBtn: document.getElementById("reload-btn"),
  clearCompare: document.getElementById("clear-compare"),
  viewMode: document.getElementById("view-mode"),
};

const state = {
  people: new Map(), // id(string) -> person summary from /persons
  selectedId: null,
  compare: [null, null], // [aId, bId]
};

const view = new TreeView(els.svg, {
  onSelect: (id) => selectPerson(id),
  onToggle: () => {},
});

function setStatus(msg, isError = false) {
  els.status.textContent = msg;
  els.status.classList.toggle("error", isError);
}

function personName(id) {
  const p = state.people.get(String(id));
  return p ? displayName(p) : `#${id}`;
}
function displayName(p) {
  return [p.name_prefix, p.given_name, p.surname, p.name_suffix].filter(Boolean).join(" ") || "(unknown)";
}

async function loadPeople() {
  const list = await api.persons();
  state.people = new Map(list.map((p) => [String(p.id), p]));
}

async function loadTree() {
  setStatus("Loading…");
  try {
    await loadPeople();
    let graph;
    const mode = els.viewMode.value;
    if (mode !== "full" && state.selectedId) {
      graph = await api.tree(state.selectedId, mode === "both" ? "full" : mode);
    } else {
      graph = await api.tree();
    }
    view.setGraph(graph);
    const empty = graph.nodes.length === 0;
    els.empty.hidden = !empty;
    setStatus(empty ? "No people yet" : `${graph.nodes.length} people · ${graph.edges.length} links`);
  } catch (err) {
    setStatus(err.message, true);
    console.error(err);
  }
}

async function selectPerson(id) {
  state.selectedId = id;
  view.setSelected(String(id));
  renderDetail(id);
  // Re-render subtree views centred on the new selection.
  if (els.viewMode.value !== "full") loadTree();
}

async function renderDetail(id) {
  const p = state.people.get(String(id));
  if (!p) {
    els.detail.innerHTML = `<span class="muted">Person #${id}</span>`;
    return;
  }
  els.detail.classList.remove("muted");
  els.detail.innerHTML = `
    <div class="person-head">
      <div class="avatar" id="detail-avatar"></div>
      <div>
        <div class="name">${displayName(p)}</div>
        <div class="meta">${sexLabel(p.sex)}${p.xref_id ? " · " + p.xref_id : ""}</div>
      </div>
    </div>
    <ul class="events"><li class="muted">Loading events…</li></ul>
    <div class="photo-add">
      <input type="url" id="photo-url" placeholder="Photo URL…" />
      <button class="btn subtle" id="photo-add-btn">Add photo</button>
    </div>
    <div class="detail-actions">
      <button class="btn subtle" data-slot="0">Set as A</button>
      <button class="btn subtle" data-slot="1">Set as B</button>
    </div>`;
  els.detail.querySelectorAll("button[data-slot]").forEach((b) =>
    b.addEventListener("click", () => setCompareSlot(Number(b.dataset.slot), id))
  );

  // Add-photo handler.
  const urlInput = els.detail.querySelector("#photo-url");
  const addPhoto = async () => {
    const url = urlInput.value.trim();
    if (!url) return;
    try {
      await api.addMedia(id, { url, is_primary: true });
      urlInput.value = "";
      await loadTree(); // refresh node avatars
      renderDetail(id); // refresh thumbnail
    } catch (err) {
      setStatus(err.message, true);
    }
  };
  els.detail.querySelector("#photo-add-btn").addEventListener("click", addPhoto);
  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") addPhoto();
  });

  // Load events + media in parallel.
  try {
    const [events, media] = await Promise.all([api.personEvents(id), api.personMedia(id)]);
    const ul = els.detail.querySelector(".events");
    ul.innerHTML = events.length
      ? events
          .map(
            (e) =>
              `<li><span class="etype">${e.type}</span> ${e.date_value || ""} ${
                e.place ? "· " + e.place : ""
              }</li>`
          )
          .join("")
      : `<li class="muted">No events recorded.</li>`;

    const primary = media.find((m) => m.is_primary) || media[0];
    const avatar = els.detail.querySelector("#detail-avatar");
    if (primary) {
      avatar.style.backgroundImage = `url("${primary.url}")`;
      avatar.classList.add("has-photo");
      avatar.textContent = "";
    } else {
      avatar.textContent = (displayName(p)[0] || "?").toUpperCase();
    }
  } catch {
    /* leave the loading text */
  }
}

function sexLabel(s) {
  return { M: "Male", F: "Female", X: "Intersex", U: "Unknown" }[s] || "Unknown";
}

function setCompareSlot(slot, id) {
  state.compare[slot] = String(id);
  renderSlots();
  view.setComparison(state.compare);
  maybeAnalyse();
}

function renderSlots() {
  [els.slotA, els.slotB].forEach((el, i) => {
    const id = state.compare[i];
    el.classList.toggle("filled", Boolean(id));
    el.querySelector(".slot-name").textContent = id ? personName(id) : "—";
  });
}

async function maybeAnalyse() {
  const [a, b] = state.compare;
  if (!a || !b) {
    els.analysis.className = "analysis muted";
    els.analysis.textContent = "Set two people to analyse how they're related.";
    view.setPath([]);
    return;
  }
  if (a === b) {
    els.analysis.className = "analysis muted";
    els.analysis.textContent = "Pick two different people.";
    return;
  }
  try {
    const r = await api.relationship(a, b);
    view.setPath(r.path || []);
    els.analysis.className = "analysis";
    const pct = (x) => (x * 100).toFixed(2) + "%";
    els.analysis.innerHTML = `
      <div class="verdict">${personName(b)} is ${personName(a)}'s ${r.description}</div>
      <dl>
        <dt>Kinship (φ)</dt><dd>${r.kinship_coefficient.toFixed(4)}</dd>
        <dt>Relationship (r)</dt><dd>${pct(r.coefficient_of_relationship)}</dd>
        <dt>Common ancestors</dt><dd>${
          r.most_recent_common_ancestors.map(personName).join(", ") || "—"
        }</dd>
        <dt>Path length</dt><dd>${r.path ? r.path.length - 1 + " steps" : "no path"}</dd>
      </dl>`;
  } catch (err) {
    els.analysis.className = "analysis";
    els.analysis.innerHTML = `<span class="muted">${err.message}</span>`;
  }
}

// ---- toolbar ----
els.importInput.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  setStatus("Importing…");
  try {
    const r = await api.importGedcom(file);
    setStatus(`Imported ${r.persons} people, ${r.families} families`);
    state.selectedId = null;
    await loadTree();
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    e.target.value = "";
  }
});

els.sampleBtn.addEventListener("click", async () => {
  setStatus("Loading sample…");
  try {
    await api.loadSample();
    state.selectedId = null;
    await loadTree();
  } catch (err) {
    setStatus(err.message, true);
  }
});

els.exportBtn.addEventListener("click", (e) => {
  e.preventDefault();
  window.open(api.exportUrl(), "_blank");
});

els.reloadBtn.addEventListener("click", loadTree);
els.viewMode.addEventListener("change", loadTree);
els.clearCompare.addEventListener("click", () => {
  state.compare = [null, null];
  renderSlots();
  view.setComparison([]);
  maybeAnalyse();
});

// initial load
loadTree();
