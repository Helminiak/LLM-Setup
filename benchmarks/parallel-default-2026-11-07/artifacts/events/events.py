#!/usr/bin/env python3
"""Summarize tool_use / tool_result events from a Hermes stream-json JSONL feed.

Standard library only. ``summarize(lines)`` consumes an iterable of JSONL string
records (one JSON value per item) and returns::

    {"tools": {name: {"calls": int, "results": int}}, "invalid": int}

Record handling:

* A record that fails to parse as JSON (including blank and whitespace-only
  records), or parses to anything other than a JSON object, counts toward
  ``invalid``.
* A valid object whose ``type`` is neither ``tool_use`` nor ``tool_result`` is
  an unrelated event and is ignored entirely (it is *not* counted as invalid).
* ``tool_use`` increments ``calls`` for its name; ``tool_result`` increments
  ``results``.

Tool names are emitted in sorted (deterministic) order. Names must be
JSON-object keys, so non-``str`` names are coerced with ``str()`` after sorting
the raw key list, which keeps the ordering itself deterministic.
"""

import json

__all__ = ["summarize"]

_EVENT_FIELDS = {"tool_use": "calls", "tool_result": "results"}


def summarize(lines):
    """Aggregate tool call/result counts from an iterable of JSONL strings.

    Args:
        lines: iterable of strings, each holding one JSON value. Blank and
            whitespace-only items are invalid JSON and count toward
            ``invalid``, as does anything that parses to a non-object.

    Returns:
        ``{"tools": {name: {"calls": int, "results": int}}, "invalid": int}``
        with tool names in deterministic sorted order.
    """
    calls = {}
    results = {}
    invalid = 0

    for raw in lines:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        text = raw if isinstance(raw, str) else str(raw)
        try:
            event = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            invalid += 1
            continue
        if not isinstance(event, dict):
            invalid += 1
            continue

        etype = event.get("type")
        field = _EVENT_FIELDS.get(etype) if isinstance(etype, str) else None
        if field is None:
            continue  # unrelated valid event

        name = str(event.get("name", ""))
        bucket = calls if field == "calls" else results
        bucket[name] = bucket.get(name, 0) + 1

    tools = {}
    for name in sorted(set(calls) | set(results)):
        tools[name] = {"calls": calls.get(name, 0), "results": results.get(name, 0)}

    return {"tools": tools, "invalid": invalid}


def main(argv=None):
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="events",
        description="Summarize tool_use/tool_result events from stream-json JSONL.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="JSONL files to read (default: stdin)",
    )
    args = parser.parse_args(argv)

    def _iter(paths):
        if not paths:
            for line in sys.stdin:
                yield line
            return
        for path in paths:
            with open(path, "r", errors="replace") as fh:
                for line in fh:
                    yield line

    print(json.dumps(summarize(_iter(args.paths)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
