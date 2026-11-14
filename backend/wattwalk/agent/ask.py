"""Ask-the-user callback for Person 2's router (plan 12.6, D21). Owner: Person 3.

make_ask_fn(ctx) returns an AskFn: it stores the question (status open), emits a `question` event,
blocks the calling worker thread up to config.TIMEOUTS_S["ask_user"] seconds, and returns the answer
or None (question then marked expired). answer() is called by POST /audits/{sid}/answer.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

from .. import config, store
from ..contracts import Question
from ..errors import AuditCancelled

_lock = threading.Lock()
_waiting: dict[tuple[str, str], tuple[threading.Event, list]] = {}


class QuestionNotOpen(Exception):
    pass


class QuestionNotFound(Exception):
    pass


def make_ask_fn(ctx, agent: str = "walker") -> Callable[[Question], Optional[str]]:
    sid, bus = ctx.sid, ctx.bus

    def ask(q: Question) -> Optional[str]:
        ctx.check_cancel()
        timeout = float(config.TIMEOUTS_S["ask_user"])
        q = q.model_copy(update={"status": "open", "answer": None})
        flag, slot = threading.Event(), []
        with _lock:
            _waiting[(sid, q.question_id)] = (flag, slot)
        store.upsert_question(sid, q)
        bus.emit(agent, "question", q.text,
                 {"question_id": q.question_id, "choices": q.choices, "timeout_s": int(round(timeout)),
                  "asset_id": q.asset_id, "attr": q.attr})
        try:
            waited = 0.0
            while waited < timeout and not flag.is_set():
                step = min(0.1, timeout - waited)
                flag.wait(step)
                waited += step
                if ctx.cancel.is_set() and not flag.is_set():
                    raise AuditCancelled(f"audit {sid} cancelled while waiting for {q.question_id}")
        finally:
            with _lock:
                answered = flag.is_set()
                _waiting.pop((sid, q.question_id), None)
                if not answered:
                    store.upsert_question(sid, q.model_copy(update={"status": "expired"}))
        if answered:
            return slot[0]
        bus.emit(agent, "tool_result",
                 f"Question {q.question_id} expired without an answer; {q.attr} left unknown",
                 {"question_id": q.question_id})
        return None

    return ask


def answer(sid: str, question_id: str, text: str) -> Question:
    with _lock:
        q = next((x for x in store.questions(sid) if x.question_id == question_id), None)
        if q is None:
            raise QuestionNotFound(question_id)
        waiter = _waiting.get((sid, question_id))
        if q.status != "open" or waiter is None:
            raise QuestionNotOpen(question_id)
        if q.choices and text not in q.choices:
            raise ValueError(f"answer must be one of {q.choices}")
        q = q.model_copy(update={"status": "answered", "answer": text})
        store.upsert_question(sid, q)
        flag, slot = waiter
        slot.append(text)
        flag.set()
    return q
