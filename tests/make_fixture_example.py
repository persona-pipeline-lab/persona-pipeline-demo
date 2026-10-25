# -*- coding: utf-8 -*-
"""Re-create tests/fixtures/project/outputs_example/ (the saved dummy answers used by the replay test).

The answers come from tests/helpers.FakeClient (hand-defined dummy answers, a few of them invalid on
purpose); the metadata (hashes, parameters) is produced by the real engine code. No model is called.

  python tests/make_fixture_example.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from engine import accept, audit, build_dataset, build_prompts, code_outputs, generate, replay  # noqa: E402
from engine import common as C  # noqa: E402
from helpers import FIXTURE_CONFIG, FakeClient  # noqa: E402


def main():
    cfg = C.load_config(FIXTURE_CONFIG)
    out = tempfile.mkdtemp(prefix="fixture_run_")
    try:
        build_prompts.build(cfg, out)
        client = FakeClient()
        generate.run(cfg, out, client=client)
        accept.run(cfg, os.path.join(out, "ledger.jsonl"), os.path.join(out, "generated"), out)
        code_outputs.run(cfg, out, client=client)
        build_dataset.run(cfg, out)
        audit.run(cfg, os.path.join(out, "ledger.jsonl"), os.path.join(out, "sent"), os.path.join(out, "generated"),
                  os.path.join(out, "audit_report.txt"))
        replay.snapshot(cfg, out, C.path_of(cfg, "example_dir"))
    finally:
        shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    main()
