"""Tests for the low-level GEDCOM tokenizer and tree builder."""

from __future__ import annotations

from backend.app.parsers.structure import build_forest, parse_records, tokenize


def test_tokenize_parses_level_xref_tag_value():
    lines = tokenize("0 @I1@ INDI\n1 NAME John /Smith/\n1 SEX M\n")
    assert [(line.level, line.xref, line.tag, line.value) for line in lines] == [
        (0, "@I1@", "INDI", ""),
        (1, None, "NAME", "John /Smith/"),
        (1, None, "SEX", "M"),
    ]


def test_pointer_value_is_not_mistaken_for_xref():
    (line,) = tokenize("1 FAMC @F1@")
    assert line.tag == "FAMC"
    assert line.xref is None
    assert line.value == "@F1@"


def test_blank_and_malformed_lines_are_skipped():
    lines = tokenize("0 HEAD\n\n   \ngarbage-with-no-level\n0 TRLR\n")
    assert [line.tag for line in lines] == ["HEAD", "TRLR"]


def test_build_forest_nests_children_by_level():
    roots = parse_records("0 @I1@ INDI\n1 NAME John /Smith/\n2 GIVN John\n1 SEX M\n")
    assert len(roots) == 1
    indi = roots[0]
    assert indi.tag == "INDI" and indi.xref == "@I1@"
    name = indi.first("NAME")
    assert name is not None and name.value_of("GIVN") == "John"
    assert indi.value_of("SEX") == "M"


def test_bom_is_stripped():
    roots = parse_records("﻿0 HEAD\n0 TRLR\n")
    assert [r.tag for r in roots] == ["HEAD", "TRLR"]


def test_cont_and_conc_fold_into_parent_value():
    roots = parse_records("0 @I1@ INDI\n1 NOTE Line one\n2 CONT Line two\n2 CONC  continued\n")
    note = roots[0].first("NOTE")
    assert note is not None
    assert note.value == "Line one\nLine two continued"


def test_all_returns_repeated_children():
    roots = build_forest(tokenize("0 @F1@ FAM\n1 CHIL @I3@\n1 CHIL @I4@\n"))
    assert [c.value for c in roots[0].all("CHIL")] == ["@I3@", "@I4@"]
