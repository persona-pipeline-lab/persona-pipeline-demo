# -*- coding: utf-8 -*-
"""Step 2: send each built text to an OpenAI-compatible endpoint and save one record per job.

For every job this module
  1. re-computes the SHA-256 of the built text and asserts it equals the ledger value (before sending),
  2. sends the text as one user message (no system message),
  3. saves the text actually sent to sent/<job>.txt and the response + metadata to generated/<job>.json.

The API key is read from the environment variable named in the config (never stored, never logged).
`client` can be injected (tests use a fake client; the real run builds an openai client).
"""
import os
import sys
import time
from datetime import datetime, timezone

from . import common as C


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def make_client(section):
    """Build an OpenAI-compatible client from a config section (base_url, api_key_env)."""
    from openai import OpenAI  # imported lazily so that replay/tests do not need a network client
    key_env = section.get("api_key_env")
    key = os.environ.get(key_env, "") if key_env else ""
    if not key:
        key = section.get("api_key_placeholder", "not-needed")  # local servers usually accept any value
    kw = {"api_key": key}
    if section.get("base_url"):
        kw["base_url"] = section["base_url"]
    kw["timeout"] = section.get("timeout_seconds", 900)
    return OpenAI(**kw)


def chat_once(client, section, params, text):
    """One chat completion. Returns a dict with response_text and metadata."""
    kwargs = {
        "model": section["model"],
        "messages": [{"role": "user", "content": text}],
        "temperature": params["temperature"],
        "top_p": params["top_p"],
        section.get("max_tokens_param", "max_tokens"): params["max_tokens"],
    }
    if params.get("seed") is not None:
        kwargs["seed"] = params["seed"]
    extra = dict(section.get("extra_body") or {})
    if params.get("reasoning_effort"):
        extra["reasoning_effort"] = params["reasoning_effort"]
    if extra:
        kwargs["extra_body"] = extra
    if params.get("json_mode"):
        kwargs["response_format"] = {"type": "json_object"}
    r = client.chat.completions.create(**kwargs)
    ch = r.choices[0]
    msg = ch.message
    reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None) or ""
    usage = getattr(r, "usage", None)
    return {
        "response_text": msg.content or "",
        "reasoning_text": reasoning,
        "finish_reason": getattr(ch, "finish_reason", None),
        "actual_model": getattr(r, "model", None),
        "response_id": getattr(r, "id", None),
        "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
        "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
    }


def with_retry(fn, retries, backoff):
    last = None
    for i in range(retries + 1):
        try:
            return fn(), ""
        except Exception as e:  # noqa: BLE001 - network/API errors are recorded, not raised
            last = "%s: %s" % (type(e).__name__, str(e)[:300])
            if i < retries:
                time.sleep(backoff * (i + 1))
    return None, last


def run(cfg, out_dir, client=None, limit=0, resume=True, dry_run=False, sleep=None):
    """Send all (or the first `limit`) jobs. Returns a dict of counts."""
    ledger = C.read_jsonl(os.path.join(out_dir, "ledger.jsonl"))
    if limit:
        ledger = ledger[:limit]
    gsec = cfg["generation"]
    # pre-send assertion for every job
    texts = {}
    for r in ledger:
        with open(os.path.join(out_dir, r["built_path"]), "rb") as f:
            raw = f.read()
        if C.sha_bytes(raw) != r["sent_sha256"]:
            raise SystemExit("built text does not match the ledger SHA-256: %s. Nothing was sent." % r["job_id"])
        texts[r["job_id"]] = raw.decode("utf-8")
    print("[pre-send] %d jobs, all built texts match the ledger (%d unique SHA-256)"
          % (len(ledger), len({r["sent_sha256"] for r in ledger})))
    if dry_run:
        print("[dry-run] nothing sent")
        return {"jobs": len(ledger), "sent": 0, "skipped": 0, "errors": 0}
    client = client or make_client(gsec)
    retries = int(gsec.get("retries", 2))
    backoff = float(gsec.get("retry_backoff_seconds", 10))
    sent = skipped = errors = 0
    for r in ledger:
        gpath = os.path.join(out_dir, "generated", C.job_filename(r["job_id"], ".json"))
        if resume and os.path.exists(gpath):
            skipped += 1
            continue
        text = texts[r["job_id"]]
        t_req = now_iso()
        res, err = with_retry(lambda: chat_once(client, gsec, r["params"], text), retries, backoff)
        t_res = now_iso()
        spath = os.path.join(out_dir, "sent", C.job_filename(r["job_id"], ".txt"))
        C.write_bytes(spath, text.encode("utf-8"))
        ok = res is not None and res["response_text"].strip() != ""
        if res is None:
            res = {"response_text": "", "reasoning_text": "", "finish_reason": "api_error", "actual_model": None,
                   "response_id": None, "prompt_tokens": None, "completion_tokens": None}
        elif not ok:
            err = "empty response text"
        rec = {
            "job_id": r["job_id"], "seq": r["seq"], "person_id": r["person_id"], "condition": r["condition"],
            "scenario": r["scenario"], "rep": r["rep"], "model": r["model"],
            "sent_sha256": C.sha_bytes(text.encode("utf-8")), "sent_file": "sent/" + C.job_filename(r["job_id"], ".txt"),
            "params": dict(r["params"]), "status": "ok" if ok else "error", "error_message": err,
            "response_text": res["response_text"], "reasoning_text": res["reasoning_text"],
            "finish_reason": res["finish_reason"], "actual_model": res["actual_model"],
            "response_id": res["response_id"],
            "usage": {"prompt_tokens": res["prompt_tokens"], "completion_tokens": res["completion_tokens"]},
            "endpoint_kind": gsec.get("endpoint_kind", ""),
            "timestamp_requested": t_req, "timestamp_responded": t_res,
        }
        C.write_json(gpath, rec)
        sent += 1
        errors += 0 if ok else 1
        print("[%d/%d] seq=%s %s %s" % (sent + skipped, len(ledger), r["seq"], rec["status"], r["job_id"]), flush=True)
        if sleep:
            time.sleep(sleep)
    print("[done] sent=%d skipped(existing)=%d errors=%d" % (sent, skipped, errors))
    return {"jobs": len(ledger), "sent": sent, "skipped": skipped, "errors": errors}
