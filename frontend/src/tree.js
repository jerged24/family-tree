// D3 + d3-dag renderer for the family DAG.
// Vendored locally (frontend/vendor/) so the app has no runtime CDN dependency —
// see frontend/vendor/README.md for versions and how to refresh them.
import * as d3 from "../vendor/d3.js";
import * as d3dag from "../vendor/d3-dag.js";

const NODE_W = 168;
const NODE_H = 52;

// Snap a focal point (percent) to the nearest 9-position SVG alignment so a
// cropped avatar keeps the face in frame.
function focalToAspect(fx = 50, fy = 50) {
  const px = fx < 34 ? "xMin" : fx > 66 ? "xMax" : "xMid";
  const py = fy < 34 ? "YMin" : fy > 66 ? "YMax" : "YMid";
  return `${px}${py} slice`;
}

// First 4-digit year in a GEDCOM-ish date string, or null.
function yearOf(s) {
  const m = (s || "").match(/\b(\d{4})\b/);
  return m ? Number(m[1]) : null;
}

// Possibly-living = no death, and birth unknown or within the last century.
const CURRENT_YEAR = new Date().getFullYear();
function isLiving(info) {
  if (info.death) return false;
  const year = yearOf(info.birth);
  return year === null || year > CURRENT_YEAR - 100;
}

// Was this person alive during `year`? People with no known birth year can't be
// placed on a timeline, so they're treated as "not alive then" (dimmed).
function aliveInYear(info, year) {
  const by = yearOf(info.birth);
  if (by === null || by > year) return false;
  const dy = yearOf(info.death);
  return dy === null || dy >= year;
}

export class TreeView {
  constructor(svgEl, { onSelect, onToggle } = {}) {
    this.svg = d3.select(svgEl);
    this.onSelect = onSelect || (() => {});
    this.onToggle = onToggle || (() => {});

    // Circular clip for node avatars.
    this.svg
      .append("defs")
      .html('<clipPath id="ft-avatar-clip"><circle cx="22" cy="26" r="15"/></clipPath>');

    this.viewport = this.svg.append("g").attr("class", "viewport");
    this.linkLayer = this.viewport.append("g").attr("class", "links");
    this.unionLayer = this.viewport.append("g").attr("class", "unions");
    this.assocLayer = this.viewport.append("g").attr("class", "assocs");
    this.nodeLayer = this.viewport.append("g").attr("class", "nodes");

    this.zoom = d3
      .zoom()
      .scaleExtent([0.15, 2.5])
      .on("zoom", (e) => this.viewport.attr("transform", e.transform));
    this.svg.call(this.zoom);

    this.raw = { nodes: [], edges: [] };
    this.collapsed = new Set();
    this.selectedId = null;
    this.compareIds = [];
    this.pathNodeSet = new Set();
    this.pathEdgeSet = new Set();
    this.filterIds = null; // Set of matching ids, or null for "no filter"
    this.privacy = false; // when true, mask living people's name/dates/photo
    this.eraYear = null; // timeline year, or null for "no timeline"
    this.layoutMode = "topdown"; // topdown | leftright | radial
  }

  setFilter(ids) {
    this.filterIds = ids;
    this._applyDim();
  }

  setEra(year) {
    this.eraYear = year;
    this._applyDim();
  }

  setLayout(mode) {
    if (mode === this.layoutMode) return;
    this.layoutMode = mode;
    this.render(true);
  }

  setPrivacy(on) {
    this.privacy = on;
    this.render(false);
  }

  _masked(node) {
    return this.privacy && isLiving(this._info(node));
  }

  // A node is dimmed if it fails the name/decade filter or falls outside the
  // active timeline year. The two conditions combine (either one dims it).
  _dimmed(id) {
    if (this.filterIds !== null && !this.filterIds.has(id)) return true;
    if (this.eraYear !== null) {
      const info = this.raw.nodes.find((r) => r.id === id);
      if (info && !aliveInYear(info, this.eraYear)) return true;
    }
    return false;
  }

