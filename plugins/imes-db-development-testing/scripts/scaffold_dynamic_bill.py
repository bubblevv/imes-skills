#!/usr/bin/env python3
"""Scaffold an IMES dynamic-bill contract from an ER SVG.

This tool is intentionally review-only: it parses the ER diagram and emits a
contract manifest, a physical-schema draft, read-only preflight SQL, and a
reference-evidence query pack. It does not connect to SQL Server and never
writes database objects.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

FIELD_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")
TABLE_RE = re.compile(r"^表(?:头|体)\s*[·•]\s*([A-Za-z][A-Za-z0-9_]*)")
GENERIC_TABLE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s*[·•]\s*.+$")
TYPE_RE = re.compile(
    r"^(?:var)?char\(\d+\)$|^(?:big)?int$|^smallint$|^bit$|^datetime(?:2)?$|^date$|^decimal\(\d+,\d+\)$",
    re.I,
)


def xml_texts(svg_path: Path) -> list[str]:
    root = ET.parse(svg_path).getroot()
    result: list[str] = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "text":
            continue
        value = "".join(node.itertext()).strip()
        if value:
            result.append(value)
    return result


def parse_tables(svg_path: Path) -> dict[str, dict[str, Any]]:
    texts = xml_texts(svg_path)
    tables: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    pending_markers: set[str] = set()
    i = 0
    while i < len(texts):
        value = texts[i]
        match = TABLE_RE.match(value)
        if match:
            table_name = match.group(1)
            role = "header" if value.startswith("表头") else "detail"
            current = tables.setdefault(table_name, {"table": table_name, "roles": set(), "fields": []})
            current["roles"].add(role)
            pending_markers.clear()
            i += 1
            continue
        # Standalone ER tables terminate the previous table context.
        generic_match = GENERIC_TABLE_RE.match(value)
        if generic_match and not value.startswith(("表头", "表体")):
            table_name = generic_match.group(1)
            current = tables.setdefault(table_name, {"table": table_name, "roles": set(), "fields": []})
            current["roles"].add("standalone")
            pending_markers.clear()
            i += 1
            continue
        if current is None:
            i += 1
            continue
        if value in {"PK", "FK"}:
            pending_markers.add(value.lower())
            i += 1
            continue
        if FIELD_RE.fullmatch(value):
            # ER layout: field, Chinese label, type; PK/FK badges precede field.
            label = texts[i + 1] if i + 1 < len(texts) else ""
            type_name = texts[i + 2] if i + 2 < len(texts) else ""
            if label and TYPE_RE.fullmatch(type_name):
                current["fields"].append(
                    {
                        "name": value,
                        "label": label,
                        "er_type": type_name,
                        "pk": "pk" in pending_markers,
                        "fk": "fk" in pending_markers,
                    }
                )
                pending_markers.clear()
                i += 3
                continue
        i += 1

    for table in tables.values():
        table["roles"] = sorted(table["roles"])
    return tables


def sql_literal(value: str) -> str:
    return "N'" + value.replace("'", "''") + "'"


def safe_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"unsafe identifier: {value!r}")
    return value


def contract_diff(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Compare ER field contracts and flag additions, removals, and likely renames."""
    old_tables = {table["table"]: table for table in baseline.get("tables", [])}
    new_tables = {table["table"]: table for table in current.get("tables", [])}
    added: list[dict[str, str]] = []
    removed: list[dict[str, str]] = []
    renamed: list[dict[str, str]] = []
    for table_name in sorted(set(old_tables) | set(new_tables)):
        old_fields = {field["name"]: field for field in old_tables.get(table_name, {}).get("fields", [])}
        new_fields = {field["name"]: field for field in new_tables.get(table_name, {}).get("fields", [])}
        for name in sorted(set(new_fields) - set(old_fields)):
            field = new_fields[name]
            added.append({"table": table_name, "field": name, "label": field.get("label", "")})
        for name in sorted(set(old_fields) - set(new_fields)):
            field = old_fields[name]
            removed.append({"table": table_name, "field": name, "label": field.get("label", "")})
        old_by_label = {field.get("label"): name for name, field in old_fields.items() if field.get("label")}
        new_by_label = {field.get("label"): name for name, field in new_fields.items() if field.get("label")}
        for label in sorted(set(old_by_label) & set(new_by_label)):
            old_name, new_name = old_by_label[label], new_by_label[label]
            if old_name != new_name:
                renamed.append({"table": table_name, "from": old_name, "to": new_name, "label": label})
    return {
        "baseline_source": baseline.get("source"),
        "current_source": current.get("source"),
        "changed": bool(added or removed or renamed),
        "added": added,
        "removed": removed,
        "likely_renames": renamed,
        "review_rule": "字段变更后不得复用旧 forward/rollback/verification/crud；必须重新评审物理列、元数据、查询页和测试。",
    }


