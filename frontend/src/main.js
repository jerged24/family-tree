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
  importCsvInput: document.getElementById("import-csv-input"),
  templateBtn: document.getElementById("template-btn"),
  addPersonBtn: document.getElementById("add-person-btn"),
  sampleBtn: document.getElementById("sample-btn"),
  exportBtn: document.getElementById("export-btn"),
  reloadBtn: document.getElementById("reload-btn"),
  clearCompare: document.getElementById("clear-compare"),
  viewMode: document.getElementById("view-mode"),
  layoutMode: document.getElementById("layout-mode"),
  timelineBtn: document.getElementById("timeline-btn"),
  timeline: document.getElementById("timeline"),
  eraSlider: document.getElementById("era-slider"),
  eraLabel: document.getElementById("era-label"),
  timelineOff: document.getElementById("timeline-off"),
  dedupeBtn: document.getElementById("dedupe-btn"),
  dedupeModal: document.getElementById("dedupe-modal"),
  dedupeList: document.getElementById("dedupe-list"),
  dedupeClose: document.getElementById("dedupe-close"),
  filterText: document.getElementById("filter-text"),
  filterDecade: document.getElementById("filter-decade"),
  privacyToggle: document.getElementById("privacy-toggle"),
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

// Capitalize the first letter of each word, leaving the rest of each word as typed.
function titleCase(s) {
  return (s || "").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Friendly display labels for GEDCOM event tags (the tags themselves stay in the data).
const EVENT_LABELS = {
  BIRT: "DOB", DEAT: "DOD", MARR: "Married", DIV: "Divorced", BURI: "Buried",
  CHR: "Christened", BAPM: "Baptized", ADOP: "Adopted", GRAD: "Graduated",
  IMMI: "Immigrated", OCCU: "Occupation", RESI: "Residence", ENGA: "Engaged",
  ANUL: "Annulled", EVEN: "Event",
};
const eventLabel = (tag) => EVENT_LABELS[tag] || tag;

// ---- person-form modal (reusable) ----
const personModal = document.getElementById("person-modal");
const personForm = document.getElementById("person-form");
let modalResolve = null;

function openPersonForm(title, prefill = {}, opts = {}) {
  document.getElementById("person-modal-title").textContent = title;
  document.getElementById("pf-given").value = prefill.given || "";
  document.getElementById("pf-surname").value = prefill.surname || "";
  document.getElementById("pf-sex").value = prefill.sex || "U";
  document.getElementById("pf-dob").value = prefill.dob || "";
  document.getElementById("pf-dod").value = prefill.dod || "";
  document.getElementById("pf-pedigree").value = "BIRTH";
  document.getElementById("pf-pedigree-wrap").hidden = !opts.showPedigree;
  personModal.hidden = false;
  document.getElementById("pf-given").focus();
  return new Promise((resolve) => (modalResolve = resolve));
}
function closePersonForm(result) {
  personModal.hidden = true;
  const resolve = modalResolve;
  modalResolve = null;
  if (resolve) resolve(result);
}
personForm.addEventListener("submit", (e) => {
  e.preventDefault();
  closePersonForm({
    given: titleCase(document.getElementById("pf-given").value.trim()),
    surname: titleCase(document.getElementById("pf-surname").value.trim()),
    sex: document.getElementById("pf-sex").value,
    dob: document.getElementById("pf-dob").value.trim(),
    dod: document.getElementById("pf-dod").value.trim(),
    pedigree: document.getElementById("pf-pedigree").value,
  });
});
// Auto-capitalize names as you leave the field.
["pf-given", "pf-surname"].forEach((id) => {
  const el = document.getElementById(id);
  el.addEventListener("blur", () => {
    el.value = titleCase(el.value);
  });
});
document.getElementById("pf-cancel").addEventListener("click", () => closePersonForm(null));
personModal.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closePersonForm(null);
});

