#!/usr/bin/env python3
"""Fast structural validation for the IMES database-development skill."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> int:
    required = (
        ROOT / "SKILL.md",
        ROOT / "references" / "client-source-contract.md",
        ROOT / "references" / "document-form-contract.md",
        ROOT / "references" / "complex-form-fast-path.md",
        ROOT / "scripts" / "audit_live_dynamic_bills.sql",
        ROOT / "scripts" / "validate_dynamic_bill_artifacts.py",
        ROOT / "scripts" / "self_test.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing skill files: " + ", ".join(missing))

    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    contract = (ROOT / "references" / "client-source-contract.md").read_text(encoding="utf-8")
    audit = (ROOT / "scripts" / "audit_live_dynamic_bills.sql").read_text(encoding="utf-8")

    required_markers = (
        "Live 元数据全量门禁",
        "audit_live_dynamic_bills.sql",
        "BDJB",
        "AppData.adddate",
        "明细单号",
    )
    for marker in required_markers:
        if marker not in skill and marker not in contract:
            raise SystemExit(f"missing contract marker: {marker}")

    forbidden_write_shapes = ("INSERT dbo.", "UPDATE dbo.", "DELETE dbo.", "CREATE TABLE dbo.")
    for token in forbidden_write_shapes:
        if token.upper() in audit.upper():
            raise SystemExit(f"live audit must remain read-only: {token}")

    for token in ("@Forms", "RELATION_NULL_ALIAS", "DETAIL_ALIAS", "BDJB_BASE", "AuditStatus", "IOJCBDZD_TOP=1"):
        if token not in audit:
            raise SystemExit(f"live audit is missing required check: {token}")

    print("IMES skill quick validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
