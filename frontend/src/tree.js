// D3 + d3-dag renderer for the family DAG.
// Vendored locally (frontend/vendor/) so the app has no runtime CDN dependency —
// see frontend/vendor/README.md for versions and how to refresh them.
import * as d3 from "../vendor/d3.js";
import * as d3dag from "../vendor/d3-dag.js";

const NODE_W = 168;
const NODE_H = 52;

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

  render(fit = false) {
    const { visible, childrenMap, byId } = this._visibleIds();
    if (visible.size === 0) {
      this.linkLayer.selectAll("*").remove();
      this.nodeLayer.selectAll("*").remove();
      return;
    }

    const layoutData = [...visible].map((id) => ({
      id,
      parentIds: (byId.get(id).parentIds || []).filter((p) => visible.has(p)),
    }));

    const builder = d3dag.graphStratify();
    const dag = builder(layoutData);

    const layout = d3dag
      .sugiyama()
      .nodeSize([NODE_W + 28, NODE_H + 46])
      .gap([26, 46]);
    layout(dag);

    const nodes = [...dag.nodes()];
    const links = [...dag.links()];
    const pt = (p) => (Array.isArray(p) ? p : [p.x, p.y]);
    const lineGen = d3
      .line()
      .curve(d3.curveMonotoneY)
      .x((p) => pt(p)[0])
      .y((p) => pt(p)[1]);

    // Edge pedigree lookup (source->target) for dashed adopted links.
    const pedigree = new Map(this.raw.edges.map((e) => [`${e.source}->${e.target}`, e.pedigree]));

    // ---- links ----
    this.linkLayer
      .selectAll("path.link")
      .data(links, (l) => `${l.source.data.id}->${l.target.data.id}`)
      .join("path")
      .attr("class", (l) => {
        const key = `${l.source.data.id}->${l.target.data.id}`;
        const adopted = (pedigree.get(key) || "BIRTH") !== "BIRTH";
        return `link${adopted ? " adopted" : ""}`;
      })
      .attr("d", (l) => lineGen(l.points));

    // ---- nodes ----
    const nodeSel = this.nodeLayer
      .selectAll("g.node")
      .data(nodes, (n) => n.data.id)
      .join((enter) => this._enterNode(enter, childrenMap));

    nodeSel.attr("transform", (n) => `translate(${n.x - NODE_W / 2}, ${n.y - NODE_H / 2})`);

    // update sex class + toggle sign on existing nodes
    nodeSel.attr("class", (n) => {
      const info = this.raw.nodes.find((r) => r.id === n.data.id) || {};
      const sexClass = info.sex === "M" ? "male" : info.sex === "F" ? "female" : "other";
      return `node ${sexClass}`;
    });
    // refresh name + dates text (so edits to an existing person show without a full redraw)
    nodeSel.select("text.name").text((n) => this._info(n).name || "(unknown)");
    nodeSel.select("text.dates").text((n) => this._dateLabel(this._info(n)));

    // update avatar photo / initial (handles nodes gaining a photo after a reload)
    nodeSel
      .select("image.avatar-img")
      .attr("href", (n) => this._info(n).photo_url || null)
      .style("display", (n) => (this._info(n).photo_url ? null : "none"));
    nodeSel
      .select("text.avatar-initial")
      .text((n) => (this._info(n).name || "?").trim().charAt(0).toUpperCase())
      .style("display", (n) => (this._info(n).photo_url ? "none" : null));

    nodeSel.select(".toggle-sign").text((n) => (this.collapsed.has(n.data.id) ? "+" : "–"));
    nodeSel
      .select(".toggle")
      .style("display", (n) => (this._hasChildren(n.data.id) ? null : "none"));
    nodeSel
      .select(".toggle-sign")
      .style("display", (n) => (this._hasChildren(n.data.id) ? null : "none"));

    this._applyHighlights();
    if (fit) this.fitToView(nodes);
  }

  _hasChildren(id) {
    return this.raw.nodes.some((n) => (n.parentIds || []).includes(id));
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
    const b = info.birth ? `b. ${info.birth}` : "";
    const d = info.death ? `d. ${info.death}` : "";
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
    this.pathNodeSet = new Set((ids || []).map(String));
    this.pathEdgeSet = new Set();
    for (let i = 0; i < (ids || []).length - 1; i++) {
      const a = String(ids[i]);
      const b = String(ids[i + 1]);
      this.pathEdgeSet.add(`${a}->${b}`);
      this.pathEdgeSet.add(`${b}->${a}`);
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
    this.linkLayer.selectAll("path.link").each((l, i, g) => {
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