// Create a person from form data (plus DOB/DOD events). Returns the new id.
async function createPersonFromForm(form) {
  const person = await api.createPerson({
    given_name: form.given || null,
    surname: form.surname || null,
    sex: form.sex || "U",
  });
  if (form.dob) await api.createEvent({ type: "BIRT", person_id: person.id, date_value: form.dob });
  if (form.dod) await api.createEvent({ type: "DEAT", person_id: person.id, date_value: form.dod });
  return person.id;
}

// Family reuse: find the person's partner (or child) family, else create one.
// When creating a CHILD membership, an optional non-birth pedigree is applied.
async function familyOf(personId, role, pedigree) {
  const memberships = await api.personMemberships(personId);
  const existing = memberships.find((m) => m.role === role);
  if (existing) return existing.family_id;
  const fam = await api.createFamily();
  const payload = { person_id: personId, family_id: fam.id, role };
  if (role === "CHILD" && pedigree && pedigree !== "BIRTH") payload.pedigree = pedigree;
  await api.addMember(fam.id, payload);
  return fam.id;
}

async function addRelative(kind, anchorId, form) {
  const pedigree = form.pedigree || "BIRTH";
  if (kind === "child") {
    const famId = await familyOf(anchorId, "PARTNER");
    const childId = await createPersonFromForm(form);
    const payload = { person_id: childId, family_id: famId, role: "CHILD" };
    if (pedigree !== "BIRTH") payload.pedigree = pedigree;
    await api.addMember(famId, payload);
  } else if (kind === "spouse") {
    const famId = await familyOf(anchorId, "PARTNER");
    const spouseId = await createPersonFromForm(form);
    await api.addMember(famId, { person_id: spouseId, family_id: famId, role: "PARTNER" });
  } else if (kind === "parent") {
    // The anchor is the CHILD in this new family; the pedigree describes that link.
    const famId = await familyOf(anchorId, "CHILD", pedigree);
    const parentId = await createPersonFromForm(form);
    await api.addMember(famId, { person_id: parentId, family_id: famId, role: "PARTNER" });
  }
}

// Bring a person's DOB/DOD event into line with an edited value: update, create, or delete.
async function reconcileDateEvent(personId, type, existing, newValue) {
  const value = (newValue || "").trim();
  if (value && existing && existing.date_value !== value) {
    await api.updateEvent(existing.id, { date_value: value });
  } else if (value && !existing) {
    await api.createEvent({ type, person_id: personId, date_value: value });
  } else if (!value && existing) {
    await api.deleteEvent(existing.id);
  }
}

async function editPerson(id) {
  const p = state.people.get(String(id));
  if (!p) return;
  const events = await api.personEvents(id);
  const birth = events.find((e) => e.type === "BIRT");
  const death = events.find((e) => e.type === "DEAT");
  const form = await openPersonForm("Edit person", {
    given: p.given_name || "",
    surname: p.surname || "",
    sex: p.sex || "U",
    dob: birth?.date_value || "",
    dod: death?.date_value || "",
  });
  if (!form) return;
  setStatus("Saving…");
  try {
    await api.updatePerson(id, {
      given_name: form.given || null,
      surname: form.surname || null,
      sex: form.sex || "U",
    });
    await reconcileDateEvent(id, "BIRT", birth, form.dob);
    await reconcileDateEvent(id, "DEAT", death, form.dod);
    await loadTree();
    renderDetail(id);
    setStatus("Saved");
  } catch (err) {
    setStatus(err.message, true);
  }
}

