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

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Event, Person, Relationship
from backend.app.models.base import EventType, RelationshipRole
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


def build_slideshow(db: Session, title: str = "Our Family Tree") -> str:
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

    ordered = sorted(
        persons.values(), key=lambda p: (_year(dates.get(p.id, (None, None))[0]), _name(p))
    )

    slides = [
        '<section class="slide title active">'
        f"<h1>{html.escape(title)}</h1>"
        f'<p class="count">{len(ordered)} '
        f'{"person" if len(ordered) == 1 else "people"}</p>'
        '<p class="hint">Use ← → arrow keys, or click, to move through the family</p>'
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

    return _PAGE.replace("{{TITLE}}", html.escape(title)).replace("{{SLIDES}}", "\n".join(slides))


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
<div class="controls">
  <button id="prev" title="Previous (←)">‹</button>
  <span id="counter"></span>
  <button id="next" title="Next (→)">›</button>
  <button id="full" title="Full screen">⛶</button>
</div>
<script>
  const slides = [...document.querySelectorAll('.slide')];
  let i = 0;
  function show(n) {
    i = (n + slides.length) % slides.length;
    slides.forEach((s, k) => s.classList.toggle('active', k === i));
    document.getElementById('counter').textContent = (i + 1) + ' / ' + slides.length;
  }
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
</script>
</body>
</html>
"""
