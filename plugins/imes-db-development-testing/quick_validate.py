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
        ROOT / "references" / "metadata-join-help-defects.md",
        ROOT / "scripts" / "audit_live_dynamic_bills.sql",
        ROOT / "scripts" / "scan_metadata_defects.sql",
        ROOT / "scripts" / "validate_dynamic_bill_artifacts.py",
        ROOT / "scripts" / "self_test.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing skill files: " + ", ".join(missing))

    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    contract = (ROOT / "references" / "client-source-contract.md").read_text(encoding="utf-8")
    audit = (ROOT / "scripts" / "audit_live_dynamic_bills.sql").read_text(encoding="utf-8")
    scanner = (ROOT / "scripts" / "scan_metadata_defects.sql").read_text(encoding="utf-8")
    join_ref = (ROOT / "references" / "metadata-join-help-defects.md").read_text(encoding="utf-8")

    required_markers = (
        "Live 元数据全量门禁",
        "audit_live_dynamic_bills.sql",
        "BDJB",
        "AppData.adddate",
        "明细单号",
        "scan_metadata_defects.sql",
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

    # 元数据缺陷扫描脚本必须保持只读
    for token in ("INSERT dbo.", "UPDATE dbo.", "DELETE dbo.", "CREATE TABLE dbo.", "ALTER TABLE"):
        if token.upper() in scanner.upper():
            raise SystemExit(f"metadata defect scanner must remain read-only: {token}")

    # 扫描脚本必须覆盖七类缺陷
    for token in ("同一 Vkey 多行 TOP=1", "同表同 PO 同 GLZD", "帮助填了中文名",
                  "切换=1 但 GLZD 为空", "GLZD 没有 TOP=1 路由",
                  "元数据字段名在物理表里不存在", "Filter 形状可疑"):
        if token not in scanner:
            raise SystemExit(f"scanner is missing a defect class: {token}")

    # 对照参考必须覆盖报错原文到规则的映射
    for token in ("关键字 'from'", "关键字 'with'", "1013", "bit", "TOP=0", "LMark"):
        if token not in join_ref:
            raise SystemExit(f"join/help reference is missing: {token}")

    print("IMES skill quick validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