async function removePerson(id) {
  const p = state.people.get(String(id));
  if (!p) return;
  if (!window.confirm(`Delete ${displayName(p)} and their family links? This cannot be undone.`)) {
    return;
  }
  setStatus("Deleting…");
  try {
    await api.deletePerson(id);
    if (state.selectedId === id) state.selectedId = null;
    state.compare = state.compare.map((c) => (c === String(id) ? null : c));
    renderSlots();
    view.setComparison(state.compare);
    maybeAnalyse();
    els.detail.className = "detail muted";
    els.detail.textContent = "Select a person on the tree.";
    await loadTree();
    setStatus(`Deleted ${displayName(p)}`);
  } catch (err) {
    setStatus(err.message, true);
  }
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
    populateDecades(graph.nodes);
    applyFilter();
    if (!els.timeline.hidden) configureTimeline(); // keep the era range in sync with the data
    const empty = graph.nodes.length === 0;
    els.empty.hidden = !empty;
    setStatus(empty ? "No people yet" : `${graph.nodes.length} people · ${graph.edges.length} links`);
  } catch (err) {
    setStatus(err.message, true);
    console.error(err);
  }
}

// ---- filter: dim people who don't match the name text and/or birth decade ----
const yearOf = (birth) => {
  const m = (birth || "").match(/\b(\d{4})\b/);
  return m ? Number(m[1]) : null;
};

function populateDecades(nodes) {
  const decades = new Set();
  for (const n of nodes) {
    const y = yearOf(n.birth);
    if (y) decades.add(Math.floor(y / 10) * 10);
  }
  const current = els.filterDecade.value;
  const opts = ['<option value="">Any decade</option>'];
  for (const d of [...decades].sort((a, b) => a - b)) opts.push(`<option value="${d}">${d}s</option>`);
  els.filterDecade.innerHTML = opts.join("");
  els.filterDecade.value = decades.has(Number(current)) ? current : "";
}

// ---- timeline / era slider: highlight who was alive in the chosen year ----
function timelineRange() {
  const years = [];
  for (const n of view.raw.nodes) {
    const b = yearOf(n.birth);
    if (b) years.push(b);
    const d = yearOf(n.death);
    if (d) years.push(d);
  }
  return years.length ? [Math.min(...years), Math.max(...years)] : null;
}

function configureTimeline() {
  const range = timelineRange();
  if (!range) {
    setStatus("No dated people to place on a timeline");
    return false;
  }
  const [min, max] = range;
  els.eraSlider.min = String(min);
  els.eraSlider.max = String(max);
  // Preserve the current year if it's still in range, else start at the end.
  const cur = Number(els.eraSlider.value);
  const year = cur >= min && cur <= max ? cur : max;
  els.eraSlider.value = String(year);
  els.eraLabel.textContent = String(year);
  view.setEra(year);
  return true;
}

function toggleTimeline() {
  if (els.timeline.hidden) {
    if (!configureTimeline()) return; // nothing dated → stay off
    els.timeline.hidden = false;
    els.timelineBtn.classList.add("active");
  } else {
    els.timeline.hidden = true;
    els.timelineBtn.classList.remove("active");
    view.setEra(null);
  }
}

// ---- duplicate detection + merge ----
async function openDuplicates() {
  els.dedupeModal.hidden = false;
  els.dedupeList.innerHTML = '<div class="dedupe-empty">Scanning…</div>';
  try {
    renderDuplicates(await api.duplicates());
  } catch (err) {
    els.dedupeList.innerHTML = `<div class="dedupe-empty">${err.message}</div>`;
  }
}

function renderDuplicates(pairs) {
  if (!pairs.length) {
    els.dedupeList.innerHTML = '<div class="dedupe-empty">No possible duplicates found. 🎉</div>';
    return;
  }
  els.dedupeList.innerHTML = pairs
    .map((p) => {
      const a = p.a.display_name;
      const b = p.b.display_name;
      return `<div class="dedupe-pair">
        <div class="dedupe-reason">${p.reason}</div>
        <div class="dedupe-people">
          <div class="dedupe-person">${a}<div class="dp-sub">#${p.a.id}</div></div>
          <div class="vs">vs</div>
          <div class="dedupe-person">${b}<div class="dp-sub">#${p.b.id}</div></div>
        </div>
        <div class="dedupe-keep">
          <button class="btn" data-keep="${p.a.id}" data-merge="${p.b.id}">Keep ${a}</button>
          <button class="btn" data-keep="${p.b.id}" data-merge="${p.a.id}">Keep ${b}</button>
        </div>
      </div>`;
    })
    .join("");
}

