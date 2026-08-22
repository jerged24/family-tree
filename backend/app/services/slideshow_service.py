"""Build a self-contained HTML slideshow of the family — one slide per person.

The output is a single ``.html`` file with all CSS, JS, and photos inlined (local
uploads are base64-embedded), so it opens and presents in any browser, offline,
with no dependencies. People are ordered oldest-first (by birth year) to read as a
chronological family story.
"""

from __future__ import annotations

import base64
import html
import mimetypes
import re
from collections import defaultdict

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Event, Person, Relationship
from backend.app.models.base import EventType, RelationshipRole, Sex
from backend.app.services.graph_service import GraphService
from backend.app.services.tree_service import _display_dates, _photos
from backend.app.storage import media_dir

_YEAR = re.compile(r"\b(\d{4})\b")


def _name(p: Person) -> str:
    parts = [p.name_prefix, p.given_name, p.surname, p.name_suffix]
    return " ".join(x for x in parts if x) or "(unknown)"


def _year(s: str | None) -> int:
    m = _YEAR.search(s or "")
    return int(m.group(1)) if m else 9999  # undated people sort to the end


def _lifespan(birth: str | None, death: str | None) -> str:
    if birth and death:
        return f"{birth} – {death}"
    if birth:
        return f"b. {birth}"
    if death:
        return f"d. {death}"
    return ""


def _embed_photo(url: str | None) -> str | None:
    """Inline a local upload as a data URI; pass data:/http(s) URLs through as-is."""
    if not url:
        return None
    if url.startswith(("data:", "http://", "https://")):
        return url
    if url.startswith("/media/files/"):
        path = media_dir() / url.rsplit("/", 1)[-1]
        if path.is_file():
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
    return url