def render_schema(manifest: dict[str, Any]) -> str:
    lines = [
        "/* REVIEW-ONLY draft generated by scaffold_dynamic_bill.py.",
        "   Do not deploy until runtime contract, key strategy, audit columns,",
        "   Unicode types, foreign-key targets, and metadata are confirmed. */",
        "SET NOCOUNT ON;",
        "",
    ]
    for table in manifest["tables"]:
        table_name = safe_identifier(table["table"])
        lines.extend(
            [
                f"IF OBJECT_ID(N'dbo.{table_name}', N'U') IS NOT NULL",
                f"    THROW 51000, N'{table_name} already exists; review before changing it.', 1;",
                f"CREATE TABLE dbo.{table_name}",
                "(",
            ]
        )
        columns: list[str] = []
        for field in table["fields"]:
            name = safe_identifier(field["name"])
            er_type = field["er_type"]
            nullability = "NOT NULL" if field["pk"] else "NULL"
            note = " -- FK target unresolved" if field["fk"] else ""
            columns.append(f"    {name:<32} {er_type:<14} {nullability},{note}")
        if not columns:
            lines.append("    -- No ER fields parsed; stop and inspect the SVG.")
        else:
            lines.extend(columns)
            pk = [f["name"] for f in table["fields"] if f["pk"]]
            if pk:
                quoted = ", ".join(safe_identifier(x) for x in pk)
                lines.append(f"    CONSTRAINT PK_{table_name} PRIMARY KEY ({quoted})")
            else:
                lines[-1] = lines[-1].rstrip(",")
        lines.extend([f");", ""])
    return "\n".join(lines)


def render_preflight(manifest: dict[str, Any]) -> str:
    lines = [
        "/* Read-only preflight generated by scaffold_dynamic_bill.py. */",
        "SET NOCOUNT ON;",
        "SELECT DB_NAME() AS CurrentDatabase, @@SERVERNAME AS CurrentServer;",
        "",
    ]
    if manifest.get("expected_database"):
        db = sql_literal(manifest["expected_database"])
        lines.extend(
            [
                f"IF DB_NAME() <> {db}",
                "    THROW 51001, N'Connected database does not match the expected target.', 1;",
                "",
            ]
        )
    for table in manifest["tables"]:
        table_name = safe_identifier(table["table"])
        lines.extend(
            [
                f"SELECT N'{table_name}' AS ExpectedTable,",
                "       c.name AS ColumnName, TYPE_NAME(c.user_type_id) AS DataType,",
                "       c.max_length, c.is_nullable, c.column_id",
                "FROM sys.columns AS c",
                f"WHERE c.object_id = OBJECT_ID(N'dbo.{table_name}', N'U')",
                "ORDER BY c.column_id;",
                "",
            ]
        )
    bill_name = manifest.get("bill_name")
    if bill_name:
        lines.extend(
            [
                "SELECT * FROM dbo.IOBDZD WHERE IOBDZD_MC = " + sql_literal(bill_name) + ";",
                "SELECT * FROM dbo.BDJB WHERE BDJB_PJLX = " + sql_literal(bill_name) + ";",
                "SELECT * FROM dbo.SYS_TbColumn WHERE 表名 IN ("
                + sql_literal(bill_name)
                + ", "
                + sql_literal(bill_name + "查询")
                + ") ORDER BY 表名, TRY_CONVERT(int, PO), 顺序, 字段名;",
                "SELECT * FROM dbo.SYSWSPACE WHERE SYSWSPACE_MC = " + sql_literal(bill_name) + ";",
            ]
        )
    return "\n".join(lines) + "\n"