async function mergePair(keepId, mergeId) {
  try {
    await api.mergePersons(keepId, mergeId);
    // If either side of the merge was selected/compared, drop the stale id.
    if (String(state.selectedId) === String(mergeId)) state.selectedId = keepId;
    await loadTree();
    renderDuplicates(await api.duplicates()); // refresh the remaining pairs in place
  } catch (err) {
    setStatus(err.message, true);
  }
}

function applyFilter() {
  const text = els.filterText.value.trim().toLowerCase();
  const decade = els.filterDecade.value ? Number(els.filterDecade.value) : null;
  if (!text && decade === null) {
    view.setFilter(null);
    return;
  }
  const match = new Set();
  for (const n of view.raw.nodes) {
    const nameOk = !text || n.name.toLowerCase().includes(text);
    const y = yearOf(n.birth);
    const decadeOk = decade === null || (y !== null && Math.floor(y / 10) * 10 === decade);
    if (nameOk && decadeOk) match.add(n.id);
  }
  view.setFilter(match);
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
    <div class="entity-actions">
      <button class="btn subtle" id="edit-person">Edit</button>
      <button class="btn subtle danger" id="delete-person">Delete</button>
    </div>
    <ul class="events"><li class="muted">Loading events…</li></ul>
    <div class="godparents" id="godparents"></div>
    <div class="add-relatives">
      <span class="add-label">Add relative:</span>
      <button class="btn subtle" data-rel="parent">+ Parent</button>
      <button class="btn subtle" data-rel="spouse">+ Spouse</button>
      <button class="btn subtle" data-rel="child">+ Child</button>
    </div>
    <div class="photo-add">
      <label class="btn subtle photo-file-btn">+ Photo<input type="file" id="photo-file" accept="image/*" hidden /></label>
      <input type="url" id="photo-url" placeholder="or paste a URL…" />
      <button class="btn subtle" id="photo-add-btn">Add URL</button>
    </div>
    <div class="media-gallery" id="media-gallery"></div>
    <div class="detail-actions">
      <button class="btn subtle" data-slot="0">Set as A</button>
      <button class="btn subtle" data-slot="1">Set as B</button>
    </div>`;

  // Edit / delete this person.
  els.detail.querySelector("#edit-person").addEventListener("click", () => editPerson(id));
  els.detail.querySelector("#delete-person").addEventListener("click", () => removePerson(id));

  // Add-relative handlers.
  els.detail.querySelectorAll("button[data-rel]").forEach((b) =>
    b.addEventListener("click", async () => {
      const form = await openPersonForm(`Add ${b.dataset.rel}`, {}, {
        showPedigree: b.dataset.rel !== "spouse",
      });
      if (!form) return;
      setStatus(`Adding ${b.dataset.rel}…`);
      try {
        await addRelative(b.dataset.rel, id, form);
        await loadTree();
        renderDetail(id);
        setStatus(`${b.dataset.rel} added`);
      } catch (err) {
        setStatus(err.message, true);
      }
    })
  );

  // Photo upload (file picker + drag-and-drop onto the avatar).
  const uploadFile = async (file) => {
    if (!file) return;
    setStatus("Uploading photo…");
    try {
      await api.uploadMedia(id, file, { is_primary: true });
      await loadTree();
      renderDetail(id);
      setStatus("Photo added");
    } catch (err) {
      setStatus(err.message, true);
    }
  };
  els.detail
    .querySelector("#photo-file")
    .addEventListener("change", (e) => uploadFile(e.target.files[0]));

  const avatarDrop = els.detail.querySelector("#detail-avatar");
  ["dragenter", "dragover"].forEach((ev) =>
    avatarDrop.addEventListener(ev, (e) => {
      e.preventDefault();
      avatarDrop.classList.add("drop-hover");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    avatarDrop.addEventListener(ev, (e) => {
      e.preventDefault();
      avatarDrop.classList.remove("drop-hover");
    })
  );
  avatarDrop.addEventListener("drop", (e) => uploadFile(e.dataTransfer.files[0]));
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

  // Load events + media + associations in parallel.
  try {
    const [events, media, associations] = await Promise.all([
      api.personEvents(id),
      api.personMedia(id),
      api.personAssociations(id),
    ]);
    const ul = els.detail.querySelector(".events");
    ul.innerHTML = events.length
      ? events
          .map(
            (e) =>
              `<li><span class="etype">${eventLabel(e.type)}</span> ${e.date_value || ""} ${
                e.place ? "· " + e.place : ""
              }</li>`
          )
          .join("")
      : `<li class="muted">No events recorded.</li>`;

    const primary = media.find((m) => m.is_primary) || media[0];
    const avatar = els.detail.querySelector("#detail-avatar");
    if (primary) {
      avatar.style.backgroundImage = `url("${primary.url}")`;
      avatar.style.backgroundPosition = `${primary.focal_x ?? 50}% ${primary.focal_y ?? 50}%`;
      avatar.classList.add("has-photo");
      avatar.textContent = "";
      avatar.title = "Click where the face is to set the focus point";
      avatar.onclick = async (e) => {
        const r = avatar.getBoundingClientRect();
        const fx = Math.min(100, Math.max(0, Math.round(((e.clientX - r.left) / r.width) * 100)));
        const fy = Math.min(100, Math.max(0, Math.round(((e.clientY - r.top) / r.height) * 100)));
        try {
          await api.updateMedia(primary.id, { focal_x: fx, focal_y: fy });
          await loadTree();
          renderDetail(id);
        } catch (err) {
          setStatus(err.message, true);
        }
      };
    } else {
      avatar.textContent = (displayName(p)[0] || "?").toUpperCase();
    }
    renderGallery(id, media);
    renderGodparents(id, associations);
  } catch {
    /* leave the loading text */
  }
}

// Godparent links touching this person, plus a picker to add a new godparent.
function renderGodparents(id, assocs) {
  const box = els.detail.querySelector("#godparents");
  if (!box) return;
  const rows = assocs
    .map((a) => {
      const otherId = a.from_person_id === id ? a.to_person_id : a.from_person_id;
      const role = a.to_person_id === id ? "godparent" : "godchild";
      return `<li><span>${personName(otherId)} <span class="gp-label">(${role})</span></span>
        <button class="gp-remove" data-gp="${a.id}" title="Remove">×</button></li>`;
    })
    .join("");
  const existing = new Set(assocs.filter((a) => a.to_person_id === id).map((a) => a.from_person_id));
  const options = ['<option value="">+ Add a godparent…</option>'];
  for (const [pid, person] of state.people) {
    const n = Number(pid);
    if (n === id || existing.has(n)) continue;
    options.push(`<option value="${pid}">${displayName(person)}</option>`);
  }
  box.innerHTML = `
    <div class="gp-label">Godparents / godchildren</div>
    <ul>${rows || '<li class="muted">None yet.</li>'}</ul>
    <div class="gp-add"><select id="gp-select">${options.join("")}</select></div>`;

  box.querySelectorAll("button[data-gp]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await api.deleteAssociation(Number(b.dataset.gp));
        await loadTree();
        renderDetail(id);
      } catch (err) {
        setStatus(err.message, true);
      }
    })
  );
  box.querySelector("#gp-select").addEventListener("change", async (e) => {
    const godparentId = Number(e.target.value);
    if (!godparentId) return;
    try {
      // from = the chosen godparent, to = this person (the godchild)
      await api.addAssociation(godparentId, { to_person_id: id, type: "GODPARENT" });
      await loadTree();
      renderDetail(id);
    } catch (err) {
      setStatus(err.message, true);
    }
  });
}

// Thumbnails of every photo on a person: click ★ to make it the main avatar, × to remove.
function renderGallery(id, media) {
  const gallery = els.detail.querySelector("#media-gallery");
  if (!gallery) return;
  gallery.innerHTML = media
    .map(
      (m) => `
      <div class="thumb ${m.is_primary ? "is-primary" : ""}" style="background-image:url('${m.url}')">
        <button class="thumb-btn star" data-star="${m.id}" title="Set as main photo">★</button>
        <button class="thumb-btn del" data-del="${m.id}" title="Remove photo">×</button>
      </div>`
    )
    .join("");
  gallery.querySelectorAll("button[data-star]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await api.updateMedia(Number(b.dataset.star), { is_primary: true });
        await loadTree();
        renderDetail(id);
      } catch (err) {
        setStatus(err.message, true);
      }
    })
  );
  gallery.querySelectorAll("button[data-del]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await api.deleteMedia(Number(b.dataset.del));
        await loadTree();
        renderDetail(id);
      } catch (err) {
        setStatus(err.message, true);
      }
    })
  );
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

// Headers here must match the spreadsheet importer's recognized columns.
const TEMPLATE_HEADERS = [
  "First name", "Last name", "Sex", "Date of birth", "Birth place", "Date of death",
  "Father's full name", "Mother's full name", "Spouse's full name", "Notes",
];

function downloadBlankTemplate() {
  const row = TEMPLATE_HEADERS.map((h) => (/[",\n]/.test(h) ? `"${h.replace(/"/g, '""')}"` : h)).join(",");
  const blob = new Blob([`${row}\r\n`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "family_intake_template.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

els.templateBtn.addEventListener("click", downloadBlankTemplate);

els.importCsvInput.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  setStatus("Importing spreadsheet…");
  try {
    const r = await api.importCsv(file);
    const bits = [`${r.persons} people`];
    if (r.stubs) bits.push(`${r.stubs} referenced added`);
    if (r.families) bits.push(`${r.families} families`);
    setStatus(`Imported ${bits.join(", ")}`);
    state.selectedId = null;
    await loadTree();
    if (r.warnings && r.warnings.length) {
      // Surface unmatched/ambiguous names so the owner can fix them by hand.
      alert(`Imported with ${r.warnings.length} note(s):\n\n• ${r.warnings.join("\n• ")}`);
    }
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    e.target.value = "";
  }
});

