"""Fake chat model for testing structured-output handling without network."""
from __future__ import annotations

from langchain_core.runnables import RunnableLambda


class RateLimitError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class FakeChatModel:
    """``responses`` is a list consumed in order; each item is a value to return,
    an exception instance to raise, or a callable(schema, input) -> value."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def with_structured_output(self, schema, **_kw):
        def run(_input):
            self.calls += 1
            if not self.responses:
                raise AssertionError("FakeChatModel ran out of responses")
            r = self.responses.pop(0)
            if isinstance(r, Exception):
                raise r
            if callable(r):
                return r(schema, _input)
            return r
        return RunnableLambda(run)
