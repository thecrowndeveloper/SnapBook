#!/usr/bin/env python3
"""Stdlib-only evidence gate for RPI JSON change records.

Validates record structure and that phase evidence is present. It cannot assess
whether evidence is truthful, sufficient, safe, or whether code is secure.
"""
import argparse
import json
import sys
from pathlib import Path

VALID_DEPTHS = {"quick", "standard", "deep"}
VALID_STATUSES = {"research", "plan", "implement", "complete", "hold"}
VALID_RISKS = {"low", "medium", "high", "critical"}
VALID_DEPLOYMENTS = {"not_requested", "pending", "succeeded", "failed"}

def nonempty(value):
    return isinstance(value, str) and bool(value.strip())

def list_has_text(value):
    return isinstance(value, list) and any(nonempty(item) for item in value)

def validate(record):
    errors = []
    if not isinstance(record, dict):
        return ["record must be a JSON object"]
    for field in ("project", "change_id", "title"):
        if not nonempty(record.get(field)):
            errors.append(f"missing non-empty field: {field}")
    if record.get("workflow") != "RPI":
        errors.append("workflow must equal 'RPI'")
    if record.get("depth") not in VALID_DEPTHS:
        errors.append(f"depth must be one of: {', '.join(sorted(VALID_DEPTHS))}")
    if record.get("status") not in VALID_STATUSES:
        errors.append(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    if record.get("risk_level") not in VALID_RISKS:
        errors.append(f"risk_level must be one of: {', '.join(sorted(VALID_RISKS))}")

    research = record.get("research")
    if not isinstance(research, dict):
        errors.append("research must be an object")
    else:
        if not list_has_text(research.get("findings")):
            errors.append("research.findings needs at least one non-empty finding")
        if not list_has_text(research.get("evidence")):
            errors.append("research.evidence needs at least one evidence reference")
        if not isinstance(research.get("assumptions"), list):
            errors.append("research.assumptions must be a list")
        if not isinstance(research.get("unknowns"), list):
            errors.append("research.unknowns must be a list")

    plan = record.get("plan")
    if not isinstance(plan, dict):
        errors.append("plan must be an object")
    else:
        for field in ("scope", "acceptance_criteria", "risks", "test_strategy"):
            if not list_has_text(plan.get(field)):
                errors.append(f"plan.{field} needs at least one non-empty entry")
        if not nonempty(plan.get("rollback")):
            errors.append("plan.rollback must describe rollback/recovery")
        if plan.get("approval") not in {"not_required", "pending", "approved"}:
            errors.append("plan.approval must be not_required, pending, or approved")

    implementation = record.get("implementation")
    if not isinstance(implementation, dict):
        errors.append("implementation must be an object")
    else:
        if record.get("status") in {"implement", "complete"}:
            if not list_has_text(implementation.get("changed_files")):
                errors.append("implementation.changed_files needs at least one file")
            if not list_has_text(implementation.get("tests")):
                errors.append("implementation.tests needs at least one test/check result")
            if not nonempty(implementation.get("review")):
                errors.append("implementation.review must contain a diff review note")
        if implementation.get("deployment") not in VALID_DEPLOYMENTS:
            errors.append(f"implementation.deployment must be one of: {', '.join(sorted(VALID_DEPLOYMENTS))}")
        if not isinstance(implementation.get("post_deploy_verification"), list):
            errors.append("implementation.post_deploy_verification must be a list")

    if record.get("status") == "complete":
        if not isinstance(implementation, dict) or implementation.get("deployment") == "pending":
            errors.append("complete status cannot have deployment pending")
        if not isinstance(implementation, dict) or implementation.get("deployment") == "succeeded":
            if not list_has_text(implementation.get("post_deploy_verification")):
                errors.append("successful deployment needs post-deploy verification evidence")
    return errors

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True, help="Path to RPI JSON record")
    args = parser.parse_args()
    path = Path(args.record)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read valid JSON record: {exc}", file=sys.stderr)
        return 2
    errors = validate(data)
    if errors:
        print("RPI evidence gate: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("RPI evidence gate: PASS (structure/evidence presence only; not evidence truth or quality)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
