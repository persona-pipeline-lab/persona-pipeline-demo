# -*- coding: utf-8 -*-
"""Step 5: build the two tables.

Table A (dataset_A.csv): one row per generation job.
    person_id, condition, model, scenario, rep, accepted (1/0), the structured answers q1..q6 (only for
    accepted jobs), and the coded values (value, confidence, parse_ok per coding block).
Table B (dataset_B.csv): one row per person, the columns of persons.csv. Join key: person_id.
    C0 jobs have an empty person_id (no persona), so they have no row in table B.

No test statistics are computed here.
"""
import os

from . import common as C
from .code_outputs import coding_path, parse_coded

A_BASE = ["job_id", "person_id", "condition", "model", "scenario", "rep", "accepted", "violations",
          "q1_1", "q1_2", "q1_3", "q2_category", "q2_text", "q3", "q4_text",
          "q5_1", "q5_2", "q5_3", "q5_4", "q5_5", "q6_text"]


def a_columns(cfg):
    cols = list(A_BASE)
    for b in cfg["coding"]["blocks"]:
        n = b["name"]
        cols += ["code_" + n, "code_" + n + "_confidence", "code_" + n + "_parse_ok"]
    return cols


def run(cfg, out_dir, coding_dir=None, dataset_dir=None):
    """coding_dir: directory that holds the coding/ folder (default out_dir). dataset_dir: where to write (default out_dir)."""
    coding_dir = coding_dir or out_dir
    dataset_dir = dataset_dir or out_dir
    acc = C.read_csv(os.path.join(out_dir, "acceptance.csv"))
    cols = a_columns(cfg)
    rows_a, n_coded, n_missing = [], 0, 0
    for r in acc:
        row = {c: r.get(c, "") for c in A_BASE}
        row["accepted"] = 1 if r["accepted"] == "PASS" else 0
        for b in cfg["coding"]["blocks"]:
            n = b["name"]
            row["code_" + n] = row["code_" + n + "_confidence"] = row["code_" + n + "_parse_ok"] = ""
            if r["accepted"] != "PASS":
                continue
            p = coding_path(coding_dir, r["job_id"], n)
            if not os.path.exists(p):
                n_missing += 1
                continue
            res = parse_coded(C.read_json(p).get("raw_text", ""), b["output_key"])
            row["code_" + n], row["code_" + n + "_confidence"], row["code_" + n + "_parse_ok"] = res["value"], res["confidence"], res["ok"]
            n_coded += 1
        rows_a.append(row)
    persons = C.read_persons(cfg)
    hdr_b = list(persons[0].keys())
    C.write_csv(os.path.join(dataset_dir, "dataset_A.csv"), cols, rows_a)
    C.write_csv(os.path.join(dataset_dir, "dataset_B.csv"), hdr_b, persons)
    notice = cfg.get("dataset_notice", "")
    if notice:
        with open(os.path.join(dataset_dir, "dataset_NOTICE.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(notice.strip() + "\n")
        print("[dataset] NOTICE:", notice.strip())
    print("[dataset] table A: %d rows x %d columns (accepted=%d); coded cells=%d, accepted cells without a coding file=%d"
          % (len(rows_a), len(cols), sum(r["accepted"] for r in rows_a), n_coded, n_missing))
    print("[dataset] table B: %d rows x %d columns; join key = person_id" % (len(persons), len(hdr_b)))
    return rows_a, persons