  _applyDim() {
    this.nodeLayer.selectAll("g.node").classed("dimmed", (n) => this._dimmed(n.data.id));
    this.linkLayer
      .selectAll("path.edge")
      .classed("dimmed", (l) => this._dimmed(l.source.data.id) || this._dimmed(l.target.data.id));
  }

  setGraph(graph) {
    this.raw = graph;
    const ids = new Set(graph.nodes.map((n) => n.id));
    // Drop collapse state for nodes that no longer exist.
    this.collapsed = new Set([...this.collapsed].filter((id) => ids.has(id)));
    this.render(true);
  }

  // ---- visibility given the collapsed set ----
  _visibleIds() {
    const childrenMap = new Map();
    const byId = new Map(this.raw.nodes.map((n) => [n.id, n]));
    for (const n of this.raw.nodes) childrenMap.set(n.id, []);
    for (const n of this.raw.nodes) {
      for (const p of n.parentIds || []) {
        if (childrenMap.has(p)) childrenMap.get(p).push(n.id);
      }
    }
    const roots = this.raw.nodes.filter((n) => (n.parentIds || []).length === 0).map((n) => n.id);
    const visible = new Set();
    const queue = [...roots];
    while (queue.length) {
      const id = queue.shift();
      if (visible.has(id)) continue;
      visible.add(id);
      if (!this.collapsed.has(id)) {
        for (const c of childrenMap.get(id) || []) queue.push(c);
      }
    }
    // Any node never reached (e.g. isolated) still shows.
    for (const n of this.raw.nodes) if (!visible.has(n.id) && (n.parentIds || []).length === 0) visible.add(n.id);
    return { visible, childrenMap, byId };
  }

  // Build the d3-dag input with a marriage-join node per couple: partners point
  // into the join (so the layout sets them side by side), children hang from it.
  _buildLayout(visible) {
    const byId = new Map();
    for (const id of visible) byId.set(id, { id, parentIds: [], union: false });

    for (const fam of this.raw.families || []) {
      const partners = (fam.partners || []).filter((p) => visible.has(p));
      const kids = (fam.children || []).filter((c) => visible.has(c.id));
      if (partners.length === 0) continue; // no visible partner to anchor the join
      if (partners.length < 2 && kids.length === 0) continue; // a lone person — nothing to join
      const uid = `u${fam.id}`;
      const pedById = {};
      for (const c of kids) pedById[c.id] = c.pedigree;
      byId.set(uid, { id: uid, parentIds: partners.slice(), union: true, pedById });
      for (const c of kids) byId.get(c.id).parentIds.push(uid);
    }
    return [...byId.values()];
  }

