# -*- coding: utf-8 -*-
"""Step 4: code the free-text answers (q2_text, q4_text, q6_text) with a separate prompt per variable.

Blindness: the coder receives ONLY the free-text sentence(s) inside the prompt template. Person,
condition, model, scenario and the sent text are never passed.

The coding endpoint can differ from the generation endpoint (config: coding.*). Any setting left
null in `coding` falls back to the `generation` setting; in that case the coder and the generator
are the same model, which is a simplification (see README).
Each coding call is made once. Unparseable answers are flagged, not repeated.
"""
import json
import os
import time

from . import common as C
from .generate import chat_once, make_client, now_iso, with_retry


def coding_section(cfg):
    """Effective endpoint settings for coding: coding.* with null entries filled from generation.*."""
    g, c = cfg["generation"], cfg["coding"]
    sec = {}
    for k in ("endpoint_kind", "base_url", "api_key_env", "model", "max_tokens_param", "extra_body", "timeout_seconds",
             "retries", "retry_backoff_seconds"):
        sec[k] = c.get(k) if c.get(k) is not None else g.get(k)
    params = {"temperature": c.get("temperature"), "top_p": c.get("top_p"), "max_tokens": c.get("max_tokens"),
              "reasoning_effort": c.get("reasoning_effort"), "seed": c.get("seed"), "json_mode": bool(c.get("json_mode"))}
    for k, v in list(params.items()):
        if v is None and k in g.get("params", {}):
            params[k] = g["params"][k]
    sec["same_as_generation"] = (sec["model"] == g.get("model") and sec["base_url"] == g.get("base_url"))
    return sec, params


def load_coding_prompts(cfg):
    """Read templates/coding_prompt.md: blocks separated by `---` lines, in the order of coding.blocks."""
    p = os.path.join(C.path_of(cfg, "templates_dir"), cfg["templates"]["coding_prompt"])
    blocks = C.split_blocks(C.read_text(p))
    names = [b["name"] for b in cfg["coding"]["blocks"]]
    if len(blocks) != len(names):
        raise ValueError("coding_prompt.md has %d blocks but config lists %d" % (len(blocks), len(names)))
    ph = cfg["placeholders"]["coding"]
    for n, b in zip(names, blocks):
        if ph not in b:
            raise ValueError("coding block '%s' has no %s placeholder" % (n, ph))
    return dict(zip(names, blocks))


def parse_coded(raw, output_key):
    """Return {'value': str, 'confidence': str, 'ok': 0/1}. Lists are joined with ';'."""
    d = None
    s = (raw or "").strip()
    try:
        d = json.loads(s)
    except Exception:  # noqa: BLE001
        a, b = s.find("{"), s.rfind("}")
        if a >= 0 and b > a:
            try:
                d = json.loads(s[a:b + 1])
            except Exception:  # noqa: BLE001
                d = None
    if not isinstance(d, dict) or output_key not in d:
        return {"value": "", "confidence": "", "ok": 0}
    v = d[output_key]
    if isinstance(v, list):
        v = ";".join(str(x) for x in v)
    return {"value": "" if v is None else str(v), "confidence": str(d.get("confidence", "")), "ok": 1}


def coding_path(out_dir, job_id, block):
    return os.path.join(out_dir, "coding", C.job_filename(job_id, "." + block + ".json"))


def run(cfg, out_dir, client=None, limit=0, resume=True):
    acc_rows = [r for r in C.read_csv(os.path.join(out_dir, "acceptance.csv")) if r["accepted"] == "PASS"]
    if limit:
        acc_rows = acc_rows[:limit]
    prompts = load_coding_prompts(cfg)
    sec, params = coding_section(cfg)
    if sec["same_as_generation"]:
        print("[code] NOTE: coding uses the same model and endpoint as generation (simplification).")
    client = client or make_client(sec)
    retries = int(sec.get("retries") or 2)
    backoff = float(sec.get("retry_backoff_seconds") or 10)
    ph = cfg["placeholders"]["coding"]
    n_done = n_skip = n_err = 0
    for r in acc_rows:
        for b in cfg["coding"]["blocks"]:
            path = coding_path(out_dir, r["job_id"], b["name"])
            if resume and os.path.exists(path):
                n_skip += 1
                continue
            inp = (r[b["source"]] or "").strip()
            prompt = prompts[b["name"]].replace(ph, inp)
            t0 = now_iso()
            res, err = with_retry(lambda: chat_once(client, sec, params, prompt), retries, backoff)
            raw = res["response_text"] if res else ""
            C.write_json(path, {
                "job_id": r["job_id"], "seq": int(r["seq"]), "block": b["name"], "source": b["source"],
                "input_sha256": C.sha_text(inp), "prompt_sha256": C.sha_text(prompt), "raw_text": raw,
                "reasoning_text": res["reasoning_text"] if res else "", "error_message": err,
                "model": sec["model"], "actual_model": res["actual_model"] if res else None,
                "endpoint_kind": sec.get("endpoint_kind") or "", "same_as_generation": sec["same_as_generation"],
                "params": {k: v for k, v in params.items() if k != "json_mode"},
                "timestamp_requested": t0, "timestamp_responded": now_iso()})
            n_done += 1
            n_err += 0 if res else 1
    print("[code] coded=%d skipped(existing)=%d api_errors=%d" % (n_done, n_skip, n_err))
    return {"coded": n_done, "skipped": n_skip, "errors": n_err}
