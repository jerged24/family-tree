"""Browser UI tests for the D3 / d3-dag frontend (run with ``pytest -m e2e``)."""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import FIXTURE

pytestmark = pytest.mark.e2e


def _node(page: Page, name: str):
    """Locator for the tree node whose card shows ``name``."""
    return page.locator("#tree-svg g.node", has_text=name).first


# SVG nodes drift during the initial fit-to-view zoom transition, so we dispatch
# DOM click events (which the app's handlers process identically) rather than
# relying on physical-click actionability against a moving target.
def _select(page: Page, name: str) -> None:
    _node(page, name).locator("rect.card").dispatch_event("click")


def _toggle(page: Page, name: str) -> None:
    _node(page, name).locator("circle.toggle").dispatch_event("click")


def _login(page: Page) -> None:
    """Wait for the login overlay to appear, then authenticate."""
    page.wait_for_selector("#login-password", state="visible")
    page.fill("#login-password", "test-pass")
    page.locator("#login-form button[type=submit]").click()
    page.wait_for_selector("#login-overlay", state="hidden")


# --------------------------------------------------------------------------- #
def test_tree_renders_all_people(page: Page, live):
    live.seed()
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#tree-svg g.node")

    names = page.eval_on_selector_all(
        "#tree-svg g.node text.name", "els => els.map(e => e.textContent)"
    )
    assert set(names) == {"John Smith", "Mary Jones", "Carol Smith", "David Smith Jr"}
    assert page.locator("#tree-svg path.link").count() == 4
    # David is adopted → both parent edges are dashed.
    assert page.locator("#tree-svg path.link.ped-adopted").count() == 2
    expect(page.locator("#empty-state")).to_be_hidden()


def test_status_reports_counts(page: Page, live):
    live.seed()
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#tree-svg g.node")
    expect(page.locator("#status")).to_contain_text("4 people")


def test_relationship_analysis(page: Page, live):
    live.seed()
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#tree-svg g.node")

    _select(page, "John Smith")
    page.locator('#detail button[data-slot="0"]').click()
    _select(page, "Carol Smith")
    page.locator('#detail button[data-slot="1"]').click()

    verdict = page.locator("#analysis .verdict")
    expect(verdict).to_contain_text("John Smith's child")
    expect(page.locator("#analysis")).to_contain_text("0.2500")  # kinship φ
    expect(page.locator("#analysis")).to_contain_text("50.00%")  # coefficient r
    # John → Carol path highlights both nodes and the connecting link.
    expect(page.locator("#tree-svg g.node.on-path")).to_have_count(2)
    expect(page.locator("#tree-svg path.link.on-path")).to_have_count(1)


def test_adopted_child_zero_kinship(page: Page, live):
    live.seed()
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#tree-svg g.node")

    _select(page, "John Smith")
    page.locator('#detail button[data-slot="0"]').click()
    _select(page, "David Smith Jr")
    page.locator('#detail button[data-slot="1"]').click()

    expect(page.locator("#analysis")).to_contain_text("0.0000")  # no genetic kinship
    expect(page.locator("#tree-svg g.node.on-path")).to_have_count(2)  # social path still exists


def test_collapse_hides_children_when_both_parents_collapsed(page: Page, live):
    live.seed()
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#tree-svg g.node")
    assert page.locator("#tree-svg g.node").count() == 4

    for name in ("John Smith", "Mary Jones"):
        _toggle(page, name)

    # Carol & David descend only from these two → now hidden.
    page.wait_for_function("document.querySelectorAll('#tree-svg g.node').length === 2")
    names = page.eval_on_selector_all(
        "#tree-svg g.node text.name", "els => els.map(e => e.textContent)"
    )
    assert set(names) == {"John Smith", "Mary Jones"}


