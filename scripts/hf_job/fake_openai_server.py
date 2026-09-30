"""A scripted stand-in for vLLM's OpenAI-compatible API, for dry-running scripts/hf_job/job.sh.

No model: it answers every role of the agent with fixed, schema-valid replies (one tool
call first, then a final JSON). Used only to test the job pipeline end to end on a laptop
without inference. Run through the `vllm` shim in scripts/hf_job/fake_vllm.

    python scripts/hf_job/fake_openai_server.py --port 8081 --served-model-name local-x
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CLS = {
    "hts10": "4202.21.90.00",
    "facts": {"material": "leather", "function": "carry", "form": "bag", "end_use": "personal"},
    "gri_path": ["GRI 1: heading 4202", "GRI 6: 4202.21"],
    "deciding_gri": "GRI 1",
    "cited_rulings": [],
    "rejected_alternatives": [{"code": "4202.22", "reason": "outer surface is leather"}],
    "missing_facts": [],
    "confidence": 0.7,
    "abstain": False,
    "rationale": "Scripted dry-run answer.",
}
PLAN = {"facts": CLS["facts"], "missing_facts": [], "candidate_headings": ["4202", "3926"], "reasoning": "x"}
MEMO = {
    "heading": "4202",
    "best_code": "4202.21.90.00",
    "argument": "scripted",
    "supporting_rulings": [],
    "exclusions_against": [],
    "strength": 0.6,
}


def reply(body: dict) -> dict:
    msgs = body.get("messages", [])
    sys_text = " ".join(m.get("content") or "" for m in msgs if m["role"] == "system")
    n_tool = sum(1 for m in msgs if m["role"] == "tool")
    tools = body.get("tools") or []
    if tools and n_tool == 0:
        name = tools[0]["function"]["name"]
        args = {"text": "leather handbag"} if name == "hts_search" else {"code": "4202.21"}
        if name == "cross_search":
            args = {"query": "leather handbag"}
        if name == "get_notes":
            args = {"scope": "chapter", "id": "42"}
        if name == "ruling_status":
            args = {"id": "N326421"}
        if name == "ask_expert":
            args = {"question": "Which heading?"}
        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{time.time_ns()}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
            ],
        }
        finish = "tool_calls"
    else:
        if "grade the legal reasoning" in sys_text:
            out = {"verdict": "pass", "reason": "scripted"}
        elif "orchestrator" in sys_text:
            out = PLAN
        elif "heading advocate" in sys_text:
            out = MEMO
        elif "senior US customs classification expert" in sys_text:
            out = "Heading 4202 applies under GRI 1."
        else:
            out = CLS
        msg = {"role": "assistant", "content": out if isinstance(out, str) else json.dumps(out)}
        finish = "stop"
    return {
        "id": "fake",
        "object": "chat.completion",
        "model": body.get("model"),
        "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "total_tokens": 1050,
            "prompt_tokens_details": {"cached_tokens": 800},
        },
    }


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code: int, obj: dict):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send(200, {"status": "ok"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        self._send(200, reply(body))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--served-model-name", default="fake")
    a, _ = ap.parse_known_args()
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
