# -*- coding: utf-8 -*-
"""Step 6: three-way audit of ledger, sent files and output records, plus an independent rebuild.

For every ledger row:
  A. the sent file exists and its SHA-256 equals the ledger value (and its length equals the ledger length)
  B. the output record exists and its recorded sent SHA-256 equals the ledger value
  C. the text re-assembled now from templates + inputs (in memory) has the same SHA-256 as the ledger
     (independent angle: it does not use any saved text)
A row is "match" only if A, B and C all hold.
"""
import collections
import json
import os

from . import common as C
from .build_prompts import build_ledger


def run(cfg, ledger_path, sent_dir, generated_dir, report_path=None, rebuild=True):
    ledger = C.read_jsonl(ledger_path)
    fresh = {}
    if rebuild:
        rows, _, _ = build_ledger(cfg)
        fresh = {r["job_id"]: r["sent_sha256"] for r in rows}
    res = []
    for r in ledger:
        why = []
        sp = os.path.join(sent_dir, C.job_filename(r["job_id"], ".txt"))
        gp = os.path.join(generated_dir, C.job_filename(r["job_id"], ".json"))
        sent_sha = ""
        if not os.path.exists(sp) or os.path.getsize(sp) == 0:
            why.append("sent_missing")
        else:
            raw = open(sp, "rb").read()
            sent_sha = C.sha_bytes(raw)
            if sent_sha != r["sent_sha256"]:
                why.append("sent_sha_differs_from_ledger")
            if len(raw.decode("utf-8")) != r["sent_chars"]:
                why.append("sent_length_differs_from_ledger")
        if not os.path.exists(gp):
            why.append("record_missing")
        else:
            rec = C.read_json(gp)
            if rec.get("sent_sha256") != r["sent_sha256"]:
                why.append("record_sha_differs_from_ledger")
        if rebuild:
            if r["job_id"] not in fresh:
                why.append("job_not_in_rebuild")
            elif fresh[r["job_id"]] != r["sent_sha256"]:
                why.append("rebuild_differs_from_ledger")
        res.append((r["seq"], r["job_id"], r["condition"], "mismatch" if why else "match", ";".join(why), sent_sha))
    extra = len(fresh) - len({x[1] for x in res}) if rebuild else 0
    cnt = collections.Counter(x[3] for x in res)
    n_sent = sum(1 for x in res if "sent_missing" not in x[4])
    n_rec = sum(1 for x in res if "record_missing" not in x[4])
    uniq = len({x[5] for x in res if x[5]})
    per = collections.defaultdict(set)
    for x in res:
        if x[5]:
            per[x[2]].add(x[5])
    lines = [
        "audit: ledger rows = %d" % len(ledger),
        "audit: sent files present = %d, output records present = %d" % (n_sent, n_rec),
        "audit: match = %d, mismatch = %d" % (cnt["match"], cnt["mismatch"]),
        "audit: unique SHA-256 of sent texts = %d; by condition: %s" % (uniq, json.dumps({k: len(v) for k, v in per.items()}, ensure_ascii=False)),
    ]
    if rebuild:
        lines.append("audit: jobs in the fresh rebuild that are not in the ledger = %d" % extra)
    bad = [x for x in res if x[3] != "match"]
    for x in bad[:20]:
        lines.append("audit: MISMATCH seq=%s %s : %s" % (x[0], x[1], x[4]))
    ok = cnt["mismatch"] == 0 and extra == 0
    lines.append("audit: RESULT = %s" % ("OK" if ok else "NOT OK"))
    for ln in lines:
        print(ln)
    if report_path:
        C.ensure_dir(os.path.dirname(report_path))
        with open(report_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        C.write_csv(os.path.splitext(report_path)[0] + "_rows.csv",
                    ["seq", "job_id", "condition", "result", "reasons", "sent_sha256"], res)
    return ok, {"match": cnt["match"], "mismatch": cnt["mismatch"], "rows": len(ledger), "unique": uniq}