els.addPersonBtn.addEventListener("click", async () => {
  const form = await openPersonForm("Add person");
  if (!form) return;
  setStatus("Adding person…");
  try {
    const newId = await createPersonFromForm(form);
    await loadTree();
    selectPerson(newId);
    setStatus("Person added");
  } catch (err) {
    setStatus(err.message, true);
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
  const privacy = els.privacyToggle.checked ? "living" : "none";
  window.open(api.exportUrl("5.5.1", privacy), "_blank");
});

els.privacyToggle.addEventListener("change", () => view.setPrivacy(els.privacyToggle.checked));

els.reloadBtn.addEventListener("click", loadTree);
els.viewMode.addEventListener("change", loadTree);
els.layoutMode.addEventListener("change", () => view.setLayout(els.layoutMode.value));
els.timelineBtn.addEventListener("click", toggleTimeline);
els.timelineOff.addEventListener("click", toggleTimeline);
els.eraSlider.addEventListener("input", () => {
  const year = Number(els.eraSlider.value);
  els.eraLabel.textContent = String(year);
  view.setEra(year);
});
els.dedupeBtn.addEventListener("click", openDuplicates);
els.dedupeClose.addEventListener("click", () => {
  els.dedupeModal.hidden = true;
});
els.dedupeList.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-keep]");
  if (btn) mergePair(btn.dataset.keep, btn.dataset.merge);
});
els.filterText.addEventListener("input", applyFilter);
els.filterDecade.addEventListener("change", applyFilter);
els.clearCompare.addEventListener("click", () => {
  state.compare = [null, null];
  renderSlots();
  view.setComparison([]);
  maybeAnalyse();
});

// initial load
loadTree();