def test_import_via_file_input(page: Page, live):
    # No seeding — start from an empty database.
    page.goto(live.url())
    _login(page)
    expect(page.locator("#empty-state")).to_be_visible()

    page.set_input_files("#import-input", str(FIXTURE))

    # Importing renders the tree and clears the empty-state overlay.
    page.wait_for_selector("#tree-svg g.node")
    assert page.locator("#tree-svg g.node").count() == 4
    expect(page.locator("#empty-state")).to_be_hidden()
    expect(page.locator("#status")).to_contain_text("4 people")


def test_load_sample_button(page: Page, live):
    # Empty DB → click "Load sample" → the bundled 9-person family renders.
    page.goto(live.url())
    _login(page)
    expect(page.locator("#empty-state")).to_be_visible()
    page.locator("#sample-btn").click()
    page.wait_for_function("document.querySelectorAll('#tree-svg g.node').length === 9")
    names = page.eval_on_selector_all(
        "#tree-svg g.node text.name", "els => els.map(e => e.textContent)"
    )
    assert "Robert King" in names and "Emily King" in names


def test_add_photo_shows_avatar_on_node(page: Page, live):
    live.seed()
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#tree-svg g.node")

    _select(page, "John Smith")
    page.wait_for_selector("#photo-url")
    tiny_gif = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
    page.fill("#photo-url", tiny_gif)
    page.locator("#photo-add-btn").click()

    # After the reload, John's node shows a photo avatar (image href set, initial hidden).
    page.wait_for_function("""() => {
            const g = [...document.querySelectorAll('#tree-svg g.node')]
              .find(n => n.querySelector('text.name')?.textContent === 'John Smith');
            const img = g && g.querySelector('image.avatar-img');
            return img && img.getAttribute('href') && img.style.display !== 'none';
        }""")


def _has_node(name: str) -> str:
    return (
        "[...document.querySelectorAll('#tree-svg g.node text.name')]"
        f".some(t => t.textContent === {name!r})"
    )


def test_add_edit_delete_person(page: Page, live):
    """Owner data entry: add a person, rename via Edit (node label must update
    in-session), then Delete."""
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#empty-state", state="attached")

    # Add a person via the toolbar modal.
    page.click("#add-person-btn")
    page.wait_for_selector("#pf-given", state="visible")
    page.fill("#pf-given", "Ada")
    page.fill("#pf-surname", "Lovelace")
    page.fill("#pf-dob", "10 DEC 1815")
    page.locator("#person-form button[type=submit]").click()
    page.wait_for_function(_has_node("Ada Lovelace"))

    # Edit: the form pre-fills, rename the surname; the node label must refresh.
    _select(page, "Ada Lovelace")
    page.wait_for_selector("#edit-person")
    page.click("#edit-person")
    page.wait_for_selector("#pf-given", state="visible")
    assert page.input_value("#pf-surname") == "Lovelace"  # pre-filled
    page.fill("#pf-surname", "Byron")
    page.locator("#person-form button[type=submit]").click()
    page.wait_for_function(_has_node("Ada Byron"))

    # Delete (accept the confirm dialog); the node disappears.
    _select(page, "Ada Byron")
    page.wait_for_selector("#delete-person")
    page.once("dialog", lambda d: d.accept())
    page.click("#delete-person")
    page.wait_for_function(f"!{_has_node('Ada Byron')}")


def test_name_capitalization_and_adopted_child(page: Page, live):
    """Names auto-capitalize; adding an adopted child yields a dashed edge."""
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#empty-state", state="attached")

    # Lowercase input is capitalized.
    page.click("#add-person-btn")
    page.wait_for_selector("#pf-given", state="visible")
    page.fill("#pf-given", "john")
    page.fill("#pf-surname", "doe")
    page.locator("#person-form button[type=submit]").click()
    page.wait_for_function(_has_node("John Doe"))

    # Add an ADOPTED child → the relationship-type dropdown shows, and the edge is dashed.
    _select(page, "John Doe")
    page.wait_for_selector("#detail button[data-rel='child']")
    page.locator("#detail button[data-rel='child']").click()
    page.wait_for_selector("#pf-pedigree-wrap:not([hidden])")
    page.fill("#pf-given", "junior")
    page.fill("#pf-surname", "doe")
    page.select_option("#pf-pedigree", "ADOPTED")
    page.locator("#person-form button[type=submit]").click()
    page.wait_for_function(_has_node("Junior Doe"))
    expect(page.locator("#tree-svg path.link.ped-adopted")).to_have_count(1)