  render(fit = false) {
    const { visible, childrenMap, byId } = this._visibleIds();
    if (visible.size === 0) {
      this.linkLayer.selectAll("*").remove();
      this.nodeLayer.selectAll("*").remove();
      return;
    }

    const layoutData = this._buildLayout(visible);

    const builder = d3dag.graphStratify();
    const dag = builder(layoutData);

    const layout = d3dag
      .sugiyama()
      // Marriage-join nodes are tiny; person cards get the full card box.
      .nodeSize((node) => (node?.data?.union ? [46, 24] : [NODE_W + 28, NODE_H + 46]))
      .gap([26, 28]);
    layout(dag);

    const nodes = [...dag.nodes()];
    const links = [...dag.links()];
    this._applyLayoutTransform(nodes, links);

    // ---- links: marriage (partner→union) + parentage (union→child) ----
    this.linkLayer
      .selectAll("path.edge")
      .data(links, (l) => `${l.source.data.id}->${l.target.data.id}`)
      .join("path")
      .attr("class", (l) => {
        if (l.target.data.union) return "edge marriage"; // partner → marriage join
        const ped = (l.source.data.pedById || {})[l.target.data.id] || "BIRTH"; // union → child
        return ped === "BIRTH" ? "edge link" : `edge link non-birth ped-${ped.toLowerCase()}`;
      })
      .attr("d", (l) => this._edgePath(l));

    // ---- union (marriage) join markers ----
    this.unionLayer
      .selectAll("g.union")
      .data(
        nodes.filter((n) => n.data.union),
        (n) => n.data.id
      )
      .join((enter) =>
        enter
          .append("g")
          .attr("class", "union")
          .call((g) => {
            // A gold band with a little diamond (band circle + gem silhouette + facet lines).
            g.append("circle").attr("class", "union-band").attr("r", 6);
            g.append("path")
              .attr("class", "union-gem")
              .attr("d", "M-2,-2.2 L2,-2.2 L3,-0.6 L0,3.6 L-3,-0.6 Z");
            g.append("path")
              .attr("class", "union-gem-facets")
              .attr("d", "M-3,-0.6 L3,-0.6 M-2,-2.2 L0,3.6 M2,-2.2 L0,3.6");
          })
      )
      .attr("transform", (n) => `translate(${n.x}, ${n.y})`);

    // ---- association overlay (godparents etc.) — straight dotted lines between person centers ----
    const posById = new Map(nodes.filter((n) => !n.data.union).map((n) => [n.data.id, n]));
    const assocData = (this.raw.associations || []).filter(
      (a) => posById.has(a.source) && posById.has(a.target)
    );
    this.assocLayer
      .selectAll("path.assoc")
      .data(assocData, (a) => `${a.source}~${a.target}~${a.type}`)
      .join("path")
      .attr("class", (a) => `assoc assoc-${a.type.toLowerCase()}`)
      .attr("d", (a) => {
        const s = posById.get(a.source);
        const t = posById.get(a.target);
        return `M${s.x},${s.y} L${t.x},${t.y}`;
      });

    // ---- person nodes (cards) ----
    const nodeSel = this.nodeLayer
      .selectAll("g.node")
      .data(
        nodes.filter((n) => !n.data.union),
        (n) => n.data.id
      )
      .join((enter) => this._enterNode(enter, childrenMap));

    nodeSel.attr("transform", (n) => `translate(${n.x - NODE_W / 2}, ${n.y - NODE_H / 2})`);

    // update sex class + toggle sign on existing nodes
    nodeSel.attr("class", (n) => {
      const info = this.raw.nodes.find((r) => r.id === n.data.id) || {};
      const sexClass = info.sex === "M" ? "male" : info.sex === "F" ? "female" : "other";
      return `node ${sexClass}`;
    });
    // refresh name + dates text (privacy masks living people; also lets edits show live)
    nodeSel.select("text.name").text((n) => (this._masked(n) ? "Living" : this._info(n).name || "(unknown)"));
    nodeSel.select("text.dates").text((n) => (this._masked(n) ? "" : this._dateLabel(this._info(n))));

    // update avatar photo / initial (a masked living person shows no photo)
    const showPhoto = (n) => Boolean(this._info(n).photo_url) && !this._masked(n);
    nodeSel
      .select("image.avatar-img")
      .attr("href", (n) => this._info(n).photo_url || null)
      .attr("preserveAspectRatio", (n) =>
        focalToAspect(this._info(n).photo_focal_x, this._info(n).photo_focal_y)
      )
      .style("display", (n) => (showPhoto(n) ? null : "none"));
    nodeSel
      .select("text.avatar-initial")
      .text((n) => (this._masked(n) ? "•" : (this._info(n).name || "?").trim().charAt(0).toUpperCase()))
      .style("display", (n) => (showPhoto(n) ? "none" : null));

    nodeSel.select(".toggle-sign").text((n) => (this.collapsed.has(n.data.id) ? "+" : "–"));
    nodeSel
      .select(".toggle")
      .style("display", (n) => (this._hasChildren(n.data.id) ? null : "none"));
    nodeSel
      .select(".toggle-sign")
      .style("display", (n) => (this._hasChildren(n.data.id) ? null : "none"));

    this._applyHighlights();
    this._applyDim();
    if (fit) this.fitToView(nodes);
  }

