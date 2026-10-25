# -*- coding: utf-8 -*-
"""The real templates under projects/_template and the scan tool."""
import json
import os
import sys

from engine import build_prompts
from engine import common as C
from helpers import REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import check_forbidden  # noqa: E402

TPL = os.path.join(REPO, "projects", "_template", "templates")


def real_cfg():
    cfg = C.load_config(os.path.join(REPO, "config", "demo.yaml"))
    cfg["paths"]["templates_dir"] = "../_template/templates"
    return cfg


def test_real_templates_match_their_hash_record():
    cfg = real_cfg()
    sha = build_prompts.verify_frozen(cfg)
    assert len(sha) == 9
    build_prompts.check_params_match_frozen(cfg)


def test_real_templates_have_the_placeholders_and_blocks():
    cfg = real_cfg()
    tpl = build_prompts.load_templates(cfg)
    assert "{AUTOBIOGRAPHY}" in tpl["persona"]
    from engine import code_outputs
    blocks = code_outputs.load_coding_prompts(cfg)
    assert list(blocks) == ["pr_frame", "risk_orient", "time_horizon_q4", "exp_type_q6"]


def test_real_template_folder_is_clean_for_the_scan():
    assert check_forbidden.scan(os.path.join(REPO, "projects", "_template")) == []


def test_scan_finds_planted_items(tmp_path):
    # the forbidden strings are assembled at run time so that this test file itself is clean
    bad_word = "Drop" + "box"
    bad_path = "C:" + "\\Users\\someone"
    secret = "sk" + "-" + "a1b2c3d4e5f6g7h8i9j0"
    (tmp_path / "a.md").write_text("ok line\n%s here\npath %s\nkey %s\n" % (bad_word, bad_path, secret), encoding="utf-8")
    (tmp_path / "names.txt").write_text("Taro Testname\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("Taro Testname appears\n", encoding="utf-8")
    nb = {"cells": [{"cell_type": "code", "source": "", "outputs": [{"x": 1}], "execution_count": 3, "metadata": {}}],
          "metadata": {"colab": {"provenance": []}}, "nbformat": 4, "nbformat_minor": 5}
    (tmp_path / "c.ipynb").write_text(json.dumps(nb), encoding="utf-8")
    f = check_forbidden.scan(str(tmp_path), names=["Taro Testname"])
    cats = sorted({x[2] for x in f})
    assert "word:" + bad_word in cats and "abs_path" in cats and "secret" in cats
    assert "name_list" in cats and "ipynb" in cats
    assert any(x[0] == "a.md" and x[1] == 2 for x in f)


def test_scan_corpus_overlap(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    shared = "これは検査用の十二文字以上の同一文です。"
    (corpus / "x.md").write_text("前置き" + shared + "後置き", encoding="utf-8")
    proj = tmp_path / "repo" / "p" / "inputs" / "texts"
    proj.mkdir(parents=True)
    (proj / "D1.md").write_text("## 見出し\n" + shared, encoding="utf-8")
    (proj / "D2.md").write_text("## 見出し\n全く別の内容だけが書かれている短い文章です。", encoding="utf-8")
    sh = check_forbidden.corpus_shingles(str(corpus))
    f = check_forbidden.scan(str(tmp_path / "repo"), corpus=sh)
    assert [x[0] for x in f if x[2] == "corpus_12char"] == [os.path.join("p", "inputs", "texts", "D1.md")]
