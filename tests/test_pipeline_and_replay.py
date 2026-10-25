# -*- coding: utf-8 -*-
"""Whole pipeline with a fake client, and replay mode on the saved dummy answers."""
import os
import shutil

import pytest

from engine import accept, audit, build_dataset, build_prompts, code_outputs, generate, replay
from engine import common as C
from helpers import FIXTURE_CONFIG, FakeClient

FX_ROOT = os.path.dirname(os.path.dirname(FIXTURE_CONFIG))


def fixture_copy(tmp_path, with_example=True):
    dst = tmp_path / "fx"
    ignore = None if with_example else shutil.ignore_patterns("outputs_example")
    shutil.copytree(FX_ROOT, dst, ignore=ignore)
    return C.load_config(str(dst / "config" / "demo.yaml")), dst


def test_full_pipeline_with_fake_client(tmp_path):
    cfg, _ = fixture_copy(tmp_path, with_example=False)
    out = str(tmp_path / "run")
    build_prompts.build(cfg, out)
    client = FakeClient()
    res = generate.run(cfg, out, client=client)
    assert res["sent"] == 48 and res["errors"] == 0
    # the first call carried the frozen parameters and the reasoning_effort setting
    kw = client.calls[0]
    assert kw["temperature"] == 1.0 and kw["top_p"] == 1.0 and kw["max_tokens"] == 8192
    assert kw["seed"] == 7 * 100 + 1 and kw["extra_body"] == {"reasoning_effort": "medium"}
    assert len(kw["messages"]) == 1 and kw["messages"][0]["role"] == "user"       # no system message
    rows = accept.run(cfg, os.path.join(out, "ledger.jsonl"), os.path.join(out, "generated"), out)
    n_pass = sum(1 for r in rows if r["accepted"] == "PASS")
    assert 0 < n_pass < 48                                       # some pass, some deliberately fail
    assert os.path.getsize(os.path.join(out, "rejects.csv")) > 0
    code_outputs.run(cfg, out, client=client)
    # coding prompts contain only the sentence, nothing about the person / condition
    coding_calls = [c for c in client.calls[48:]]
    assert len(coding_calls) == n_pass * 2
    for c in coding_calls:
        body = c["messages"][0]["content"]
        assert "T1" not in body and "C3" not in body and "scen_a" not in body and "mock-model" not in body
    a, b = build_dataset.run(cfg, out)
    assert len(a) == 48 and len(b) == 3
    assert sum(r["accepted"] for r in a) == n_pass
    ok, stats = audit.run(cfg, os.path.join(out, "ledger.jsonl"), os.path.join(out, "sent"), os.path.join(out, "generated"))
    assert ok and stats["match"] == 48


def test_generate_stops_before_sending_if_a_built_text_was_changed(tmp_path):
    cfg, _ = fixture_copy(tmp_path, with_example=False)
    out = str(tmp_path / "run")
    build_prompts.build(cfg, out)
    victim = os.path.join(out, "built", C.job_filename("T1|C3|scen_a|1", ".txt"))
    with open(victim, "ab") as f:
        f.write("x".encode("utf-8"))
    client = FakeClient()
    with pytest.raises(SystemExit):
        generate.run(cfg, out, client=client)
    assert client.calls == []                                   # nothing was sent


def test_api_error_is_recorded_not_raised(tmp_path):
    cfg, _ = fixture_copy(tmp_path, with_example=False)
    out = str(tmp_path / "run")
    build_prompts.build(cfg, out)

    class Broken:
        class chat:                                             # noqa: N801
            class completions:                                  # noqa: N801
                @staticmethod
                def create(**kw):
                    raise RuntimeError("boom")
    res = generate.run(cfg, out, client=Broken(), limit=2)
    assert res["errors"] == 2
    rec = C.read_json(os.path.join(out, "generated", C.job_filename("T1|C3|scen_a|1", ".json")))
    assert rec["status"] == "error" and "boom" in rec["error_message"]


def test_audit_detects_a_changed_sent_file(tmp_path):
    cfg, dst = fixture_copy(tmp_path)
    ex = str(dst / "project" / "outputs_example")
    victim = os.path.join(ex, "sent", C.job_filename("T2|C3|scen_b|2", ".txt"))
    with open(victim, "ab") as f:
        f.write(b" ")
    ok, stats = audit.run(cfg, os.path.join(ex, "ledger.jsonl"), os.path.join(ex, "sent"), os.path.join(ex, "generated"))
    assert not ok and stats["mismatch"] == 1


def test_replay_runs_on_saved_answers(tmp_path, capsys):
    cfg, _ = fixture_copy(tmp_path)
    assert replay.replay(cfg, workdir=str(tmp_path / "wd")) is True
    out = capsys.readouterr().out
    assert "manifest check: OK" in out and "RESULT = OK" in out
    assert "48 / 48" in out and "dataset_A.csv identical to the saved example: yes" in out
    assert out.index("rejects first") < out.index("table A")      # rejects are shown before the dataset


@pytest.mark.parametrize("target", ["project/inputs/texts/T2.md", "project/templates/scenario_a.md",
                                    "project/inputs/persons.csv"])
def test_replay_stops_if_an_input_changed(tmp_path, capsys, target):
    cfg, dst = fixture_copy(tmp_path)
    p = dst / target
    p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert replay.replay(cfg, workdir=str(tmp_path / "wd")) is False
    out = capsys.readouterr().out
    assert "STOP: manifest does not match" in out
    assert not os.path.exists(tmp_path / "wd" / "ledger.jsonl")     # stopped before building


def test_replay_stops_if_config_changed(tmp_path, capsys):
    cfg, _ = fixture_copy(tmp_path)
    cfg["reps"] = 3
    assert replay.replay(cfg, workdir=str(tmp_path / "wd")) is False
    assert "generation-relevant config differs" in capsys.readouterr().out


def test_demo_cli_check_and_replay(tmp_path, capsys):
    import demo
    assert demo.main(["check", "--config", FIXTURE_CONFIG]) == 0
    dst = tmp_path / "fx"
    shutil.copytree(FX_ROOT, dst)
    assert demo.main(["replay", "--config", str(dst / "config" / "demo.yaml"), "--workdir", str(tmp_path / "wd")]) == 0
