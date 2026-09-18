"""The catalogue is compliant, and the policy checks catch each rule."""

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from policy_check import approx_tokens, check, load_catalog  # noqa: E402


def _catalog():
    return copy.deepcopy(load_catalog())


def _tool(catalog, name):
    return next(t for t in catalog["tools"] if t["name"] == name)


def test_shipped_catalog_is_compliant():
    catalog = load_catalog()
    assert check(catalog) == []
    assert len(catalog["tools"]) == 10
    writes = [t for t in catalog["tools"] if t["kind"] == "write"]
    assert {t["name"] for t in writes} == {"add_incident_comment",
                                           "propose_stories"}


def test_every_description_is_within_budget():
    for tool in load_catalog()["tools"]:
        assert approx_tokens(tool["description"]) <= 60, tool["name"]


def test_write_tool_without_hitl_is_rejected():
    catalog = _catalog()
    _tool(catalog, "add_incident_comment")["hitl"] = False
    assert any(p.startswith("P3") for p in check(catalog))


def test_write_tool_open_to_viewer_is_rejected():
    catalog = _catalog()
    _tool(catalog, "propose_stories")["roles"].append("viewer")
    assert any("viewer" in p for p in check(catalog))


def test_write_example_must_show_confirm_and_key():
    catalog = _catalog()
    del _tool(catalog, "propose_stories")["example"]["confirm"]
    assert any("confirm" in p for p in check(catalog))


def test_long_description_is_rejected():
    catalog = _catalog()
    _tool(catalog, "get_incident")["description"] = "word " * 70
    assert any(p.startswith("P2") for p in check(catalog))


def test_rows_without_source_ref_are_rejected():
    catalog = _catalog()
    _tool(catalog, "search_incidents")["fields"].remove("source_ref")
    assert any(p.startswith("P4") for p in check(catalog))


def test_pii_field_is_rejected():
    catalog = _catalog()
    _tool(catalog, "search_incidents")["fields"].append("reporter_email")
    problems = check(catalog)
    assert any(p.startswith("P5") and "reporter_email" in p
               for p in problems)


def test_unknown_role_and_duplicate_name_are_rejected():
    catalog = _catalog()
    _tool(catalog, "get_incident")["roles"] = ["admin"]
    catalog["tools"].append(copy.deepcopy(_tool(catalog, "draft_rca")))
    problems = check(catalog)
    assert any(p.startswith("P1") for p in problems)
    assert any("duplicate" in p for p in problems)