def _birthplaces(db: Session, ids: set[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    if not ids:
        return out
    rows = db.scalars(
        select(Event).where(Event.person_id.in_(ids), Event.type == EventType.BIRTH)
    ).all()
    for ev in rows:
        if ev.place:
            out[ev.person_id] = ev.place
    return out


def _spouses(db: Session) -> dict[int, list[int]]:
    partners_by_family: dict[int, list[int]] = defaultdict(list)
    for r in db.scalars(select(Relationship).where(Relationship.role == RelationshipRole.PARTNER)):
        partners_by_family[r.family_id].append(r.person_id)
    out: dict[int, list[int]] = defaultdict(list)
    for partners in partners_by_family.values():
        for pid in partners:
            for other in partners:
                if other != pid and other not in out[pid]:
                    out[pid].append(other)
    return out


def _rel_row(label: str, names: list[str]) -> str:
    if not names:
        return ""
    joined = html.escape(" · ".join(names))
    return f'<div class="rel"><span class="rlabel">{label}</span>{joined}</div>'


def _ordered_people(gs, persons, dates, anchor_id):
    """Order people for the show: father's ancestors, then mother's, then the anchor
    and their descendants, then anyone else — each section oldest-first (down the line).
    With no anchor, the whole family oldest-first.
    """

    def key(p):
        return (_year(dates.get(p.id, (None, None))[0]), _name(p))

    if anchor_id is None or anchor_id not in persons:
        return sorted(persons.values(), key=key)

    # Generational order (ancestors before descendants) is more reliable than birth
    # year for "going down the line"; birth year / name only break ties within a rank.
    try:
        topo = {n: i for i, n in enumerate(nx.topological_sort(gs.graph))}
    except Exception:  # noqa: BLE001 - a cyclic graph shouldn't happen; fall back gracefully
        topo = {}

    def gen_key(p):
        return (topo.get(p.id, 0), *key(p))

    parents = gs.parents(anchor_id)
    father = next((pid for pid in parents if persons[pid].sex == Sex.MALE), None)
    mother = next((pid for pid in parents if persons[pid].sex == Sex.FEMALE), None)
    leftover = [pid for pid in parents if pid not in (father, mother)]
    if father is None and leftover:
        father = leftover.pop(0)
    if mother is None and leftover:
        mother = leftover.pop(0)

    paternal = (gs.ancestors(father) | {father}) if father is not None else set()
    maternal = (gs.ancestors(mother) | {mother}) if mother is not None else set()
    maternal -= paternal  # a shared ancestor stays on the paternal side
    descendants = gs.descendants(anchor_id) | {anchor_id}

    ordered: list[Person] = []
    seen: set[int] = set()

    def add(bucket) -> None:
        for p in sorted((persons[i] for i in bucket if i in persons), key=gen_key):
            if p.id not in seen:
                seen.add(p.id)
                ordered.append(p)

    add(paternal)  # father's ancestors, oldest first — down to the father
    add(maternal)  # then mother's ancestors, oldest first
    add(descendants)  # the anchor and their bloodline going down
    add(set(persons) - seen)  # anyone else, so no one is left out
    return ordered


def build_slideshow(
    db: Session, title: str = "Our Family Tree", anchor_id: int | None = None, seconds: float = 6.0
) -> str:
    gs = GraphService(db)
    g = gs.graph
    persons = {p.id: p for p in db.scalars(select(Person))}
    ids = set(persons)
    dates = _display_dates(db, ids)
    photos = _photos(db, ids)
    places = _birthplaces(db, ids)
    spouses = _spouses(db)

    def nm(pid: int) -> str:
        return g.nodes[pid]["name"] if pid in g else _name(persons[pid])

    ordered = _ordered_people(gs, persons, dates, anchor_id)

    slides = [
        '<section class="slide title active">'
        f"<h1>{html.escape(title)}</h1>"
        f'<p class="count">{len(ordered)} '
        f'{"person" if len(ordered) == 1 else "people"}</p>'
        '<p class="hint">Playing automatically · ← → to move · ⏸ to pause</p>'
        "</section>"
    ]

    for p in ordered:
        birth, death = dates.get(p.id, (None, None))
        photo = _embed_photo(photos.get(p.id, (None,))[0]) if p.id in photos else None
        fx, fy = (photos[p.id][1], photos[p.id][2]) if p.id in photos else (50.0, 50.0)
        if photo:
            media = (
                f'<div class="photo"><img src="{html.escape(photo, quote=True)}" alt="" '
                f'style="object-position:{fx}% {fy}%"></div>'
            )
        else:
            initial = html.escape((_name(p)[:1] or "?").upper())
            media = (
                f'<div class="photo initial sex-{html.escape(p.sex.value.lower())}">{initial}</div>'
            )

        life = html.escape(_lifespan(birth, death))
        place = places.get(p.id)
        rels = (
            _rel_row("Parents", [nm(x) for x in gs.parents(p.id)])
            + _rel_row("Spouse", [nm(x) for x in spouses.get(p.id, [])])
            + _rel_row("Children", [nm(x) for x in gs.children(p.id)])
        )
        notes = f'<p class="notes">{html.escape(p.notes)}</p>' if p.notes else ""

        slides.append(
            '<section class="slide">'
            f"{media}"
            f"<h2>{html.escape(_name(p))}</h2>"
            + (f'<p class="life">{life}</p>' if life else "")
            + (f'<p class="place">Born in {html.escape(place)}</p>' if place else "")
            + (f'<div class="rels">{rels}</div>' if rels else "")
            + notes
            + "</section>"
        )

    return (
        _PAGE.replace("{{TITLE}}", html.escape(title))
        .replace("{{INTERVAL}}", str(int(max(2.0, seconds) * 1000)))
        .replace("{{SLIDES}}", "\n".join(slides))
    )


# Self-contained page shell: all CSS/JS inline, no external requests.
_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
  :root { --bg:#101826; --card:#182234; --ink:#f3f6fb; --muted:#9fb0c7; --accent:#6ea8fe; }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; background:var(--bg); color:var(--ink);
    font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  .deck { height:100%; }
  .slide { position:fixed; inset:0; display:none; flex-direction:column;
    align-items:center; justify-content:center; text-align:center; padding:6vmin; gap:1.2rem; }
  .slide.active { display:flex; animation:fade .4s ease; }
  @keyframes fade { from { opacity:0; transform:translateY(8px); } to { opacity:1; } }
  .title h1 { font-size:8vmin; margin:0; }
  .title .count { font-size:3vmin; color:var(--accent); margin:0; }
  .title .hint { font-size:2.2vmin; color:var(--muted); margin-top:2rem; }
  .photo { width:36vmin; height:36vmin; border-radius:50%; overflow:hidden;
    box-shadow:0 10px 40px rgba(0,0,0,.5); border:3px solid var(--card); }
  .photo img { width:100%; height:100%; object-fit:cover; }
  .photo.initial { display:flex; align-items:center; justify-content:center;
    font-size:16vmin; font-weight:700; background:var(--card); color:var(--muted); }
  .photo.initial.sex-m { color:#7db1ff; } .photo.initial.sex-f { color:#ff9ecb; }
  .slide h2 { font-size:6vmin; margin:0; }
  .life { font-size:3vmin; color:var(--accent); margin:0; }
  .place { font-size:2.4vmin; color:var(--muted); margin:0; }
  .rels { display:flex; flex-direction:column; gap:.35rem; margin-top:.6rem; font-size:2.3vmin; }
  .rel .rlabel { color:var(--muted); margin-right:.5rem; font-size:.85em;
    text-transform:uppercase; letter-spacing:.05em; }
  .notes { max-width:70ch; font-size:2.3vmin; color:var(--muted);
    font-style:italic; margin-top:.4rem; }
  .controls { position:fixed; bottom:3vmin; left:50%; transform:translateX(-50%);
    display:flex; align-items:center; gap:1rem; background:rgba(0,0,0,.35);
    padding:.5rem .9rem; border-radius:999px; backdrop-filter:blur(6px); }
  .controls button { font-size:1.4rem; line-height:1; background:none; border:none;
    color:var(--ink); cursor:pointer; padding:.2rem .5rem; border-radius:8px; }
  .controls button:hover { background:rgba(255,255,255,.12); }
  #counter { color:var(--muted); font-variant-numeric:tabular-nums;
    min-width:5ch; text-align:center; }
</style>
</head>
<body>
<div class="deck">
{{SLIDES}}
</div>
<audio id="bgm" loop></audio>
<div class="controls">
  <button id="prev" title="Previous (←)">‹</button>
  <button id="play" title="Play / pause">⏸</button>
  <span id="counter"></span>
  <button id="next" title="Next (→)">›</button>
  <button id="full" title="Full screen">⛶</button>
</div>
<script>
  const slides = [...document.querySelectorAll('.slide')];
  const BGM = "";
  const INTERVAL = {{INTERVAL}};
  const audio = document.getElementById('bgm');
  if (BGM) audio.src = BGM;
  let i = 0, timer = null, playing = false;
  function show(n) {
    i = (n + slides.length) % slides.length;
    slides.forEach((s, k) => s.classList.toggle('active', k === i));
    document.getElementById('counter').textContent = (i + 1) + ' / ' + slides.length;
  }
  function setPlaying(on) {
    playing = on;
    document.getElementById('play').textContent = on ? '⏸' : '▶';
    if (timer) { clearInterval(timer); timer = null; }
    if (on) {
      timer = setInterval(() => show(i + 1), INTERVAL);
      if (audio.src) audio.play().catch(() => {});
    } else if (audio.src) {
      audio.pause();
    }
  }
  document.getElementById('play').onclick = (e) => { e.stopPropagation(); setPlaying(!playing); };
  document.getElementById('next').onclick = (e) => { e.stopPropagation(); show(i + 1); };
  document.getElementById('prev').onclick = (e) => { e.stopPropagation(); show(i - 1); };
  document.getElementById('full').onclick = (e) => {
    e.stopPropagation();
    if (!document.fullscreenElement) document.documentElement.requestFullscreen();
    else document.exitFullscreen();
  };
  addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === ' ') { show(i + 1); e.preventDefault(); }
    else if (e.key === 'ArrowLeft') show(i - 1);
  });
  document.querySelector('.deck').addEventListener('click', (e) => {
    if (!e.target.closest('.controls')) show(i + 1);
  });
  show(0);
  setPlaying(true); // auto-play on open
  // Browsers may block audio until a gesture — start it on the first interaction.
  if (BGM) {
    const kick = () => { if (playing && audio.src) audio.play().catch(() => {}); };
    window.addEventListener('click', kick, { once: true });
    window.addEventListener('keydown', kick, { once: true });
  }
</script>
</body>
</html>
"""
