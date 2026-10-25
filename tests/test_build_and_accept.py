# -*- coding: utf-8 -*-
"""Build (ledger, conditions, hash assertion) and acceptance rules, on the dummy fixtures."""
import json
import os
import shutil

import pytest

from engine import accept, build_prompts
from engine import common as C
from helpers import FIXTURE_CONFIG, valid_answer


def fixture_cfg(tmp_path):
    """Copy the fixture project so that tests can tamper with files."""
    src = os.path.dirname(os.path.dirname(FIXTURE_CONFIG))
    dst = tmp_path / "fx"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("outputs_example"))
    return C.load_config(str(dst / "config" / "demo.yaml")), dst


def test_extract_block_rule(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text("# t\nheader line\n\n## Body (x)\n\n---\nINSIDE 1\nINSIDE 2\n---\nafter\n---\nlater\n", encoding="utf-8")
    assert C.extract_block(str(p), "Body") == "INSIDE 1\nINSIDE 2"
    with pytest.raises(ValueError):
        C.extract_block(str(p), "Missing")


def test_ledger_counts_and_conditions():
    cfg = C.load_config(FIXTURE_CONFIG)
    rows, texts, mixed = build_prompts.build_ledger(cfg)
    assert len(rows) == 3 * 4 * 2 * 2          # persons x conditions x scenarios x reps
    assert len({r["job_id"] for r in rows}) == len(rows)
    by = {(r["person_id"], r["condition"], r["scenario"], r["rep"]): r for r in rows}
    # seed rule
    assert all(r["params"]["seed"] == 7 * 100 + r["rep"] for r in rows)
    # C0 has no persona block and no person
    c0 = [r for r in rows if r["condition"] == "C0"]
    assert all(r["person_id"] == "" for r in c0)
    assert all("{AUTOBIOGRAPHY}" not in texts[r["job_id"]] and "人物枠" not in texts[r["job_id"]] for r in c0)
    assert len({r["sent_sha256"] for r in c0 if r["scenario"] == "scen_a"}) == 1
    # C3 contains the own marker only; C3W the next person's marker (cyclic)
    mark = {"T1": "甲", "T2": "乙", "T3": "丙"}
    nxt = {"T1": "T2", "T2": "T3", "T3": "T1"}
    for r in rows:
        t = texts[r["job_id"]]
        if r["condition"] == "C3":
            assert mark[r["person_id"]] in t and sum(mark[o] in t for o in mark if o != r["person_id"]) == 0
        if r["condition"] == "C3W":
            m = mark[nxt[r["person_id"]]]
            assert m in t and mark[r["person_id"]] not in t
        if r["condition"] == "C3-mixed":
            assert mark[r["person_id"]] not in t            # none of the person's own episodes remain
    # mixed: same number of episodes, headings renumbered 1..n
    t = texts[by[("T1", "C3-mixed", "scen_a", 1)]["job_id"]]
    assert "（1）見出し" in t and "（2）見出し" in t and "（3）見出し" in t and "（4）" not in t
    assert len(mixed) == 9


def test_mixed_is_deterministic_and_length_matched():
    cfg = C.load_config(FIXTURE_CONFIG)
    persons, bodies, _ = build_prompts.load_people(cfg)
    order = [p["person_id"] for p in persons]
    a, rows_a = build_prompts.mixed_texts(order, bodies)
    b, rows_b = build_prompts.mixed_texts(order, bodies)
    assert a == b and rows_a == rows_b
    for r in rows_a:
        assert r["source_person"] != r["person_id"]
    # within one person, no source episode is used twice
    seen = set()
    for r in rows_a:
        k = (r["person_id"], r["source_person"], r["source_ep_index"])
        assert k not in seen
        seen.add(k)


def test_build_stops_when_a_template_is_edited(tmp_path):
    cfg, dst = fixture_cfg(tmp_path)
    p = dst / "project" / "templates" / "questions.md"
    p.write_text(p.read_text(encoding="utf-8") + "extra\n", encoding="utf-8")
    with pytest.raises(build_prompts.FrozenHashError):
        build_prompts.build(cfg, str(tmp_path / "out"))
    assert not os.path.exists(tmp_path / "out" / "ledger.jsonl")     # nothing was built


def test_params_must_match_frozen_file(tmp_path):
    cfg, dst = fixture_cfg(tmp_path)
    cfg["generation"]["params"]["temperature"] = 0.7
    with pytest.raises(build_prompts.FrozenHashError):
        build_prompts.check_params_match_frozen(cfg)


# ------------------------------------------------------------- acceptance
ACC = C.load_config(FIXTURE_CONFIG)["accept"]


def good():
    return valid_answer(1)


def rules(d):
    v, _ = accept.check_rules(json.dumps(d, ensure_ascii=False), ACC)
    return v


def test_accept_valid():
    assert rules(good()) == []


@pytest.mark.parametrize("mut,expected", [
    (lambda d: d.pop("q3"), ["rule2", "rule5"]),
    (lambda d: d.update(extra=1), ["rule2"]),
    (lambda d: d.update(q1=["A", "A", "B"]), ["rule3"]),
    (lambda d: d.update(q1=["A", "B"]), ["rule3"]),
    (lambda d: d.update(q1=["A", "B", "Z"]), ["rule3"]),
    (lambda d: d.update(q2_category=5), ["rule4"]),
    (lambda d: d.update(q2_category=True), ["rule4"]),
    (lambda d: d.update(q2_category="2"), ["rule4"]),
    (lambda d: d.update(q3="拡大"), ["rule5"]),
    (lambda d: d.update(q5_ranking=["株主", "株主", "顧客", "取引先", "地域社会"]), ["rule6"]),
    (lambda d: d.update(q5_ranking=["株主", "従業員", "顧客", "取引先"]), ["rule6"]),
    (lambda d: d.update(q4_text="  "), ["rule7"]),
    (lambda d: d.update(q6_text=None), ["rule7"]),
])
def test_accept_violations(mut, expected):
    d = good()
    mut(d)
    assert rules(d) == expected


def test_accept_not_json_and_not_object():
    assert accept.check_rules("not json", ACC)[0] == ["rule1"]
    assert accept.check_rules("[1,2]", ACC)[0] == ["rule1", "rule2"]
    # surrounding whitespace is allowed (rule 1 strips it)
    assert accept.check_rules("\n " + json.dumps(good(), ensure_ascii=False) + " \n", ACC)[0] == []
