# -*- coding: utf-8 -*-
"""Command-line entry point.

  python demo.py check      validate templates (frozen hashes), inputs and config; nothing is sent
  python demo.py build      assemble the texts and write the ledger (outputs/ledger.jsonl, outputs/built/)
  python demo.py generate   send the built texts to the generation endpoint (needs a model server)
  python demo.py accept     mechanical acceptance (seven format rules)
  python demo.py code       code the free-text answers (needs a model server)
  python demo.py dataset    write dataset_A.csv and dataset_B.csv
  python demo.py audit      three-way audit (ledger / sent files / output records)
  python demo.py snapshot   copy outputs/ to outputs_example/ and write manifest.json
  python demo.py replay     run everything on the saved answers in outputs_example/ (no model needed)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from engine import accept, audit, build_dataset, build_prompts, code_outputs, generate, replay  # noqa: E402
from engine import common as C  # noqa: E402


def check(cfg):
    """Return the number of errors; warnings are printed but not counted."""
    errors = 0

    def err(msg):
        nonlocal errors
        errors += 1
        print("[check] ERROR: " + msg)
    try:
        build_prompts.verify_frozen(cfg)
        print("[check] template files match templates/%s" % cfg["templates"]["hashes"])
        build_prompts.check_params_match_frozen(cfg)
        print("[check] config params equal the frozen generation_params.yaml")
    except build_prompts.FrozenHashError as e:
        err(str(e))
    try:
        rows, texts, mixed = build_prompts.build_ledger(cfg)
        print("[check] ledger can be built: %d jobs, %d unique texts" % (len(rows), len({r['sent_sha256'] for r in rows})))
    except Exception as e:  # noqa: BLE001
        err("cannot build: %s" % e)
    try:
        code_outputs.load_coding_prompts(cfg)
        print("[check] coding prompt blocks: %d, placeholders present" % len(cfg["coding"]["blocks"]))
    except Exception as e:  # noqa: BLE001
        err("coding prompts: %s" % e)
    # the accept lists in the config must appear in the question / output-format text
    tdir = C.path_of(cfg, "templates_dir")
    try:
        qtext = C.read_text(os.path.join(tdir, cfg["templates"]["questions"])) + C.read_text(os.path.join(tdir, cfg["templates"]["output_format"]))
        acc = cfg["accept"]
        for item in list(acc["q3_options"]) + list(acc["q5_names"]):
            if item not in qtext:
                print("[check] WARNING: '%s' (accept lists) does not appear in the questions/output-format templates" % item)
    except Exception as e:  # noqa: BLE001
        err("accept-list consistency: %s" % e)
    print("[check] %s" % ("OK" if errors == 0 else "%d error(s)" % errors))
    return errors


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["check", "build", "generate", "accept", "code", "dataset", "audit", "snapshot", "replay"])
    ap.add_argument("--config", default=os.path.join(HERE, "config", "demo.yaml"))
    ap.add_argument("--project", default=None, help="project folder (overrides `project` in the config)")
    ap.add_argument("--out-dir", default=None, help="working output folder (default: the project's outputs_dir)")
    ap.add_argument("--example-dir", default=None, help="replay/snapshot folder (default: the project's example_dir)")
    ap.add_argument("--workdir", default=None, help="replay only: where to write the re-created files (default: a temp folder)")
    ap.add_argument("--limit", type=int, default=0, help="generate/code: only the first N jobs")
    ap.add_argument("--dry-run", action="store_true", help="generate: check hashes, send nothing")
    ap.add_argument("--no-resume", action="store_true", help="generate/code: redo existing files")
    a = ap.parse_args(argv)

    cfg = C.load_config(a.config, a.project)
    out = a.out_dir or C.path_of(cfg, "outputs_dir")
    example = a.example_dir or C.path_of(cfg, "example_dir")
    cmd = a.command
    if cmd == "check":
        return 1 if check(cfg) else 0
    if cmd == "build":
        build_prompts.build(cfg, out)
    elif cmd == "generate":
        build_prompts.check_params_match_frozen(cfg)
        generate.run(cfg, out, limit=a.limit, resume=not a.no_resume, dry_run=a.dry_run)
    elif cmd == "accept":
        accept.run(cfg, os.path.join(out, "ledger.jsonl"), os.path.join(out, "generated"), out)
    elif cmd == "code":
        code_outputs.run(cfg, out, limit=a.limit, resume=not a.no_resume)
    elif cmd == "dataset":
        build_dataset.run(cfg, out)
    elif cmd == "audit":
        ok, _ = audit.run(cfg, os.path.join(out, "ledger.jsonl"), os.path.join(out, "sent"), os.path.join(out, "generated"),
                          os.path.join(out, "audit_report.txt"))
        return 0 if ok else 1
    elif cmd == "snapshot":
        replay.snapshot(cfg, out, example)
    elif cmd == "replay":
        return 0 if replay.replay(cfg, example_dir=example, workdir=a.workdir) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