  // Orthogonal (right-angle) connector between two nodes: leaves the source's
  // near edge, turns once at the midpoint, and enters the target's near edge —
  // vertical/horizontal only. Radial stays a straight radial spoke.
  _edgePath(l) {
    const s = l.source;
    const t = l.target;
    if (this.layoutMode === "radial") return `M${s.x},${s.y} L${t.x},${t.y}`;
    if (this.layoutMode === "leftright") {
      const sx = s.data.union ? s.x : s.x + NODE_W / 2;
      const tx = t.data.union ? t.x : t.x - NODE_W / 2;
      const midX = (sx + tx) / 2;
      return `M${sx},${s.y} H${midX} V${t.y} H${tx}`;
    }
    // top-down: down from the source, across, then down into the target
    const sy = s.data.union ? s.y : s.y + NODE_H / 2;
    const ty = t.data.union ? t.y : t.y - NODE_H / 2;
    const midY = (sy + ty) / 2;
    return `M${s.x},${sy} V${midY} H${t.x} V${ty}`;
  }

  // Re-map sugiyama's top-down coordinates into the active layout. Mutates each
  // node's x/y in place; for the alternate modes it also rewrites link waypoints
  // (the straight-line generator then connects the transformed centers).
  _applyLayoutTransform(nodes, links) {
    const mode = this.layoutMode;
    if (mode === "topdown" || !nodes.length) return;

    if (mode === "leftright") {
      for (const n of nodes) [n.x, n.y] = [n.y, n.x];
      for (const l of links) l.points = l.points.map((p) => (Array.isArray(p) ? [p[1], p[0]] : [p.y, p.x]));
      return;
    }

    if (mode === "radial") {
      const xs = nodes.map((n) => n.x);
      const ys = nodes.map((n) => n.y);
      const minX = Math.min(...xs);
      const spanX = Math.max(...xs) - minX || 1;
      const minY = Math.min(...ys);
      const sweep = 1.8 * Math.PI; // leave an angular gap so the ends don't overlap
      for (const n of nodes) {
        const theta = ((n.x - minX) / spanX) * sweep - sweep / 2 + Math.PI / 2;
        const r = n.y - minY + 70; // generations become concentric rings
        n.x = Math.cos(theta) * r;
        n.y = Math.sin(theta) * r;
      }
      for (const l of links) l.points = [[l.source.x, l.source.y], [l.target.x, l.target.y]];
    }
  }

  _hasChildren(id) {
    return (this.raw.families || []).some(
      (f) => (f.partners || []).includes(id) && (f.children || []).length > 0
    );
  }

  _enterNode(enter, childrenMap) {
    const g = enter.append("g").attr("class", "node");

    g.append("rect")
      .attr("class", "card")
      .attr("width", NODE_W)
      .attr("height", NODE_H)
      .attr("rx", 8);

    g.append("rect")
      .attr("class", "sexbar")
      .attr("width", 6)
      .attr("height", NODE_H)
      .attr("rx", 3);

    // Avatar: colored circle with the person's initial, overlaid by a photo if present.
    g.append("circle").attr("class", "avatar-bg").attr("cx", 22).attr("cy", 26).attr("r", 15);
    g.append("text").attr("class", "avatar-initial").attr("x", 22).attr("y", 27);
    g.append("image")
      .attr("class", "avatar-img")
      .attr("x", 7)
      .attr("y", 11)
      .attr("width", 30)
      .attr("height", 30)
      .attr("clip-path", "url(#ft-avatar-clip)")
      .attr("preserveAspectRatio", "xMidYMid slice");

    g.append("text")
      .attr("class", "name")
      .attr("x", 44)
      .attr("y", 21)
      .text((n) => this._info(n).name || "(unknown)");

    g.append("text")
      .attr("class", "dates")
      .attr("x", 44)
      .attr("y", 38)
      .text((n) => this._dateLabel(this._info(n)));

    // collapse toggle (top-right corner)
    g.append("circle")
      .attr("class", "toggle")
      .attr("cx", NODE_W - 12)
      .attr("cy", 12)
      .attr("r", 9);
    g.append("text")
      .attr("class", "toggle-sign")
      .attr("x", NODE_W - 12)
      .attr("y", 12);

    g.on("click", (event, n) => {
      event.stopPropagation();
      // Click on the toggle circle collapses; elsewhere selects.
      const cls = event.target.getAttribute("class") || "";
      if (cls.includes("toggle")) {
        this.toggleCollapse(n.data.id);
      } else {
        this.onSelect(n.data.id);
      }
    });
    g.on("dblclick", (event, n) => {
      event.stopPropagation();
      this.toggleCollapse(n.data.id);
    });

    return g;
  }

