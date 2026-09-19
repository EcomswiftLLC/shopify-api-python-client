"""A scriptable fake transport shared by the test modules.

No mocking library and no real network calls: a ``FakeTransport`` instance
is a queue of canned ``HTTPResponse`` objects, one per call, so tests can
assert exactly which request the client sent and control what it gets back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from shopify_client.http import HTTPResponse


@dataclass
class RecordedCall:
    url: str
    method: str
    headers: Dict[str, str]
    body: Optional[bytes]


class FakeTransport:
    def __init__(self, responses: List[HTTPResponse]) -> None:
        self._responses = list(responses)
        self.calls: List[RecordedCall] = []

    def __call__(
        self,
        url: str,
        method: str,
        headers: Mapping[str, str],
        data: Optional[bytes],
        timeout: float,
    ) -> HTTPResponse:
        self.calls.append(RecordedCall(url=url, method=method, headers=dict(headers), body=data))
        if not self._responses:
            raise AssertionError("FakeTransport ran out of scripted responses")
        return self._responses.pop(0)


def json_response(status: int, payload: Any, headers: Optional[Dict[str, str]] = None) -> HTTPResponse:
    return HTTPResponse(status=status, headers=headers or {}, body=json.dumps(payload).encode("utf-8"))


class SleepRecorder:
    """Drop-in replacement for ``time.sleep`` that records durations instead of waiting."""

    def __init__(self) -> None:
        self.calls: List[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
