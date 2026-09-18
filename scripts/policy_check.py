"""Policy-as-code checks on the tool catalogue (catalog/tools.yaml).

Run: ``python scripts/policy_check.py`` (exit 1 on any violation). Part of
the permit-to-operate gate; also imported by tests/test_policy.py.

Rules
  P1  every tool has kind (read|write), non-empty roles drawn from the
      declared roles, a description and an example
  P2  description is at most 60 tokens (approximate: words + punctuation)
  P3  every write tool is hitl: true, its example carries confirm and
      idempotency_key, and viewer is never allowed to call it
  P4  every row-returning tool declares selectable fields, including
      source_ref
  P5  no selectable field or example key matches a raw-PII pattern
  P6  names are unique snake_case; rate_limit is a positive integer
"""

import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_PATH = os.path.join(ROOT, "catalog", "tools.yaml")
MAX_DESCRIPTION_TOKENS = 60


def approx_tokens(text):
    """Rough token count: words and punctuation marks."""
    return len(re.findall(r"\w+|[^\w\s]", text or ""))


def load_catalog(path=CATALOG_PATH):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _keys(obj):
    """All dict keys nested anywhere in obj."""
    found = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.add(str(k))
            found |= _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _keys(v)
    return found


def check(catalog):
    """Return a list of violation strings (empty means compliant)."""
    problems = []
    roles = set(catalog.get("roles") or [])
    pii = [p.lower() for p in catalog.get("pii_field_patterns") or []]
    names = []
    for tool in catalog.get("tools") or []:
        name = tool.get("name", "<unnamed>")
        names.append(name)

        def bad(rule, msg, name=name):
            problems.append(f"{rule} {name}: {msg}")

        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            bad("P6", "name must be snake_case")
        if tool.get("kind") not in ("read", "write"):
            bad("P1", "kind must be read or write")
        tool_roles = tool.get("roles") or []
        if not tool_roles or not set(tool_roles) <= roles:
            bad("P1", f"roles must be a non-empty subset of {sorted(roles)}")
        if not tool.get("description"):
            bad("P1", "description is required")
        elif approx_tokens(tool["description"]) > MAX_DESCRIPTION_TOKENS:
            bad("P2", f"description is {approx_tokens(tool['description'])} "
                      f"tokens (max {MAX_DESCRIPTION_TOKENS})")
        example = tool.get("example")
        if not isinstance(example, dict) or not example:
            bad("P1", "example must be a non-empty mapping")
            example = {}
        if tool.get("kind") == "write":
            if tool.get("hitl") is not True:
                bad("P3", "write tools must set hitl: true")
            for key in ("confirm", "idempotency_key"):
                if key not in example:
                    bad("P3", f"write tool example must include {key}")
            if "viewer" in tool_roles:
                bad("P3", "viewer may not call a write tool")
        if tool.get("returns_rows"):
            fields = tool.get("fields") or []
            if not fields:
                bad("P4", "row-returning tools must declare fields")
            elif "source_ref" not in fields:
                bad("P4", "fields must include source_ref")
        for key in set(tool.get("fields") or []) | _keys(example):
            if any(p in key.lower() for p in pii):
                bad("P5", f"field or example key '{key}' looks like raw PII")
        rate = tool.get("rate_limit")
        if not isinstance(rate, int) or isinstance(rate, bool) or rate < 1:
            bad("P6", "rate_limit must be a positive integer")
    dupes = {n for n in names if names.count(n) > 1}
    for n in sorted(dupes):
        problems.append(f"P6 {n}: duplicate tool name")
    return problems


def main(argv=None):
    path = argv[0] if argv else CATALOG_PATH
    catalog = load_catalog(path)
    problems = check(catalog)
    tools = catalog.get("tools") or []
    if problems:
        print(f"Policy check FAILED for {path}: {len(problems)} violation(s)")
        for p in problems:
            print("  -", p)
        return 1
    writes = sum(1 for t in tools if t.get("kind") == "write")
    longest = max(approx_tokens(t["description"]) for t in tools)
    print(f"Policy check OK: {len(tools)} tools ({writes} write, all HITL), "
          f"{len(catalog.get('roles') or [])} roles, longest description "
          f"{longest} tokens")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