  _info(node) {
    return this.raw.nodes.find((r) => r.id === node.data.id) || {};
  }

  _dateLabel(info) {
    const b = info.birth ? `B. ${info.birth}` : "";
    const d = info.death ? `D. ${info.death}` : "";
    return [b, d].filter(Boolean).join("  ·  ");
  }

  toggleCollapse(id) {
    if (!this._hasChildren(id)) return;
    if (this.collapsed.has(id)) this.collapsed.delete(id);
    else this.collapsed.add(id);
    this.onToggle(id, this.collapsed.has(id));
    this.render(false);
  }

  setSelected(id) {
    this.selectedId = id;
    this._applyHighlights();
  }

  setComparison(ids) {
    this.compareIds = ids.filter(Boolean);
    this._applyHighlights();
  }

  setPath(ids) {
    const path = (ids || []).map(String);
    this.pathNodeSet = new Set(path);
    this.pathEdgeSet = new Set();
    // Each parent/child step renders as two legs through the couple's join marker;
    // mark both so the highlight follows the actual drawn lines.
    for (let i = 0; i < path.length - 1; i++) {
      const a = path[i];
      const b = path[i + 1];
      for (const f of this.raw.families || []) {
        const uid = `u${f.id}`;
        const kids = (f.children || []).map((c) => c.id);
        const partners = f.partners || [];
        if (partners.includes(a) && kids.includes(b)) {
          this.pathEdgeSet.add(`${a}->${uid}`).add(`${uid}->${b}`);
        }
        if (partners.includes(b) && kids.includes(a)) {
          this.pathEdgeSet.add(`${b}->${uid}`).add(`${uid}->${a}`);
        }
      }
    }
    this._applyHighlights();
  }

  _applyHighlights() {
    const compare = new Set(this.compareIds.map(String));
    this.nodeLayer.selectAll("g.node").each((n, i, g) => {
      const el = d3.select(g[i]);
      const id = n.data.id;
      el.classed("selected", id === this.selectedId || compare.has(id));
      el.classed("on-path", this.pathNodeSet.has(id));
    });
    this.linkLayer.selectAll("path.edge").each((l, i, g) => {
      const key = `${l.source.data.id}->${l.target.data.id}`;
      d3.select(g[i]).classed("on-path", this.pathEdgeSet.has(key));
    });
  }

  fitToView(nodes) {
    const box = this.svg.node().getBoundingClientRect();
    if (!nodes.length || !box.width) return;
    const xs = nodes.map((n) => n.x);
    const ys = nodes.map((n) => n.y);
    const minX = Math.min(...xs) - NODE_W;
    const maxX = Math.max(...xs) + NODE_W;
    const minY = Math.min(...ys) - NODE_H;
    const maxY = Math.max(...ys) + NODE_H;
    const w = maxX - minX;
    const h = maxY - minY;
    const scale = Math.min(box.width / w, box.height / h, 1.4);
    const tx = (box.width - w * scale) / 2 - minX * scale;
    const ty = (box.height - h * scale) / 2 - minY * scale;
    this.svg
      .transition()
      .duration(400)
      .call(this.zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
  }
}
