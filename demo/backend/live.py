"""Live hearings: run the real agents with an event callback and a per-session spend cap.

Live mode is off unless DEMO_MODE=live and ANTHROPIC_API_KEY is set. Every model call
goes through `guarded_complete`, which refuses a call when the session's real spend
plus a conservative estimate of that call would pass the session cap. Spend is the
larger of what this process counted (fresh, uncached calls only) and what the spend
ledger holds for the session's run id.
"""

from __future__ import annotations

import base64
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from tariffagent.agents.events import ErrorEvent, EventBus
from tariffagent.llm.anthropic_provider import estimate_usd
from tariffagent.llm.base import LLMRequest, LLMResponse


class SessionCapReached(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


@dataclass
class Session:
    sid: str
    spent_usd: float = 0.0
    runs: int = 0
    active: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def run_id(self) -> str:
        return f"demo-{self.sid}"


class Sessions:
    def __init__(self):
        self._s: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get(self, sid: str | None) -> Session:
        sid = sid if sid and re.fullmatch(r"[a-f0-9]{16,32}", sid) else uuid.uuid4().hex[:20]
        with self._lock:
            if sid not in self._s:
                self._s[sid] = Session(sid)
            return self._s[sid]


def ledger_spent(run_id: str) -> float:
    try:
        from tariffagent.ledger import spent

        return spent(run_id=run_id)
    except Exception:  # noqa: BLE001
        return 0.0


def session_spent(sess: Session) -> float:
    return max(sess.spent_usd, ledger_spent(sess.run_id))


def make_guarded_complete(
    sess: Session,
    cap_usd: float,
    cancel: threading.Event,
    complete: Callable[[LLMRequest], LLMResponse] | None = None,
) -> Callable[[LLMRequest], LLMResponse]:
    """Wraps model calls with the session cap. `complete` overrides the provider (tests)."""

    def guarded(req: LLMRequest) -> LLMResponse:
        if cancel.is_set():
            raise Cancelled("The viewer left the hearing.")
        req.run_id = sess.run_id
        est = estimate_usd(req)
        used = session_spent(sess)
        if used + est > cap_usd:
            raise SessionCapReached(
                f"Session spend cap reached: ${used:.4f} spent, next call could cost up to ${est:.4f}, "
                f"cap ${cap_usd:.2f}."
            )
        if complete is not None:
            resp = complete(req)
        else:
            from tariffagent.agents.runner import provider_for

            resp = provider_for(req.model).complete(req)
        if not resp.from_cache:
            with sess.lock:
                sess.spent_usd += resp.usd
        return resp

    return guarded


def run_hearing(
    *,
    description: str,
    arm: str,
    sess: Session,
    tools,
    guarded: Callable[[LLMRequest], LLMResponse],
    emit: Callable[[dict], None],
) -> dict:
    """Runs one classification. Events go to `emit` as dicts as they happen."""
    from tariffagent.agents.multi import MultiConfig, multi_episode
    from tariffagent.agents.runner import drive
    from tariffagent.agents.single import AgentConfig, single_episode
    from tariffagent.agents.tooling import ToolExecutor

    sess.runs += 1
    item = {"item_id": f"live-{sess.runs}-{int(time.time())}", "description": description}
    bus = EventBus(f"{sess.run_id}:{item['item_id']}", lambda ev: emit(ev.model_dump()))
    try:
        if arm == "multi":
            cfg = MultiConfig.default(run_id=sess.run_id)
            gen = multi_episode(item, cfg, tools, bus)
        else:
            cfg = AgentConfig.for_arm("A", run_id=sess.run_id)
            gen = single_episode(item, cfg, ToolExecutor(tools, bus), bus)
        return drive(gen, complete=guarded)
    except Exception as e:  # noqa: BLE001
        bus.emit(ErrorEvent(agent="court", message=f"{type(e).__name__}: {str(e)[:400]}"))
        return {"error": str(e)}


PHOTO_PROMPT = (
    "Describe the product in this photo for a US customs classification. Say what it is, what it is "
    "made of (say when the material is uncertain), what it does, how it is built, and who uses it. "
    "Three to five plain sentences. Do not suggest a tariff code."
)


def photo_request(data_url: str, model: str) -> LLMRequest:
    m = re.fullmatch(r"data:(image/(?:jpeg|png|webp|gif));base64,([A-Za-z0-9+/=\s]+)", data_url.strip())
    if not m:
        raise ValueError("The photo must be a JPEG, PNG, WebP or GIF data URL.")
    raw = base64.b64decode(m.group(2), validate=False)
    if len(raw) > 4_500_000:
        raise ValueError("The photo is too large. Keep it under about 4 MB.")
    return LLMRequest(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": m.group(1), "data": m.group(2)},
                    },
                    {"type": "text", "text": PHOTO_PROMPT},
                ],
            }
        ],
        max_tokens=400,
        temperature=0.0,
        purpose="demo:describe-photo",
        cache=False,
    )
