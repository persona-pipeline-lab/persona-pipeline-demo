# -*- coding: utf-8 -*-
"""Step 3: mechanical acceptance by seven format rules. Failed jobs are NOT regenerated;
they are listed in rejects.csv.

Rules (applied to the response text):
  rule1  parses as JSON (after stripping surrounding whitespace) and is an object
  rule2  exactly the seven keys q1, q2_category, q2_text, q3, q4_text, q5_ranking, q6_text
  rule3  q1: a list of exactly 3 distinct symbols, each from accept.q1_symbols
  rule4  q2_category: an integer (not a boolean) from accept.q2_categories
  rule5  q3: one of accept.q3_options
  rule6  q5_ranking: a permutation of accept.q5_names
  rule7  q2_text, q4_text, q6_text: non-empty strings
Additional record checks (not numbered rules): id_mismatch, sha_mismatch, params_mismatch, status_not_ok.
The value sets (symbols, categories, options, names) come from the config; the rule structure is fixed.
"""
import collections
import json
import os

from . import common as C

KEYS = ["q1", "q2_category", "q2_text", "q3", "q4_text", "q5_ranking", "q6_text"]
COLS = ["seq", "job_id", "person_id", "condition", "scenario", "rep", "model", "api_status", "accepted",
        "violations", "sha_check", "q1_1", "q1_2", "q1_3", "q2_category", "q2_text", "q3", "q4_text",
        "q5_1", "q5_2", "q5_3", "q5_4", "q5_5", "q6_text", "finish_reason", "completion_tokens"]


def check_rules(text, acc):
    """Return (list of violated rule names, parsed dict or None)."""
    v = []
    try:
        d = json.loads(text.strip())
    except Exception:  # noqa: BLE001
        return ["rule1"], None
    if not isinstance(d, dict):
        return ["rule1", "rule2"], None
    if set(d.keys()) != set(KEYS):
        v.append("rule2")
    q1 = d.get("q1")
    sym = set(acc["q1_symbols"])
    if not (isinstance(q1, list) and len(q1) == 3 and all(isinstance(x, str) and x in sym for x in q1)
            and len(set(q1)) == 3):
        v.append("rule3")
    q2 = d.get("q2_category")
    if not (isinstance(q2, int) and not isinstance(q2, bool) and q2 in set(acc["q2_categories"])):
        v.append("rule4")
    q3 = d.get("q3")
    if not (isinstance(q3, str) and q3 in set(acc["q3_options"])):
        v.append("rule5")
    q5 = d.get("q5_ranking")
    if not (isinstance(q5, list) and len(q5) == len(acc["q5_names"]) and all(isinstance(x, str) for x in q5)
            and sorted(q5) == sorted(acc["q5_names"])):
        v.append("rule6")
    for k in ("q2_text", "q4_text", "q6_text"):
        x = d.get(k)
        if not (isinstance(x, str) and x.strip()):
            v.append("rule7")
            break
    return v, d


def accept_one(ledger_row, rec, acc):
    """Return (row dict for acceptance.csv). rec may be None (missing output)."""
    r = ledger_row
    row = {c: "" for c in COLS}
    row.update(seq=r["seq"], job_id=r["job_id"], person_id=r["person_id"], condition=r["condition"],
               scenario=r["scenario"], rep=r["rep"], model=r["model"])
    if rec is None:
        row.update(accepted="MISSING", violations="missing")
        return row
    viol = []
    row["api_status"] = rec.get("status", "")
    row["finish_reason"] = rec.get("finish_reason", "")
    row["completion_tokens"] = (rec.get("usage") or {}).get("completion_tokens", "")
    if not all(rec.get(k) == r[k] for k in ("seq", "job_id", "person_id", "condition", "scenario", "rep", "model")):
        viol.append("id_mismatch")
    sha_ok = rec.get("sent_sha256") == r["sent_sha256"]
    row["sha_check"] = "OK" if sha_ok else "NG"
    if not sha_ok:
        viol.append("sha_mismatch")
    if rec.get("params") != r["params"]:
        viol.append("params_mismatch")
    if rec.get("status") != "ok":
        viol.append("status_not_ok")
    rv, d = check_rules(rec.get("response_text") or "", acc)
    viol += rv
    if d is not None and not rv:
        q1, q5 = d["q1"], d["q5_ranking"]
        for i in range(3):
            row["q1_%d" % (i + 1)] = q1[i]
        for i in range(len(q5)):
            row["q5_%d" % (i + 1)] = q5[i]
        for k in ("q2_category", "q2_text", "q3", "q4_text", "q6_text"):
            row[k] = d[k]
    row["accepted"] = "FAIL" if viol else "PASS"
    row["violations"] = ";".join(viol)
    return row


def run(cfg, ledger_path, generated_dir, out_dir):
    """Accept every ledger job against its saved record. Writes acceptance.csv, rejects.csv,
    acceptance_summary.csv in out_dir and prints the rejects first."""
    acc = cfg["accept"]
    ledger = C.read_jsonl(ledger_path)
    rows = []
    for r in ledger:
        p = os.path.join(generated_dir, C.job_filename(r["job_id"], ".json"))
        rec = C.read_json(p) if os.path.exists(p) else None
        rows.append(accept_one(r, rec, acc))
    rejects = [x for x in rows if x["accepted"] != "PASS"]
    C.write_csv(os.path.join(out_dir, "acceptance.csv"), COLS, rows)
    C.write_csv(os.path.join(out_dir, "rejects.csv"), COLS, rejects)
    cross = collections.defaultdict(collections.Counter)
    for x in rows:
        cross[(x["model"], x["condition"])][x["accepted"]] += 1
    summ = [{"model": m, "condition": c, "PASS": n["PASS"], "FAIL": n["FAIL"], "MISSING": n["MISSING"],
             "total": sum(n.values())} for (m, c), n in sorted(cross.items())]
    C.write_csv(os.path.join(out_dir, "acceptance_summary.csv"), ["model", "condition", "PASS", "FAIL", "MISSING", "total"], summ)
    tot = collections.Counter(x["accepted"] for x in rows)
    print("[accept] rejects first: %d not accepted (FAIL=%d, MISSING=%d)" % (len(rejects), tot["FAIL"], tot["MISSING"]))
    vc = collections.Counter(v for x in rejects for v in x["violations"].split(";") if v)
    print("[accept] violations by rule:", dict(vc) if vc else "none")
    print("[accept] total=%d PASS=%d FAIL=%d MISSING=%d" % (len(rows), tot["PASS"], tot["FAIL"], tot["MISSING"]))
    for s in summ:
        print("[accept]   %s | %s : PASS=%d FAIL=%d MISSING=%d" % (s["model"], s["condition"], s["PASS"], s["FAIL"], s["MISSING"]))
    return rows