def test_filter_dims_non_matching(page: Page, live):
    """The name filter dims people who don't match and clears cleanly."""
    live.seed()
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#tree-svg g.node")

    page.fill("#filter-text", "smith")  # fixture surnames are Smith and Jones
    page.wait_for_function("document.querySelectorAll('#tree-svg g.node.dimmed').length > 0")
    dimmed = page.eval_on_selector_all(
        "#tree-svg g.node.dimmed text.name", "els => els.map(e => e.textContent)"
    )
    assert any("Jones" in n for n in dimmed)  # Mary Jones doesn't match → dimmed
    assert not any("Smith" in n for n in dimmed)  # Smiths match → not dimmed

    page.fill("#filter-text", "")
    page.wait_for_function("document.querySelectorAll('#tree-svg g.node.dimmed').length === 0")


def test_privacy_hides_living_people(page: Page, live):
    """The privacy toggle masks living people (Carol b.~1930, no death) as 'Living'."""
    live.seed()
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#tree-svg g.node")

    page.check("#privacy-toggle")
    page.wait_for_function(_has_node("Living"))
    names = page.eval_on_selector_all(
        "#tree-svg g.node text.name", "els => els.map(e => e.textContent)"
    )
    assert "Carol Smith" not in names  # b. ~1930, no death → living, masked
    assert "John Smith" in names  # d. 1970 → not living, still shown

    page.uncheck("#privacy-toggle")
    page.wait_for_function(_has_node("Carol Smith"))


def test_layout_mode_switch(page: Page, live):
    """Switching the layout mode re-lays-out the tree (node transforms change)."""
    live.seed()
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#tree-svg g.node")

    before = page.eval_on_selector_all(
        "#tree-svg g.node", "els => els.map(e => e.getAttribute('transform'))"
    )
    page.select_option("#layout-mode", "radial")
    page.wait_for_function(
        "prev => JSON.stringify([...document.querySelectorAll('#tree-svg g.node')]"
        ".map(e => e.getAttribute('transform'))) !== prev",
        arg=json.dumps(before),
    )
    assert page.locator("#tree-svg g.node").count() == 4  # all people survive the relayout


def test_timeline_highlights_year(page: Page, live):
    """The timeline slider dims people who weren't alive in the chosen year."""
    live.seed()
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#tree-svg g.node")

    page.click("#timeline-btn")
    page.wait_for_selector("#timeline:not([hidden])")
    # Fixture: John b.1900 d.1970; Mary b.1905; Carol b.~1930. In 1902 only John is alive.
    page.eval_on_selector(
        "#era-slider",
        "el => { el.value = '1902'; el.dispatchEvent(new Event('input', {bubbles: true})); }",
    )
    page.wait_for_function(
        "() => { const d = [...document.querySelectorAll('#tree-svg g.node.dimmed text.name')]"
        ".map(t => t.textContent);"
        " return d.includes('Mary Jones') && d.includes('Carol Smith')"
        " && !d.includes('John Smith'); }"
    )
    # Turning the timeline off clears all dimming.
    page.click("#timeline-off")
    page.wait_for_function("document.querySelectorAll('#tree-svg g.node.dimmed').length === 0")


def test_godparent_link(page: Page, live):
    """Adding a godparent creates an overlay link and lists it in the detail panel."""
    live.seed()
    page.goto(live.url())
    _login(page)
    page.wait_for_selector("#tree-svg g.node")

    _select(page, "Carol Smith")
    page.wait_for_selector("#gp-select")
    page.select_option("#gp-select", label="John Smith")  # John becomes Carol's godparent

    page.wait_for_function("document.querySelectorAll('#tree-svg path.assoc').length === 1")
    expect(page.locator("#godparents")).to_contain_text("John Smith")