def render_reference_evidence(manifest: dict[str, Any]) -> str:
    """Render read-only evidence queries for a same-version working bill."""
    reference = manifest.get("reference_bill_name")
    lines = [
        "/* Read-only reference evidence generated by scaffold_dynamic_bill.py.",
        "   Run this against the confirmed target database before designing",
        "   SYS_TbColumn coordinates, lookup mappings, or BDJB rules. */",
        "SET NOCOUNT ON;",
        "SELECT DB_NAME() AS CurrentDatabase, @@SERVERNAME AS CurrentServer;",
        "",
    ]
    if not reference:
        lines.extend(
            [
                "/* No --reference-bill-name was supplied.",
                "   Re-run the scaffold with a same-version, working bill name;",
                "   do not use the target bill as its own layout evidence. */",
            ]
        )
        return "\n".join(lines) + "\n"

    reference_literal = sql_literal(reference)
    lines.extend(
        [
            "IF OBJECT_ID(N'dbo.IOBDZD', N'U') IS NULL",
            "    THROW 51002, N'IOBDZD is missing; stop and inspect the target schema.', 1;",
            "IF OBJECT_ID(N'dbo.SYS_TbColumn', N'U') IS NULL",
            "    THROW 51003, N'SYS_TbColumn is missing; stop and inspect the target schema.', 1;",
            "",
            f"DECLARE @ReferenceBillName nvarchar(100) = {reference_literal};",
            "",
            "-- Confirm the route and the physical header/detail tables first.",
            "SELECT * FROM dbo.IOBDZD WHERE IOBDZD_MC = @ReferenceBillName;",
            "",
            "-- Capture the complete visible header contract, not just the input rectangle.",
            "SELECT 表名, PO, 顺序, 字段名, 显示名, 显示, 左坐标, 顶坐标, 宽度, 高度, 控件, 列宽, 标识,",
            "       左坐标 + 宽度 AS RightEdge, 顶坐标 + 高度 AS BottomEdge",
            "FROM dbo.SYS_TbColumn",
            "WHERE 表名 = @ReferenceBillName AND PO = N'1' AND 显示 = 1",
            "ORDER BY 顺序, RID;",
            "",
            "-- Audit/footer geometry is reference evidence; the target audit top may be derived from the last non-fixed header field.",
            "-- Layout review: walk visible header fields by 顺序, try the current row first,",
            "-- and wrap only when the complete label/input/help footprint exceeds the reference right edge.",
            "-- SHBZ is not an automatically isolated column; its bottom remains the header lower bound.",
            "SELECT 表名, PO, 顺序, 字段名, 显示名, 显示, 左坐标, 顶坐标, 宽度, 高度, 控件, 列宽, 标识,",
            "       左坐标 + 宽度 AS RightEdge, 顶坐标 + 高度 AS BottomEdge",
            "FROM dbo.SYS_TbColumn",
            "WHERE 表名 = @ReferenceBillName AND PO = N'1'",
            "  AND (RIGHT(字段名, 5) = N'_SHBZ' OR RIGHT(字段名, 4) IN (N'_ZDR', N'_SHR') OR RIGHT(字段名, 3) = N'_ZY')",
            "ORDER BY 顺序, RID;",
            "",
            "SELECT N'audit-bottom' AS Evidence, MAX(顶坐标 + 高度) AS AuditBottom",
            "FROM dbo.SYS_TbColumn",
            "WHERE 表名 = @ReferenceBillName AND PO = N'1' AND RIGHT(字段名, 5) = N'_SHBZ';",
            "",
            "SELECT N'last-non-fixed-header-bottom' AS Evidence, MAX(顶坐标 + 高度) AS LastHeaderBottom",
            "FROM dbo.SYS_TbColumn",
            "WHERE 表名 = @ReferenceBillName AND PO = N'1' AND 显示 = 1",
            "  AND RIGHT(UPPER(字段名), 5) NOT IN (N'_SHBZ', N'_PJLX')",
            "  AND RIGHT(UPPER(字段名), 4) NOT IN (N'_ZDR', N'_SHR')",
            "  AND RIGHT(UPPER(字段名), 3) <> N'_ZY';",
            "",
            "-- Non-empty 帮助 fields must leave room inside the input outer width for the browse button.",
            "SELECT 字段名,帮助,宽度,",
            "       CASE WHEN NULLIF(LTRIM(RTRIM(帮助)),N'') IS NULL THEN 0 ELSE 20 END AS RequiredBrowseButtonWidth,",
            "       CASE WHEN NULLIF(LTRIM(RTRIM(帮助)),N'') IS NULL OR 宽度 > 20 THEN 1 ELSE 0 END AS BrowseWidthPass",
            "FROM dbo.SYS_TbColumn",
            "WHERE 表名=@ReferenceBillName AND PO=N'1' AND 显示=1",
            "ORDER BY 顺序,字段名;",
        ]
    )
    return "\n".join(lines) + "\n"


