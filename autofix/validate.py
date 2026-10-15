"""Decide if a test crawl's output is good enough to propose a fix.

Checks:
  1. at least `min_items` items
  2. each item passes the JSON Schema (same contract as the Schema Validator page)
  3. fill rate of each required field is within `max_fill_drop` of the last good run
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    ok: bool
    items: int
    problems: list[str] = field(default_factory=list)
    fill_rates: dict[str, float] = field(default_factory=dict)
    sample: list[dict] = field(default_factory=list)


def read_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def fill_rates(items: list[dict], fields: list[str]) -> dict[str, float]:
    if not items:
        return {f: 0.0 for f in fields}
    return {f: sum(1 for it in items if it.get(f) not in (None, "", [], {})) / len(items)
            for f in fields}


def validate(items: list[dict], schema: dict | None = None,
             baseline_fill: dict[str, float] | None = None,
             min_items: int = 20, max_fill_drop: float = 0.15,
             sample_size: int = 20) -> ValidationResult:
    problems: list[str] = []

    if len(items) < min_items:
        problems.append(f"only {len(items)} items, need {min_items}")

    if schema:
        from jsonschema import Draft202012Validator
        v = Draft202012Validator(schema)
        bad = 0
        first_err = None
        for it in items:
            errs = list(v.iter_errors(it))
            if errs:
                bad += 1
                first_err = first_err or errs[0].message
        if bad:
            problems.append(f"{bad}/{len(items)} items fail schema (e.g. {first_err})")

    fields = list((schema or {}).get("required", [])) or list(baseline_fill or {})
    rates = fill_rates(items, fields)
    for f, base in (baseline_fill or {}).items():
        now = rates.get(f, 0.0)
        if now < base - max_fill_drop:
            problems.append(f"field '{f}' filled {now:.0%} vs {base:.0%} in last good run")

    return ValidationResult(not problems, len(items), problems, rates, items[:sample_size])