def render_readme(manifest: dict[str, Any]) -> str:
    tables = ", ".join(t["table"] for t in manifest["tables"])
    reference = manifest.get("reference_bill_name") or "未指定（请补充同版本有效单据）"
    return f"""# 动态单据脚手架（审核稿）

来源 ER 图：`{manifest['source']}`

解析到的表：{tables}

参考布局单据：{reference}

## 这次工具已经做的事

- 从 SVG 的 `表头 · ...` / `表体 · ...` 区块提取字段、中文标签、ER 类型、PK/FK 标记；
- 生成 `contract.json`、`schema-draft.sql`、只读 `preflight.sql` 和 `reference-evidence.sql`；
- `reference-evidence.sql` 只读取同版本有效单据的 IOBDZD、表头布局、审核/制单/摘要锚点，并列出帮助字段的浏览按钮占用；审核按顺序先尝试同行，避免审核宽度和坐标凭经验填写；
- 将未知的动态单据约定保留为待确认项，不自动写入数据库。

## 部署前必须补齐

1. 用目标测试库的同类有效单据确认 `_ID`、`_SJDH`、`_FLH` 的实际类型和主键策略；
2. 明确标准审核列（通常是 `SHBZ/ZDR/SHR`）是否属于物理表，不能把 ER 图省略字段直接当成可查询列；
3. 明确 `IOBDZD` 编号、`MARK`、`FORMAT`、HVKey/FVKey、单号格式及是否冲突；新建契约缺省 `FORMAT` 固定为 `YYMM####`，不能留空；编号过程按可见名 `IOBDZD_MC` 读取它，`BILLNO` 不是格式入口；
4. 为每个 `PO=1/2` 字段生成有效 `SYS_TbColumn`，`标识` 保持 NULL，禁止猜写 `0`；
5. 先运行 `reference-evidence.sql`，从同版本有效单据复制完整审核/制单/摘要布局；
6. 配置维护页与独立的 `<单据名>查询` 元数据、帮助映射、BDJB 审核/撤审、SYSWSPACE 权限；
7. 运行 runtime-shaped verification 和隔离 CRUD 冒烟测试后再部署；
8. 若生成了 `contract-diff.json`，先处理新增/删除/疑似改名字段；不得直接复用旧部署脚本。

本产物是草稿，不执行数据库写入，也不代表 MFC 客户端对话框已经创建。
"""


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    tables = parse_tables(args.er_svg)
    wanted = [args.header_table, args.detail_table]
    missing = [name for name in wanted if name not in tables or not tables[name]["fields"]]
    if missing:
        raise ValueError("未从 ER 图解析到表或字段: " + ", ".join(missing))
    return {
        "source": str(args.er_svg),
        "bill_name": args.bill_name,
        "reference_bill_name": args.reference_bill_name,
        "expected_database": args.expected_database,
        "header_table": args.header_table,
        "detail_table": args.detail_table,
        "tables": [tables[name] for name in wanted],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--er-svg", type=Path, required=True)
    parser.add_argument("--header-table", required=True)
    parser.add_argument("--detail-table", required=True)
    parser.add_argument("--bill-name", help="Optional target IOBDZD/SYS_TbColumn bill name.")
    parser.add_argument("--reference-bill-name", help="Optional same-version working bill used for read-only layout evidence.")
    parser.add_argument("--expected-database", help="Optional database guard for preflight SQL.")
    parser.add_argument("--baseline-contract", type=Path, help="Optional previous contract.json for drift review.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if not args.er_svg.is_file():
            raise ValueError(f"ER SVG not found: {args.er_svg}")
        manifest = build_manifest(args)
        diff = None
        if args.baseline_contract:
            if not args.baseline_contract.is_file():
                raise ValueError(f"baseline contract not found: {args.baseline_contract}")
            baseline = json.loads(args.baseline_contract.read_text(encoding="utf-8"))
            diff = contract_diff(baseline, manifest)
        if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.force:
            raise ValueError(f"output directory is not empty: {args.output_dir}")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "contract.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (args.output_dir / "schema-draft.sql").write_text(render_schema(manifest), encoding="utf-8")
        (args.output_dir / "preflight.sql").write_text(render_preflight(manifest), encoding="utf-8")
        (args.output_dir / "reference-evidence.sql").write_text(
            render_reference_evidence(manifest), encoding="utf-8"
        )
        (args.output_dir / "README.md").write_text(render_readme(manifest), encoding="utf-8")
        if diff is not None:
            (args.output_dir / "contract-diff.json").write_text(
                json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    except (OSError, ET.ParseError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Generated dynamic-bill scaffold in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
