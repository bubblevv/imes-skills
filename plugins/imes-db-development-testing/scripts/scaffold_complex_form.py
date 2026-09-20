#!/usr/bin/env python3
"""Generate a four-stage IMES header/detail form review or deployment pack.

The generator is offline and fail-closed.  An ER SVG produces a review-blocked
pack; a completed contract produces preflight, forward, verification, isolated
CRUD, and guarded rollback scripts.  It never connects to SQL Server.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from scaffold_dynamic_bill import parse_tables
except ImportError:  # pragma: no cover
    from .scaffold_dynamic_bill import parse_tables

try:
    from metadata_width import label_column_width
except ImportError:  # pragma: no cover
    from .metadata_width import label_column_width

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TYPE_RE = re.compile(r"^(?:bigint|int|smallint|tinyint|bit|date|datetime|datetime2|(?:var)?char\((?:MAX|[1-9][0-9]*)\)|decimal\([1-9][0-9]*,[0-9]+\))(?:\s+IDENTITY\([0-9]+,[0-9]+\))?$", re.I)
META_COLUMNS = [
    "表名", "PO", "字段名", "主键", "RMark", "显示名", "标签名", "不控", "显示", "列宽", "顺序",
    "合计", "按钮", "只读", "表头", "颜色值", "新增", "更新", "置空", "筛选", "必填", "合并",
    "对齐", "切换", "GLZD", "LMark", "类型", "帮助", "标识", "默认值", "管道字符", "关键字段",
    "左坐标", "顶坐标", "宽度", "高度", "admin", "优先级", "左对齐", "右对齐", "顶对齐", "底对齐",
    "控件", "RID",
]
META_TEXT = {0, 2, 4, 5, 6, 24, 25, 26, 27, 28, 29, 30, 36, 38, 39, 40, 41, 42}
FORM_KINDS = {"inspection_template", "inspection_record", "audit_bill", "header_detail_bill"}
FIXED_HEADER_SUFFIXES = ("_SHBZ", "_PJLX", "_ZDR", "_SHR", "_ZY")
# Proven by the active BCGPEdit implementation: EnableBrowseButton(true)
# resets the image and OnChangeLayout uses max(20, imageWidth + 8).
DEFAULT_BROWSE_BUTTON_WIDTH = 20
MIN_LAYOUT_GAP = 10
REQUIRED_SYSMENU_BUTTONS = (
    # Keep the single-space pmenu/uid values stored by the Sales Order rows.
    ("显示关联单据", 0, "3", 40, 0, " ", 0, " "),
    ("保存列宽", 0, "3", 0, 1, "其他", 1, " "),
    ("列配置", 0, "4", 0, 1, "其他", 0, " "),
    ("从EXCEL导入", 0, "5", 0, 1, "其他", 0, " "),
    ("说明", 1, "3", 24, 0, " ", 0, " "),
    ("附件", 0, "3", 24, 0, " ", 0, " "),
    ("复制分录", 1, "3", 40, 0, " ", 0, " "),
)
DEFAULT_IOBDZD_FORMAT = "YYMM####"
IOBDZD_FORMAT_RE = re.compile(r"^(?:YYMM(?:#+)?|YYYYMM(?:#+)?|YYMMDD(?:#+)?|#+)$", re.I)


def normalize_iobdzd_format(value: Any) -> str:
    """Normalize the number format used by PRD_GETDANHAO.

    The stored procedure reads this value by IOBDZD_MC.  A missing/blank
    contract value is therefore not a harmless SQL NULL: it prevents the
    procedure from entering a numbering branch.  Keep explicit supported
    formats, while making the requested YYMM#### default deterministic.
    """
    if value is None:
        return DEFAULT_IOBDZD_FORMAT
    normalized = str(value).strip().upper()
    if not normalized:
        return DEFAULT_IOBDZD_FORMAT
    if not IOBDZD_FORMAT_RE.fullmatch(normalized):
        raise ValueError(
            "route.format must be a non-empty PRD_GETDANHAO format "
            "(YYMM, YYYYMM, YYMMDD, or # serial pattern)"
        )
    return normalized

def resolve_column_width(field: dict[str, Any], row: dict[str, Any], visible: bool) -> int:
    """Resolve a metadata grid width without confusing it with layout width."""
    label = row.get("label") or field.get("label") or field["name"]
    minimum = label_column_width(label)
    requested = row.get("column_width")
    if requested is None and "width" in row and not any(key in row for key in ("left", "top", "height")):
        # Compatibility for old detail-only contracts where width represented
        # both grid and control width. Layout rows should use column_width.
        requested = row.get("width")
    if requested in (None, ""):
        return minimum
    try:
        width = int(requested)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field['name']}: column_width must be an integer") from exc
    if width <= 0:
        raise ValueError(f"{field['name']}: column_width must be positive")
    if visible and width < minimum:
        raise ValueError(
            f"{field['name']}: column_width {width} is smaller than label minimum {minimum}; "
            "first-view labels must be fully visible"
        )
    return width


def required_sysmenu_rows(bill_name: str) -> list[dict[str, Any]]:
    return [
        {
            "sysmenu_bdmc": bill_name,
            "sysmenu_topfloor": topfloor,
            "sysmenu_xh": xh,
            "sysmenu_buttonname": button,
            "sysmenu_icon": icon,
            "sysmenu_submenu": submenu,
            "sysmenu_pmenu": pmenu,
            "sysmenu_trimenu": trimenu,
            "sysmenu_uid": uid,
        }
        for button, topfloor, xh, icon, submenu, pmenu, trimenu, uid in REQUIRED_SYSMENU_BUTTONS
    ]


def is_fixed_header_anchor(field_name: str) -> bool:
    upper_name = str(field_name).upper()
    return any(upper_name.endswith(suffix) for suffix in FIXED_HEADER_SUFFIXES)


def sysmenu_expected_values(bill_name: str) -> str:
    rows = required_sysmenu_rows(bill_name)
    return ",\n".join(
        "    (" + ",".join(
            sqlv(row[key], text=not isinstance(row[key], (int, float, bool)))
            for key in ("sysmenu_buttonname", "sysmenu_topfloor", "sysmenu_xh", "sysmenu_icon", "sysmenu_submenu", "sysmenu_pmenu", "sysmenu_trimenu", "sysmenu_uid")
        ) + ")"
        for row in rows
    )


def qi(value: str) -> str:
    if not IDENT_RE.fullmatch(str(value)):
        raise ValueError(f"unsafe identifier: {value!r}")
    return f"[{value}]"


def qmeta(value: str) -> str:
    if value not in META_COLUMNS:
        raise ValueError(f"unsupported metadata column: {value!r}")
    return "[" + value.replace("]", "]]" ) + "]"


def qn(value: Any) -> str:
    return "N'" + str(value).replace("'", "''") + "'"


def qs(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def sqlv(value: Any, text: bool = True) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return qn(value) if text else qs(value)


def base_type(value: str) -> str:
    return re.sub(r"\s+IDENTITY\([^)]*\)$", "", value, flags=re.I).lower()


def meta_type(field: dict[str, Any]) -> str:
    expected = "D" if base_type(str(field.get("sql", ""))) in {"date", "datetime", "datetime2"} else "S"
    explicit = field.get("meta_type") or field.get("type")
    if explicit is not None and str(explicit).strip().upper() != expected:
        raise ValueError(
            f"{field.get('name', '<unknown>')}: metadata type must be {expected} "
            "for its confirmed physical SQL type"
        )
    return expected


def expected_control(field_name: str) -> str:
    return "S" if str(field_name).upper().endswith("_PJLX") else "E"


def control(field: dict[str, Any], mt: str) -> str:
    expected = expected_control(field.get("name", ""))
    value = field.get("control")
    if value is None:
        return expected
    normalized = str(value).strip().upper()
    if normalized != expected:
        raise ValueError(
            f"{field.get('name', '<unknown>')}: new metadata control must be {expected}; "
            "do not infer special controls from SQL type"
        )
    return normalized


def flag(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n", ""}:
        return False
    raise ValueError(f"metadata flag must be boolean-like, got {value!r}")


def validate_field(field: dict[str, Any], table: str, index: int) -> dict[str, Any]:
    name = field.get("name")
    if not name or not IDENT_RE.fullmatch(str(name)):
        raise ValueError(f"{table}.fields[{index}].name is unsafe or missing")
    sql = str(field.get("sql", ""))
    if not TYPE_RE.fullmatch(sql):
        raise ValueError(f"{table}.{name}: unsupported sql type {sql!r}")
    out = dict(field)
    out["name"] = name
    out["sql"] = sql
    out["meta_type"] = meta_type(out)
    out["control"] = control(out, out["meta_type"])
    if not out.get("pk") and not out.get("label"):
        raise ValueError(f"{table}.{name}: label is required")
    if out.get("metadata", {}).get("标识") not in (None, ""):
        raise ValueError(f"{table}.{name}: SYS_TbColumn 标识 must be NULL")
    return out


def normalize(contract: dict[str, Any]) -> dict[str, Any]:
    required = ["expected_database", "expected_server", "bill_name", "form_kind", "header", "detail", "route", "metadata", "bdjb", "workspace"]
    missing = [x for x in required if x not in contract]
    if missing:
        raise ValueError("missing contract keys: " + ", ".join(missing))
    if contract["form_kind"] not in FORM_KINDS:
        raise ValueError("unsupported form_kind")
    menu_rows = contract.get("sysmenu") or required_sysmenu_rows(str(contract["bill_name"]))
    expected_menu = required_sysmenu_rows(str(contract["bill_name"]))
    for expected in expected_menu:
        matches = [row for row in menu_rows if row.get("sysmenu_buttonname") == expected["sysmenu_buttonname"]]
        if len(matches) != 1:
            raise ValueError(
                f"sysmenu must contain exactly one required button: {expected['sysmenu_buttonname']}"
            )
        actual = matches[0]
        for key, value in expected.items():
            if actual.get(key) != value:
                raise ValueError(
                    f"sysmenu {expected['sysmenu_buttonname']} has non-reference {key}; "
                    "copy the fixed Sales Order button parameters"
                )
    contract["sysmenu"] = menu_rows
    schema = str(contract.get("schema", "dbo"))
    if not IDENT_RE.fullmatch(schema):
        raise ValueError("unsafe schema")
    tables: dict[str, list[dict[str, Any]]] = {}
    for role in ("header", "detail"):
        spec = contract[role]
        table = spec.get("table")
        if not table or not IDENT_RE.fullmatch(str(table)):
            raise ValueError(f"{role}.table is unsafe or missing")
        fields = spec.get("fields") or []
        if not fields:
            raise ValueError(f"{role}.fields must not be empty")
        normalized = [validate_field(f, table, i) for i, f in enumerate(fields)]
        names = [f["name"] for f in normalized]
        if len(set(names)) != len(names):
            raise ValueError(f"{role}: duplicate field")
        if not any(f.get("pk") for f in normalized):
            raise ValueError(f"{role}: at least one primary-key field is required")
        tables[role] = normalized
        spec["fields"] = normalized
    route = contract["route"]
    route["format"] = normalize_iobdzd_format(route.get("format"))
    for key in ("bh", "htable", "ftable", "vkey", "byzd"):
        if not route.get(key):
            raise ValueError(f"route.{key} is required")
    if str(route["htable"]) != contract["header"]["table"] or str(route["ftable"]) != contract["detail"]["table"]:
        raise ValueError("route htable/ftable must match physical tables")
    header_names = {f["name"] for f in tables["header"]}
    detail_names = {f["name"] for f in tables["detail"]}
    if route["vkey"] not in header_names:
        raise ValueError("route.vkey must be a header field")
    if any(x.strip() not in header_names for x in str(route["byzd"]).split(",") if x.strip()):
        raise ValueError("route.byzd contains a missing header field")
    rel = contract["detail"].get("foreign_key") or {}
    for key in ("field", "references_field"):
        if not rel.get(key):
            raise ValueError(f"detail.foreign_key.{key} is required")
    if rel["field"] not in detail_names or rel.get("references_table") != contract["header"]["table"] or rel["references_field"] not in header_names:
        raise ValueError("detail.foreign_key does not match header/detail fields")

    md = contract["metadata"]
    rid_strategy = md.get("rid_strategy") or "runtime-max-plus-offset"
    if rid_strategy != "runtime-max-plus-offset":
        raise ValueError("metadata.rid_strategy must be runtime-max-plus-offset")
    md["rid_strategy"] = rid_strategy
    source = md.get("layout_source") or {}
    audit = md.get("audit") or {}
    if not source.get("reference_bill_name"):
        raise ValueError("metadata.layout_source.reference_bill_name is required")
    try:
        browse_button_width = int(source.get("browse_button_width", DEFAULT_BROWSE_BUTTON_WIDTH))
    except (TypeError, ValueError) as exc:
        raise ValueError("metadata.layout_source.browse_button_width must be an integer") from exc
    if browse_button_width <= 0:
        raise ValueError("metadata.layout_source.browse_button_width must be positive")
    # Keep the measured control metric in the normalized contract so generated
    # verification and a rerun use the same footprint evidence.
    source["browse_button_width"] = browse_button_width
    md["layout_source"] = source
    audit_geometry = ("left", "top", "width", "height", "bottom", "min_header_width", "natural_gap")
    if not audit.get("field") or any(key not in audit for key in audit_geometry):
        raise ValueError("metadata.audit.field and complete audit geometry are required")
    if any(int(audit[key]) < 0 for key in audit_geometry):
        raise ValueError("metadata.audit geometry cannot be negative")
    if int(audit["width"]) <= 0 or int(audit["height"]) <= 0 or int(audit["bottom"]) <= 0 or int(audit["min_header_width"]) <= 0:
        raise ValueError("metadata.audit width/height/bottom/min_header_width must be positive")
    if int(audit["natural_gap"]) < MIN_LAYOUT_GAP:
        raise ValueError(f"metadata.audit.natural_gap must be at least {MIN_LAYOUT_GAP} coordinate units")
    if int(audit["top"]) + int(audit["height"]) != int(audit["bottom"]):
        raise ValueError("metadata.audit.bottom must equal top + height")
    maintain = md.get("maintain_fields") or []
    query = md.get("query_fields") or []
    if not maintain or not query:
        raise ValueError("metadata.maintain_fields and query_fields must be complete")
    allowed = {("header", f["name"]) for f in tables["header"]} | {("detail", f["name"]) for f in tables["detail"]}
    for kind, rows in (("maintain_fields", maintain), ("query_fields", query)):
        seen: set[tuple[str, str]] = set()
        for row in rows:
            pair = (str(row.get("table_role")), str(row.get("field")))
            if pair not in allowed:
                raise ValueError(f"metadata.{kind} contains an unknown field: {pair}")
            if pair in seen:
                raise ValueError(f"metadata.{kind} contains duplicate field: {pair}")
            seen.add(pair)
            field = next(f for f in tables[pair[0]] if f["name"] == pair[1])
            expected_type = str(row.get("type") or field["meta_type"]).strip().upper()
            if expected_type != field["meta_type"]:
                raise ValueError(
                    f"metadata.{kind} {pair}: metadata type must be {field['meta_type']} "
                    "for its confirmed physical SQL type"
                )
            declared_control = str(row.get("control") or field["control"]).strip().upper()
            if row.get("标识") not in (None, ""):
                raise ValueError("SYS_TbColumn 标识 must remain NULL")
            required_control = expected_control(field["name"])
            if declared_control != required_control:
                raise ValueError(
                    f"metadata.{kind} {pair}: new metadata control must be {required_control}; "
                    "do not infer special controls from SQL type"
                )
            # Keep generated SQL deterministic even when a reviewed contract
            # spells the fixed D/S/E values with different casing.
            row["type"] = field["meta_type"]
            row["control"] = required_control
            try:
                po = int(row.get("po", 1 if pair[0] == "header" else 2))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"metadata.{kind} {pair}: PO must be an integer") from exc
            if po <= 0:
                raise ValueError(f"metadata.{kind} {pair}: PO must be positive")
            if kind == "query_fields":
                # 查询页是单一 PO 分组的扁平网格，不允许表头锚点行。
                row["po"] = 1
                row["header"] = 0
            else:
                row["po"] = po
                row["control"] = required_control
            row["column_width"] = resolve_column_width(
                field,
                row,
                flag(row.get("visible"), not field.get("identity", False)),
            )
            row["primary_key"] = flag(row.get("primary_key"), bool(field.get("pk")))
            # A physical identity/primary key is not a business key by default.
            row["key_field"] = flag(row.get("key_field"), False)
            for flag_name in ("visible", "required", "readonly"):
                if flag_name in row and row[flag_name] is None:
                    raise ValueError(f"metadata.{kind} {pair}: {flag_name} must be explicit")

        groups: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            group = int(row["po"])
            groups.setdefault(group, []).append(row)
        for po, members in groups.items():
            primary_count = sum(1 for row in members if row["primary_key"])
            if primary_count != 1:
                raise ValueError(
                    f"metadata.{kind} PO={po}: exactly one 主键=1 is required, "
                    f"got {primary_count}"
                )
            key_count = sum(1 for row in members if row["key_field"])
            if key_count > 1:
                raise ValueError(
                    f"metadata.{kind} PO={po}: at most one 关键字段=1 is allowed, "
                    f"got {key_count}"
                )
        renumber_metadata_orders(rows)

    query_aliases = [
        str(row.get("display_name") or next(
            f for f in tables[str(row["table_role"])] if f["name"] == row["field"]
        ).get("label") or row["field"])
        for row in query
    ]
    if len(query_aliases) != len(set(query_aliases)):
        raise ValueError("metadata.query_fields contains duplicate display aliases")
    query_labels = [
        str(row.get("label") or next(
            f for f in tables[str(row["table_role"])] if f["name"] == row["field"]
        ).get("label") or row["field"])
        for row in query
    ]
    if len(query_labels) != len(set(query_labels)):
        raise ValueError(
            "metadata.query_fields contains duplicate label names; "
            "query page 标签名 must be unique within the single PO group"
        )
    query_key_count = sum(1 for row in query if row["key_field"])
    if query_key_count != 1:
        raise ValueError(
            "metadata.query_fields must contain exactly one 关键字段=1, "
            f"got {query_key_count}"
        )
    audit_field = next((f for f in tables["header"] if f["name"] == str(audit["field"])), None)
    if audit_field is None:
        raise ValueError("metadata.audit.field must be a header field")
    if audit_field["meta_type"] != "S" or audit_field["control"] != "E":
        raise ValueError("metadata.audit.field must use S/E metadata contract")
    audit_rows = [x for x in maintain if str(x.get("table_role")) == "header" and str(x.get("field")) == str(audit["field"])]
    if len(audit_rows) != 1:
        raise ValueError("audit field must appear exactly once in header maintain_fields")
    audit_row = audit_rows[0]
    for key in ("left", "top", "width", "height"):
        if int(audit_row.get(key, 0)) != int(audit[key]):
            raise ValueError(f"audit field {key} does not match metadata.audit geometry")
    for row in maintain:
        if row.get("table_role") != "header" or not flag(row.get("visible"), True):
            continue
        try:
            left = int(row.get("left", 0))
            top = int(row.get("top", 0))
            width = int(row.get("width", 1200))
            height = int(row.get("height", 22))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"metadata.maintain_fields {row.get('field')}: header geometry must be integers"
            ) from exc
        if left < 0 or top < 0 or width <= 0 or height <= 0:
            raise ValueError(
                f"metadata.maintain_fields {row.get('field')}: header geometry must have non-negative coordinates and positive dimensions"
            )
    for row in maintain:
        if row.get("table_role") != "header" or not flag(row.get("visible"), True):
            continue
        help_value = row.get("help")
        if help_value is None or not str(help_value).strip():
            continue
        try:
            outer_width = int(row.get("width", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"metadata.maintain_fields {row.get('field')}: width must be an integer") from exc
        if outer_width <= browse_button_width:
            raise ValueError(
                f"metadata.maintain_fields {row.get('field')}: width must exceed the "
                f"measured help browse-button width ({browse_button_width})"
            )
    ordinary_header_rows = [
        row for row in maintain
        if row.get("table_role") == "header"
        and flag(row.get("visible"), True)
        and not is_fixed_header_anchor(str(row.get("field")))
    ]
    audit_top = int(audit["top"])
    audit_bottom = int(audit["bottom"])
    same_row_ordinary = [row for row in ordinary_header_rows if int(row.get("top", 0)) == audit_top]
    earlier_rows = [
        row for row in ordinary_header_rows
        if int(row.get("top", 0)) < audit_top
        and int(row.get("top", 0)) + int(row.get("height", 22)) <= audit_top
    ]
    crossing_rows = [
        row for row in ordinary_header_rows
        if int(row.get("top", 0)) < audit_top
        and int(row.get("top", 0)) + int(row.get("height", 22)) > audit_top
    ]
    if crossing_rows:
        raise ValueError("ordinary header fields overlap the SHBZ row; adjust only the minimal row coordinate")
    if earlier_rows:
        last_header_bottom = max(
            int(row.get("top", 0)) + int(row.get("height", 22))
            for row in earlier_rows
        )
        measured_gap = audit_top - last_header_bottom
        if measured_gap != int(audit["natural_gap"]):
            raise ValueError(
                "metadata.audit.natural_gap must equal audit top minus the last "
                f"earlier non-fixed visible header bottom ({measured_gap} measured)"
            )
        if measured_gap < MIN_LAYOUT_GAP:
            raise ValueError(f"ordinary header fields must leave at least {MIN_LAYOUT_GAP} units before a wrapped audit row")
    if not same_row_ordinary and any(int(row.get("top", 0)) >= audit_bottom for row in ordinary_header_rows):
        raise ValueError("ordinary header fields cannot be placed below the wrapped SHBZ boundary")
    if any(
        int(x.get("top", 0)) + int(x.get("height", 0)) > audit_bottom
        for x in maintain
        if str(x.get("field")) != str(audit["field"])
        and x.get("table_role") == "header"
        and flag(x.get("visible"), True)
        and not is_fixed_header_anchor(str(x.get("field")))
    ):
        raise ValueError("header field crosses the audit control bottom boundary")
    if any(
        int(x.get("left", 0)) + int(x.get("width", 0)) > int(audit["min_header_width"])
        for x in maintain
        if x.get("table_role") == "header" and flag(x.get("visible"), True)
    ):
        raise ValueError("header field exceeds the audit-derived minimum header width")
    same_row_fields: dict[int, list[dict[str, Any]]] = {}
    for row in maintain:
        if row.get("table_role") != "header" or not flag(row.get("visible"), True):
            continue
        if not is_fixed_header_anchor(str(row.get("field"))):
            top = int(row.get("top", 0))
            same_row_fields.setdefault(top, []).append(row)
    if audit_row.get("visible", True):
        same_row_fields.setdefault(audit_top, []).append(audit_row)
    for top, members in same_row_fields.items():
        members.sort(key=lambda row: (int(row.get("left", 0)), int(row.get("order", 0))))
        previous: dict[str, Any] | None = None
        for row in members:
            left = int(row.get("left", 0))
            width = int(row.get("width", 1200))
            if width <= 0:
                raise ValueError(f"metadata header field {row.get('field')}: visible width must be positive")
            if previous is not None:
                previous_right = int(previous.get("left", 0)) + int(previous.get("width", 0))
                if left < previous_right:
                    raise ValueError(
                        f"metadata header fields {previous.get('field')} and {row.get('field')} overlap on row top={top}"
                    )
            previous = row
    if not (contract["bdjb"].get("rows") or contract["bdjb"].get("rules")):
        raise ValueError("bdjb.rows or bdjb.rules is required; do not guess lifecycle SQL")
    if not (contract["workspace"].get("rows")):
        raise ValueError("workspace.rows is required")
    contract["schema"] = schema
    contract["deployment_ready"] = True
    return contract


def draft_from_er(args: argparse.Namespace) -> dict[str, Any]:
    tables = parse_tables(args.er_svg)
    missing = [x for x in (args.header_table, args.detail_table) if x not in tables or not tables[x].get("fields")]
    if missing:
        raise ValueError("未从 ER 图解析到表或字段: " + ", ".join(missing))
    def convert(name: str, role: str) -> dict[str, Any]:
        fields = []
        for f in tables[name]["fields"]:
            fields.append({"name": f["name"], "label": f.get("label", ""), "sql": f["er_type"], "pk": bool(f.get("pk")), "nullable": not bool(f.get("pk"))})
        return {"table": name, "fields": fields}
    return {
        "source": str(args.er_svg), "expected_database": args.expected_database or "", "expected_server": args.expected_server or "",
        "schema": "dbo", "bill_name": args.bill_name, "form_kind": args.form_kind,
        "header": convert(args.header_table, "header"), "detail": convert(args.detail_table, "detail"),
        "route": {}, "metadata": {}, "bdjb": {}, "workspace": {}, "deployment_ready": False,
        "review_blockers": [
            "ER 图不能证明真实 SQL 类型、identity/主键策略、默认值和约束",
            "未确认 IOBDZD 编号、MARK、HVKey/FVKey、查询页和 PO 字段集",
            "未取得同版本有效单据的 SYS_TbColumn 审核坐标；禁止猜审核宽度/坐标",
            "未确认 BDJB 审核/撤审规则、工作区编号和动态角色列",
        ],
    }


def table_ref(c: dict[str, Any], role: str) -> str:
    return f"{qi(c['schema'])}.{qi(c[role]['table'])}"


def render_columns(spec: dict[str, Any]) -> str:
    lines = []
    for f in spec["fields"]:
        nullable = "NOT NULL" if f.get("pk") or not f.get("nullable", True) else "NULL"
        default = f" DEFAULT {f['default']}" if f.get("default") else ""
        identity = " IDENTITY(1,1)" if f.get("identity") and "identity" not in f["sql"].lower() else ""
        lines.append(f"        {qi(f['name'])} {f['sql']}{identity} {nullable}{default}")
    pk = [f["name"] for f in spec["fields"] if f.get("pk")]
    lines.append(f"        CONSTRAINT {qi('PK_' + spec['table'])} PRIMARY KEY CLUSTERED ({', '.join(qi(x) for x in pk)})")
    for i, unique_fields in enumerate(spec.get("unique_fields", []), 1):
        if not unique_fields:
            continue
        lines.append(f"        CONSTRAINT {qi('UQ_' + spec['table'] + '_' + str(i))} UNIQUE NONCLUSTERED ({', '.join(qi(x) for x in unique_fields)})")
    return ",\n".join(lines)


def render_header(c: dict[str, Any], xact: bool = False) -> str:
    return "SET ANSI_NULLS ON;\nSET QUOTED_IDENTIFIER ON;\nSET NOCOUNT ON;\n" + ("SET XACT_ABORT ON;\n" if xact else "") + f"IF DB_NAME() <> {qn(c['expected_database'])} THROW 54000,N'目标数据库不匹配。',1;\nIF @@SERVERNAME <> {qn(c['expected_server'])} THROW 54001,N'目标实例不匹配。',1;\n"


def blocked(c: dict[str, Any], artifact: str) -> str:
    reasons = "\n".join("--   " + x for x in c.get("review_blockers", ["contract is not deployment-ready"]))
    return f"""/* {artifact} is intentionally blocked until the contract is complete.
{reasons}
*/
THROW 54090,N'复杂表单契约未完成，拒绝生成可部署脚本。',1;
"""


def render_schema(c: dict[str, Any]) -> str:
    """Render a non-executable schema review artifact.

    This file is intentionally comments-only.  It is useful for review and
    diffing, but must never be accidentally piped to sqlcmd as a deployment
    script; only ``forward.sql`` owns physical DDL.
    """
    lines = [
        "/* Review-only physical schema draft. This file is comments-only and must not be deployed.",
        "   Types, keys, and constraints require target DB evidence.",
        "   Use forward.sql for the authorized transactional deployment. */",
    ]
    for role in ("header", "detail"):
        spec = c[role]
        lines.append(f"-- {role}: {spec['table']}")
        ddl = "\n".join([f"CREATE TABLE [dbo].[{spec['table']}] (", render_columns(spec), ");"])
        lines.extend("-- " + ddl_line for ddl_line in ddl.splitlines())
        lines.append("")
    rel = c.get("detail", {}).get("foreign_key")
    if rel:
        lines.append(
            f"-- ALTER TABLE [dbo].[{c['detail']['table']}] ADD CONSTRAINT "
            f"[FK_{c['detail']['table']}_{rel.get('field','Detail')}] FOREIGN KEY "
            f"([{rel.get('field','')}]) REFERENCES [dbo].[{c['header']['table']}]"
            f"([{rel.get('references_field','')}]);"
        )
    return "\n".join(lines) + "\n"


def render_preflight(c: dict[str, Any]) -> str:
    lines = ["/* Stage 1: read-only identity and contract preflight. */", "SET NOCOUNT ON;", "SELECT DB_NAME() AS CurrentDatabase, @@SERVERNAME AS CurrentServer;", f"IF DB_NAME() <> {qn(c.get('expected_database',''))} THROW 54100,N'数据库不匹配。',1;" if c.get("expected_database") else "-- expected_database 未确认。"]
    for role in ("header", "detail"):
        table = c[role]["table"]
        lines += [f"SELECT N'{role}' AS TableRole,c.name,TYPE_NAME(c.user_type_id) AS DataType,c.max_length,c.is_nullable,c.column_id", "FROM sys.columns c", f"WHERE c.object_id=OBJECT_ID(N'dbo.{table}',N'U') ORDER BY c.column_id;", ""]
    lines += ["IF OBJECT_ID(N'dbo.IOBDZD',N'U') IS NULL THROW 54101,N'IOBDZD 缺失。',1;", "IF OBJECT_ID(N'dbo.SYS_TbColumn',N'U') IS NULL THROW 54102,N'SYS_TbColumn 缺失。',1;", "IF OBJECT_ID(N'dbo.sysmenu',N'U') IS NULL THROW 54103,N'sysmenu 缺失。',1;", f"SELECT IOBDZD_BH,IOBDZD_MC,IOBDZD_MARK,IOBDZD_FORMAT,IOBDZD_BILLNO,IOBDZD_BascData,IOBDZD_CurMonth,IOBDZD_ModifyDate,IOBDZD_HTABLE,IOBDZD_FTABLE,IOBDZD_HVKEY,IOBDZD_FVKEY FROM dbo.IOBDZD WHERE IOBDZD_MC IN ({qn(c.get('bill_name',''))},{qn(str(c.get('bill_name',''))+'查询')});", f"SELECT * FROM dbo.SYS_TbColumn WHERE 表名 IN ({qn(c.get('bill_name',''))},{qn(str(c.get('bill_name',''))+'查询')}) ORDER BY 表名,TRY_CONVERT(int,PO),顺序,字段名;", f"SELECT * FROM dbo.sysmenu WHERE sysmenu_bdmc={qn(c.get('bill_name',''))} ORDER BY sysmenu_topfloor,sysmenu_submenu,sysmenu_xh,sysmenu_buttonname;", "SELECT N'PREFLIGHT_REVIEW_COMPLETE' AS Status;"]
    return "\n".join(lines) + "\n"


def render_reference_evidence(c: dict[str, Any]) -> str:
    ref = c.get("metadata", {}).get("layout_source", {}).get("reference_bill_name")
    if not ref:
        return "/* No reference bill supplied.审核坐标、宽度、底边不能推测。 */\nTHROW 54110,N'缺少同版本有效参考单据。',1;\n"
    r = qn(ref)
    return f"""/* Stage 1b: read-only evidence for the same-version reference bill. */
SET NOCOUNT ON;
SELECT DB_NAME() AS CurrentDatabase,@@SERVERNAME AS CurrentServer;
SELECT * FROM dbo.IOBDZD WHERE IOBDZD_MC={r};
SELECT * FROM dbo.SYS_TbColumn WHERE 表名={r} ORDER BY TRY_CONVERT(int,PO),顺序,字段名;
SELECT * FROM dbo.SYS_TbColumn WHERE 表名={r} AND (字段名 LIKE N'%_SHBZ' OR 字段名 LIKE N'%_ZDR' OR 字段名 LIKE N'%_SHR' OR 字段名 LIKE N'%_ZY') ORDER BY TRY_CONVERT(int,PO),顺序;
-- CBCGPEdit default: EnableBrowseButton(true) reserves 20 units;
-- replace this evidence with max(20,imageWidth+8) when a custom image is active.
SELECT N'browse-button-width' AS Evidence, 20 AS DefaultWidth;
SELECT 字段名,帮助,左坐标,顶坐标,宽度,高度,左坐标+宽度 AS RightEdge,顶坐标+高度 AS BottomEdge
FROM dbo.SYS_TbColumn
WHERE 表名={r} AND PO=N'1' AND 显示=1 AND NULLIF(LTRIM(RTRIM(帮助)),N'') IS NOT NULL
ORDER BY 顺序,字段名;
SELECT * FROM dbo.BDJB WHERE BDJB_PJLX={r} ORDER BY BDJB_BH;
SELECT * FROM dbo.SYSWSPACE WHERE SYSWSPACE_MC={r} OR SYSWSPACE_MC LIKE {r}+N'%';
"""

def meta_rows(c: dict[str, Any]) -> list[dict[str, Any]]:
    return list(c["metadata"]["maintain_fields"])


def renumber_metadata_orders(rows: list[dict[str, Any]]) -> None:
    """Sort metadata deterministically and assign 1-based order per PO.

    Contracts may carry stale, zero-based, or duplicated order values.  They
    are used only as a stable sort hint; the generated runtime value is always
    normalized to 1..n independently for each PO group.
    """
    sortable: list[tuple[int, int, int, str, dict[str, Any]]] = []
    for index, row in enumerate(rows):
        raw_order = row.get("order")
        if raw_order in (None, ""):
            requested_order = index + 1
        else:
            try:
                requested_order = int(raw_order)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"metadata field {row.get('field', '<unknown>')}: order must be an integer"
                ) from exc
        sortable.append((int(row["po"]), requested_order, index, str(row["field"]), row))
    sortable.sort(key=lambda item: item[:4])
    counters: dict[int, int] = {}
    rows[:] = []
    for po, _requested_order, _index, _field_name, row in sortable:
        counters[po] = counters.get(po, 0) + 1
        row["order"] = counters[po]
        rows.append(row)


def meta_tuple(c: dict[str, Any], row: dict[str, Any], index: int, visible_name: str | None = None, rid_offset: int | None = None) -> str:
    role = row["table_role"]
    field = next(f for f in c[role]["fields"] if f["name"] == row["field"])
    mt = row.get("type") or field["meta_type"]
    ctl = row.get("control") or field["control"]
    visible = flag(row.get("visible"), not field.get("identity", False))
    label = row.get("label") or field.get("label") or field["name"]
    column_width = int(row.get("column_width", resolve_column_width(field, row, visible)))
    values: list[Any] = [
        visible_name or c["bill_name"], str(row.get("po", 1 if role == "header" else 2)), field["name"], int(flag(row.get("primary_key"), bool(field.get("pk")))), row.get("rmark"), row.get("display_name") or field.get("label") or field["name"], label, 0, int(visible), column_width, int(row.get("order", index + 1)), 0, 0, int(row.get("readonly", bool(field.get("identity")))), int(row.get("header", role == "header")), row.get("color"), 1, 1, 1, int(row.get("filter", 0)), int(row.get("required", not field.get("nullable", True))), int(row.get("merge", 1)), int(row.get("align", 7)), int(row.get("switch", 0)), row.get("glzd"), row.get("lmark"), mt, row.get("help"), None, row.get("default_value"), row.get("pipe"), int(flag(row.get("key_field"), False)), int(row.get("left", 0)), int(row.get("top", 40 + index * 30)), int(row.get("width", 1200)), int(row.get("height", 22)), "1", int(row.get("priority", 0)), row.get("left_align"), row.get("right_align"), row.get("top_align"), row.get("bottom_align"), ctl, ("__SQL__", f"@RIDBase + {rid_offset if rid_offset is not None else index}"),
    ]
    rendered = []
    for i, value in enumerate(values):
        if i == 28:  # 标识 is a hard invariant
            value = None
        if isinstance(value, tuple) and value and value[0] == "__SQL__":
            rendered.append(value[1])
        else:
            rendered.append("NULL" if value is None else (qn(value) if i in META_TEXT else str(value)))
    return "(" + ",".join(rendered) + ")"


def render_forward(c: dict[str, Any]) -> str:
    if not c.get("deployment_ready"):
        return blocked(c, "forward.sql")
    s = render_header(c, True)
    h, d = table_ref(c, "header"), table_ref(c, "detail")
    rel = c["detail"]["foreign_key"]
    meta_cols = ",".join(qmeta(x) for x in META_COLUMNS)
    maintain = meta_rows(c)
    query = list(c["metadata"]["query_fields"])
    tuples = ",\n".join("    " + meta_tuple(c, row, i, c["bill_name"], i) for i, row in enumerate(maintain))
    query_tuples = ",\n".join("    " + meta_tuple(c, dict(row, po=1, header=0), i, c["bill_name"] + "查询", len(maintain) + i) for i, row in enumerate(query))
    menu_cols = ["sysmenu_bdmc", "sysmenu_topfloor", "sysmenu_xh", "sysmenu_buttonname", "sysmenu_icon", "sysmenu_submenu", "sysmenu_pmenu", "sysmenu_trimenu", "sysmenu_uid"]
    menu_tuples = ",\n".join(
        "    (" + ",".join(sqlv(row[key], text=not isinstance(row[key], (int, float, bool))) for key in menu_cols) + ")"
        for row in c["sysmenu"]
        if row.get("sysmenu_buttonname") in {item[0] for item in REQUIRED_SYSMENU_BUTTONS}
    )
    route = c["route"]
    s += f"""BEGIN TRANSACTION;
BEGIN TRY
    DECLARE @RIDBase int = ISNULL((SELECT MAX(TRY_CONVERT(int,RID)) FROM dbo.SYS_TbColumn),0) + 1;
    IF @RIDBase <= 0 THROW 54120,N'无法分配正整数 RID。',1;
    CREATE TABLE {h} ({render_columns(c['header'])});
    CREATE TABLE {d} ({render_columns(c['detail'])}, CONSTRAINT {qi('FK_'+c['detail']['table']+'_'+rel['field'])} FOREIGN KEY ({qi(rel['field'])}) REFERENCES {h}({qi(rel['references_field'])}));
    INSERT dbo.IOBDZD (IOBDZD_BH,IOBDZD_MARK,IOBDZD_MC,IOBDZD_Type,IOBDZD_IoFlag,IOBDZD_HTABLE,IOBDZD_FTABLE,IOBDZD_HVKEY,IOBDZD_FVKEY,IOBDZD_TAB1,IOBDZD_TAB2,IOBDZD_TAB3,IOBDZD_BILLNO,IOBDZD_FORMAT,IOBDZD_BZ)
    VALUES ({qn(route['bh'])},{qn(route.get('mark','1'))},{qn(c['bill_name'])},{qn(route.get('type',''))},{int(route.get('ioflag',0))},{qn(route['htable'])},{qn(route['ftable'])},{qn(route['vkey'])},{qn(route.get('fvkey',rel['field']))},{qn(route.get('tab1','表头'))},{qn(route.get('tab2','表体'))},{qn(route.get('tab3',''))},{qn(route.get('billno',''))},{qn(route['format'])},{qn(route.get('bz',''))});
    INSERT dbo.sysmenu ({','.join(qi(key) for key in menu_cols)}) VALUES
{menu_tuples};
    INSERT dbo.SYS_TbColumn ({meta_cols}) VALUES
{tuples};
    INSERT dbo.SYS_TbColumn ({meta_cols}) VALUES
{query_tuples};
    DECLARE @sql nvarchar(max);
    SELECT @sql=STUFF((SELECT N','+QUOTENAME(c.name)+N'=1' FROM sys.columns c WHERE c.object_id=OBJECT_ID(N'dbo.SYS_TbColumn') AND c.system_type_id=104 AND c.column_id>ISNULL((SELECT column_id FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.SYS_TbColumn') AND name=N'RID'),0) ORDER BY c.column_id FOR XML PATH(''),TYPE).value('.','nvarchar(max)'),1,1,N'');
    DECLARE @cmd nvarchar(max);
    IF NULLIF(@sql,N'') IS NOT NULL BEGIN SET @cmd=N'UPDATE dbo.SYS_TbColumn SET '+@sql+N' WHERE 表名 IN (@n,@q)'; EXEC sys.sp_executesql @cmd,N'@n nvarchar(100),@q nvarchar(100)',@n={qn(c['bill_name'])},@q={qn(c['bill_name']+'查询')}; END;
"""
    for row in c["bdjb"].get("rows", []):
        cols = list(row.keys())
        s += f"    INSERT dbo.BDJB ({','.join(qi(x) for x in cols)}) VALUES ({','.join(sqlv(row[x]) for x in cols)});\n"
    ws_rows = c["workspace"]["rows"]
    ws_cols = list(ws_rows[0].keys())
    ws_values = ",\n".join("        (" + ",".join(sqlv(row[x], text=not isinstance(row[x], (int,float,bool))) for x in ws_cols) + ")" for row in ws_rows)
    s += f"""    CREATE TABLE #NewWorkspace (SYSWSPACE_ID int NOT NULL);
    INSERT dbo.SYSWSPACE ({','.join(qi(x) for x in ws_cols)})
    OUTPUT inserted.SYSWSPACE_ID INTO #NewWorkspace(SYSWSPACE_ID)
    VALUES
{ws_values};
    SELECT @sql=STUFF((SELECT N','+QUOTENAME(c.name)+N'='+CASE WHEN c.system_type_id IN (167,175,231,239) THEN N'N''1''' ELSE N'1' END FROM sys.columns c WHERE c.object_id=OBJECT_ID(N'dbo.SYSWSPACE') AND (c.name=N'admin' OR (c.system_type_id=104 AND c.column_id>ISNULL((SELECT column_id FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.SYSWSPACE') AND name=N'admin'),0))) AND c.name<>N'SYSWSPACE_ID' ORDER BY c.column_id FOR XML PATH(''),TYPE).value('.','nvarchar(max)'),1,1,N'');
    IF NULLIF(@sql,N'') IS NOT NULL BEGIN SET @cmd=N'UPDATE w SET '+@sql+N' FROM dbo.SYSWSPACE w JOIN #NewWorkspace n ON n.SYSWSPACE_ID=w.SYSWSPACE_ID'; EXEC sys.sp_executesql @cmd; END;
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT N'FORWARD_COMPLETE' AS DeployStatus;
"""
    return s


def runtime_meta(c: dict[str, Any], row: dict[str, Any], visible_name: str, rid_offset: int) -> dict[str, Any]:
    role = row["table_role"]
    field = next(f for f in c[role]["fields"] if f["name"] == row["field"])
    visible = int(row.get("visible", not field.get("identity", False)))
    column_width = int(row.get("column_width", resolve_column_width(field, row, bool(visible))))
    return {
        "表名": visible_name,
        "字段名": field["name"],
        "PO": str(row.get("po", 1 if role == "header" else 2)),
        "顺序": int(row.get("order", rid_offset + 1)),
        "显示名": row.get("display_name") or field.get("label") or field["name"],
        "标签名": row.get("label") or field.get("label") or field["name"],
        "类型": row.get("type") or field["meta_type"],
        "控件": row.get("control") or field["control"],
        "显示": visible,
        "列宽": column_width,
        "标签最小宽度": label_column_width(row.get("label") or field.get("label") or field["name"]),
        "必填": int(row.get("required", not field.get("nullable", True))),
        "只读": int(row.get("readonly", bool(field.get("identity")))),
        "左坐标": int(row.get("left", 0)),
        "顶坐标": int(row.get("top", 40 + rid_offset * 30)),
        "宽度": int(row.get("width", 1200)),
        "高度": int(row.get("height", 22)),
        "RIDOffset": rid_offset,
    }


def runtime_meta_values(c: dict[str, Any]) -> str:
    rows = [
        runtime_meta(c, row, c["bill_name"], i)
        for i, row in enumerate(c["metadata"]["maintain_fields"])
    ]
    rows += [
        runtime_meta(c, dict(row, po=1, header=0), c["bill_name"] + "查询", len(c["metadata"]["maintain_fields"]) + i)
        for i, row in enumerate(c["metadata"]["query_fields"])
    ]
    return ",\n".join(
        "    (" + ",".join([
            qn(row["表名"]), qn(row["字段名"]), qn(row["PO"]), str(row["顺序"]), qn(row["显示名"]),
            qn(row["标签名"]), str(row["列宽"]), str(row["标签最小宽度"]), qn(row["类型"]), qn(row["控件"]), str(row["显示"]),
            str(row["必填"]), str(row["只读"]), str(row["左坐标"]), str(row["顶坐标"]),
            str(row["宽度"]), str(row["高度"]), str(row["RIDOffset"]),
        ]) + ")"
        for row in rows
    )


def render_verification(c: dict[str, Any]) -> str:
    if not c.get("deployment_ready"):
        return blocked(c, "verification.sql")
    h, d = table_ref(c, "header"), table_ref(c, "detail")
    audit = c["metadata"]["audit"]
    browse_button_width = int(c["metadata"]["layout_source"].get("browse_button_width", DEFAULT_BROWSE_BUTTON_WIDTH))
    relation = c["detail"]["foreign_key"]
    workspace_names = ",".join(qn(row["SYSWSPACE_MC"]) for row in c["workspace"]["rows"] if row.get("SYSWSPACE_MC") is not None)
    expected_values = runtime_meta_values(c)
    expected_total = len(c["metadata"]["maintain_fields"]) + len(c["metadata"]["query_fields"])
    menu_values = sysmenu_expected_values(c["bill_name"])
    return render_header(c) + f"""DECLARE @ExpectedSysMenu TABLE (
    sysmenu_buttonname nvarchar(100) NOT NULL, sysmenu_topfloor bit NOT NULL, sysmenu_xh nvarchar(100) NOT NULL,
    sysmenu_icon int NOT NULL, sysmenu_submenu bit NOT NULL, sysmenu_pmenu nvarchar(100) NOT NULL,
    sysmenu_trimenu bit NOT NULL, sysmenu_uid nvarchar(100) NOT NULL
);
INSERT @ExpectedSysMenu VALUES
{menu_values};
IF (SELECT COUNT(*) FROM dbo.sysmenu WHERE sysmenu_bdmc={qn(c['bill_name'])} AND sysmenu_buttonname IN (SELECT sysmenu_buttonname FROM @ExpectedSysMenu))<>7
    THROW 54229,N'主从单据必需的系统按钮不完整或重复。',1;
IF EXISTS
(
    SELECT e.sysmenu_buttonname
    FROM @ExpectedSysMenu e
    LEFT JOIN dbo.sysmenu m
      ON m.sysmenu_bdmc={qn(c['bill_name'])} AND m.sysmenu_buttonname=e.sysmenu_buttonname
    WHERE m.SYSMENU_ID IS NULL
       OR m.sysmenu_topfloor<>e.sysmenu_topfloor OR m.sysmenu_xh<>e.sysmenu_xh
       OR m.sysmenu_icon<>e.sysmenu_icon OR m.sysmenu_submenu<>e.sysmenu_submenu
       OR ISNULL(m.sysmenu_pmenu,N'')<>e.sysmenu_pmenu OR m.sysmenu_trimenu<>e.sysmenu_trimenu
       OR ISNULL(m.sysmenu_uid,N'')<>e.sysmenu_uid
)
    THROW 54230,N'系统按钮参数未按销售订单参考契约设置。',1;
DECLARE @ExpectedMeta TABLE (
    表名 nvarchar(100) NOT NULL, 字段名 nvarchar(128) NOT NULL, PO nvarchar(10) NOT NULL, 顺序 int NOT NULL,
    显示名 nvarchar(200) NOT NULL, 标签名 nvarchar(200) NOT NULL, 列宽 int NOT NULL, 标签最小宽度 int NOT NULL, 类型 nvarchar(20) NOT NULL,
    控件 nvarchar(20) NOT NULL, 显示 int NOT NULL, 必填 int NOT NULL, 只读 int NOT NULL,
    左坐标 int NOT NULL, 顶坐标 int NOT NULL, 宽度 int NOT NULL, 高度 int NOT NULL,
    RIDOffset int NOT NULL, PRIMARY KEY (表名,字段名)
);
INSERT @ExpectedMeta (表名,字段名,PO,顺序,显示名,标签名,列宽,标签最小宽度,类型,控件,显示,必填,只读,左坐标,顶坐标,宽度,高度,RIDOffset) VALUES
{expected_values};
IF OBJECT_ID(N'{c['schema']}.{c['header']['table']}',N'U') IS NULL THROW 54200,N'表头不存在。',1;
IF OBJECT_ID(N'{c['schema']}.{c['detail']['table']}',N'U') IS NULL THROW 54201,N'表体不存在。',1;
IF (SELECT COUNT(*) FROM dbo.IOBDZD WHERE IOBDZD_MC={qn(c['bill_name'])} AND IOBDZD_HTABLE={qn(c['header']['table'])} AND IOBDZD_FTABLE={qn(c['detail']['table'])})<>1 THROW 54202,N'IOBDZD 路由不唯一。',1;
IF (SELECT COUNT(*) FROM dbo.IOBDZD WHERE IOBDZD_MC={qn(c['bill_name'])} AND NULLIF(LTRIM(RTRIM(IOBDZD_FORMAT)),N'') IS NOT NULL AND IOBDZD_FORMAT={qn(c['route']['format'])})<>1 THROW 54234,N'IOBDZD_FORMAT 为空或与编号格式契约不一致。',1;
IF NOT EXISTS (SELECT 1 FROM sys.foreign_key_columns fkc JOIN sys.foreign_keys fk ON fk.object_id=fkc.constraint_object_id WHERE fkc.parent_object_id=OBJECT_ID(N'{c['schema']}.{c['detail']['table']}') AND fkc.referenced_object_id=OBJECT_ID(N'{c['schema']}.{c['header']['table']}') AND COL_NAME(fkc.parent_object_id,fkc.parent_column_id)={qn(relation['field'])} AND COL_NAME(fkc.referenced_object_id,fkc.referenced_column_id)={qn(relation['references_field'])}) THROW 54211,N'表头表体外键缺失。',1;
IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name'])})<>{len(meta_rows(c))} THROW 54203,N'SYS_TbColumn 维护页字段集不完整。',1;
IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name']+'查询')})<>{len(c['metadata']['query_fields'])} THROW 54208,N'SYS_TbColumn 查询页字段集不完整。',1;
IF (SELECT COUNT(*) FROM @ExpectedMeta)<>{expected_total} THROW 54212,N'生成的运行时元数据契约不完整。',1;
IF EXISTS (SELECT 1 FROM @ExpectedMeta WHERE 显示=1 AND 列宽<标签最小宽度) THROW 54232,N'生成的可见字段列宽不足以显示完整标签名。',1;
IF EXISTS (SELECT 1 FROM @ExpectedMeta e LEFT JOIN dbo.SYS_TbColumn m ON m.表名=e.表名 AND m.字段名=e.字段名 WHERE m.字段名 IS NULL) THROW 54213,N'维护页或查询页存在悬空或错误字段。',1;
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名 IN ({qn(c['bill_name'])},{qn(c['bill_name']+'查询')}) AND 标识 IS NOT NULL AND LTRIM(RTRIM(标识))<>N'') THROW 54204,N'标识非空，可能触发 FF_BS。',1;
IF EXISTS (SELECT 表名,TRY_CONVERT(int,PO) FROM dbo.SYS_TbColumn WHERE 表名 IN ({qn(c['bill_name'])},{qn(c['bill_name']+'查询')}) GROUP BY 表名,TRY_CONVERT(int,PO) HAVING MIN(TRY_CONVERT(int,顺序))<>1 OR MAX(TRY_CONVERT(int,顺序))<>COUNT(*) OR COUNT(DISTINCT TRY_CONVERT(int,顺序))<>COUNT(*) OR SUM(CASE WHEN TRY_CONVERT(int,顺序) IS NULL THEN 1 ELSE 0 END)>0) THROW 54225,N'每个表名与 PO 的顺序必须从 1 连续编号。',1;
IF EXISTS (SELECT 表名,TRY_CONVERT(int,PO) FROM dbo.SYS_TbColumn WHERE 表名 IN ({qn(c['bill_name'])},{qn(c['bill_name']+'查询')}) GROUP BY 表名,TRY_CONVERT(int,PO) HAVING SUM(CASE WHEN 主键=1 THEN 1 ELSE 0 END)<>1) THROW 54220,N'每个表名与 PO 只能有一个主键。',1;
IF EXISTS (SELECT 表名,TRY_CONVERT(int,PO) FROM dbo.SYS_TbColumn WHERE 表名 IN ({qn(c['bill_name'])},{qn(c['bill_name']+'查询')}) GROUP BY 表名,TRY_CONVERT(int,PO) HAVING SUM(CASE WHEN 关键字段=1 THEN 1 ELSE 0 END)>1) THROW 54221,N'每个表名与 PO 只能有一个关键字段。',1;
IF (SELECT SUM(CASE WHEN 关键字段=1 THEN 1 ELSE 0 END) FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name']+'查询')})<>1 THROW 54222,N'查询页只能有一个关键字段。',1;
IF EXISTS (SELECT 显示名 FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name']+'查询')} GROUP BY 显示名 HAVING COUNT(*)>1) THROW 54223,N'查询页显示别名重复，派生表无法生成。',1;
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名 IN ({qn(c['bill_name'])},{qn(c['bill_name']+'查询')}) AND COALESCE(控件,N'')<>CASE WHEN RIGHT(UPPER(字段名),5)=N'_PJLX' THEN N'S' ELSE N'E' END) THROW 54224,N'新生成元数据控件规则不完整：普通字段为 E，PJLX 为 S。',1;
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn m JOIN @ExpectedMeta e ON e.表名=m.表名 AND e.字段名=m.字段名 WHERE COALESCE(m.类型,N'')<>e.类型) THROW 54231,N'日期字段必须为 D，其他新生成字段必须为 S。',1;
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn m JOIN @ExpectedMeta e ON e.表名=m.表名 AND e.字段名=m.字段名 WHERE e.显示=1 AND (m.列宽 IS NULL OR TRY_CONVERT(int,m.列宽)<e.标签最小宽度)) THROW 54233,N'可见字段列宽不足以显示完整标签名。',1;
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名 IN ({qn(c['bill_name'])},{qn(c['bill_name']+'查询')}) AND (RID IS NULL OR TRY_CONVERT(int,RID)<=0)) THROW 54205,N'RID 为空或不是正整数，客户端控件初始化会失败。',1;
IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名 IN ({qn(c['bill_name'])},{qn(c['bill_name']+'查询')}))<>(SELECT COUNT(DISTINCT TRY_CONVERT(int,RID)) FROM dbo.SYS_TbColumn WHERE 表名 IN ({qn(c['bill_name'])},{qn(c['bill_name']+'查询')})) THROW 54215,N'RID 在维护页或查询页中重复。',1;
DECLARE @RuntimeRIDBase int=(SELECT MIN(TRY_CONVERT(int,RID)) FROM dbo.SYS_TbColumn WHERE 表名 IN ({qn(c['bill_name'])},{qn(c['bill_name']+'查询')}));
IF @RuntimeRIDBase IS NULL OR @RuntimeRIDBase<=0 THROW 54216,N'RID 起始值无效。',1;
IF EXISTS (SELECT 1 FROM @ExpectedMeta e JOIN dbo.SYS_TbColumn m ON m.表名=e.表名 AND m.字段名=e.字段名 WHERE TRY_CONVERT(int,m.PO)<>TRY_CONVERT(int,e.PO) OR TRY_CONVERT(int,m.顺序)<>e.顺序 OR COALESCE(m.显示名,N'')<>e.显示名 OR COALESCE(m.标签名,N'')<>e.标签名 OR m.列宽 IS NULL OR TRY_CONVERT(int,m.列宽)<>e.列宽 OR COALESCE(m.类型,N'')<>e.类型 OR COALESCE(m.控件,N'')<>e.控件 OR TRY_CONVERT(int,m.显示)<>e.显示 OR TRY_CONVERT(int,m.必填)<>e.必填 OR TRY_CONVERT(int,m.只读)<>e.只读 OR TRY_CONVERT(int,m.左坐标)<>e.左坐标 OR TRY_CONVERT(int,m.顶坐标)<>e.顶坐标 OR TRY_CONVERT(int,m.宽度)<>e.宽度 OR TRY_CONVERT(int,m.高度)<>e.高度) THROW 54217,N'基础元数据不满足客户端运行时字段契约。',1;
IF (SELECT COUNT(*) FROM dbo.v_tbcolumn WHERE 表名 IN ({qn(c['bill_name'])},{qn(c['bill_name']+'查询')}))<>{expected_total} THROW 54218,N'v_tbcolumn 运行时投影字段集不完整。',1;
IF EXISTS (SELECT 1 FROM @ExpectedMeta e LEFT JOIN dbo.v_tbcolumn v ON v.表名=e.表名 AND v.字段名=e.字段名 WHERE v.字段名 IS NULL OR v.RID IS NULL OR TRY_CONVERT(int,v.RID)<=0 OR TRY_CONVERT(int,v.顺序)<>e.顺序 OR COALESCE(v.类型,N'')<>e.类型 OR COALESCE(v.控件,N'')<>e.控件 OR COALESCE(v.标签名,N'')<>e.标签名 OR v.列宽 IS NULL OR TRY_CONVERT(int,v.列宽)<>e.列宽 OR TRY_CONVERT(int,v.显示)<>e.显示 OR TRY_CONVERT(int,v.必填)<>e.必填 OR TRY_CONVERT(int,v.只读)<>e.只读) THROW 54219,N'v_tbcolumn 不满足客户端控件初始化读取契约。',1;
    IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name'])} AND 字段名={qn(audit['field'])} AND 顶坐标+高度>{int(audit['bottom'])}) THROW 54206,N'审核控件底边不符合契约。',1;
    IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name'])} AND 字段名={qn(audit['field'])} AND (左坐标<>{int(audit['left'])} OR 顶坐标<>{int(audit['top'])} OR 宽度<>{int(audit['width'])} OR 高度<>{int(audit['height'])})) THROW 54209,N'审核控件坐标或尺寸不符合契约。',1;
    DECLARE @BrowseButtonWidth int={browse_button_width};
    IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name'])} AND TRY_CONVERT(int,PO)=1 AND 显示=1 AND NULLIF(LTRIM(RTRIM(帮助)),N'') IS NOT NULL AND TRY_CONVERT(int,宽度)<=@BrowseButtonWidth) THROW 54235,N'带帮助字段的输入框外框宽度未为浏览按钮留出空间。',1;
    IF EXISTS (
        SELECT 1
        FROM dbo.SYS_TbColumn a JOIN dbo.SYS_TbColumn b
          ON a.表名=b.表名 AND a.PO=b.PO AND a.字段名<b.字段名
         AND a.顶坐标=b.顶坐标 AND a.表名={qn(c['bill_name'])} AND TRY_CONVERT(int,a.PO)=1
         AND a.显示=1 AND b.显示=1
         AND a.左坐标 < b.左坐标+b.宽度 AND b.左坐标 < a.左坐标+a.宽度
        WHERE RIGHT(UPPER(a.字段名),5)<>N'_PJLX' AND RIGHT(UPPER(a.字段名),4) NOT IN (N'_ZDR',N'_SHR') AND RIGHT(UPPER(a.字段名),3)<>N'_ZY'
          AND RIGHT(UPPER(b.字段名),5)<>N'_PJLX' AND RIGHT(UPPER(b.字段名),4) NOT IN (N'_ZDR',N'_SHR') AND RIGHT(UPPER(b.字段名),3)<>N'_ZY'
    ) THROW 54236,N'同一表头行的完整输入框外框发生水平重叠。',1;
    DECLARE @AuditTop int={int(audit['top'])}, @AuditBottom int={int(audit['bottom'])};
    DECLARE @NonFixedHeaderCount int=(SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name'])} AND TRY_CONVERT(int,PO)=1 AND 显示=1 AND RIGHT(UPPER(字段名),5) NOT IN (N'_SHBZ',N'_PJLX') AND RIGHT(UPPER(字段名),4) NOT IN (N'_ZDR',N'_SHR') AND RIGHT(UPPER(字段名),3)<>N'_ZY');
    DECLARE @SameRowOrdinaryCount int=(SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name'])} AND TRY_CONVERT(int,PO)=1 AND 显示=1 AND 顶坐标=@AuditTop AND RIGHT(UPPER(字段名),5)<>N'_SHBZ' AND RIGHT(UPPER(字段名),5)<>N'_PJLX' AND RIGHT(UPPER(字段名),4) NOT IN (N'_ZDR',N'_SHR') AND RIGHT(UPPER(字段名),3)<>N'_ZY');
    DECLARE @LastNonFixedHeaderBottom int=(SELECT MAX(顶坐标+高度) FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name'])} AND TRY_CONVERT(int,PO)=1 AND 显示=1 AND 顶坐标<@AuditTop AND 顶坐标+高度<=@AuditTop AND RIGHT(UPPER(字段名),5) NOT IN (N'_SHBZ',N'_PJLX') AND RIGHT(UPPER(字段名),4) NOT IN (N'_ZDR',N'_SHR') AND RIGHT(UPPER(字段名),3)<>N'_ZY');
    IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name'])} AND TRY_CONVERT(int,PO)=1 AND 显示=1 AND 顶坐标+高度>@AuditBottom AND RIGHT(UPPER(字段名),5)<>N'_SHBZ' AND RIGHT(UPPER(字段名),5)<>N'_PJLX' AND RIGHT(UPPER(字段名),4) NOT IN (N'_ZDR',N'_SHR') AND RIGHT(UPPER(字段名),3)<>N'_ZY') THROW 54237,N'非固定表头字段越过审核底边。',1;
    IF @NonFixedHeaderCount>0 AND @SameRowOrdinaryCount=0 AND @LastNonFixedHeaderBottom IS NULL THROW 54234,N'审核既未同行也没有可用于推导自然间距的上一行表头字段。',1;
    IF @LastNonFixedHeaderBottom IS NOT NULL AND (@AuditTop-@LastNonFixedHeaderBottom<10 OR @AuditTop-@LastNonFixedHeaderBottom<>{int(audit['natural_gap'])}) THROW 54234,N'审核与最后一个非固定表头字段之间的自然间距不符合契约（仅适用于审核换行）。',1;
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name'])} AND TRY_CONVERT(int,PO)=1 AND 显示=1 AND 左坐标+宽度>{int(audit['min_header_width'])}) THROW 54210,N'表头字段超过审核推导的最低宽度。',1;
IF (SELECT COUNT(*) FROM dbo.SYSWSPACE WHERE SYSWSPACE_MC IN ({workspace_names}))<>{len([row for row in c['workspace']['rows'] if row.get('SYSWSPACE_MC') is not None])} THROW 54214,N'工作区节点不完整。',1;
SELECT {', '.join(qi(f['name']) for f in c['header']['fields'])} FROM {h} WHERE 1=0;
SELECT {', '.join(qi(f['name']) for f in c['detail']['fields'])} FROM {d} WHERE 1=0;
IF NOT EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name']+'查询')}) THROW 54207,N'查询页元数据缺失。',1;
IF (SELECT COUNT(DISTINCT TRY_CONVERT(int,PO)) FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name']+'查询')})<>1 THROW 54226,N'查询页必须为单一 PO 分组。',1;
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name']+'查询')} AND COALESCE(表头,0)<>0) THROW 54227,N'查询页不允许存在表头锚点行。',1;
IF EXISTS (SELECT 标签名 FROM dbo.SYS_TbColumn WHERE 表名={qn(c['bill_name']+'查询')} GROUP BY 标签名 HAVING COUNT(*)>1) THROW 54228,N'查询页标签名重复，表头文本需唯一。',1;
SELECT N'VERIFICATION_PASS' AS VerificationStatus;
"""


def literal_for(field: dict[str, Any]) -> str:
    if "test_value" not in field:
        raise ValueError(f"CRUD requires test_value: {field['name']}")
    value = field["test_value"]
    t = base_type(field["sql"])
    if t == "bit":
        return "1" if value in (1, True, "1", "true", "True") else "0"
    if t.startswith(("int", "bigint", "smallint", "tinyint", "decimal")):
        if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", str(value)):
            raise ValueError(f"numeric test_value required: {field['name']}")
        return str(value)
    return qn(value)


def render_crud(c: dict[str, Any]) -> str:
    if not c.get("deployment_ready"):
        return blocked(c, "crud-test.sql")
    hf = [f for f in c["header"]["fields"] if not f.get("identity") and "test_value" in f]
    df = [f for f in c["detail"]["fields"] if not f.get("identity") and "test_value" in f]
    if not hf or not df:
        raise ValueError("CRUD requires test_value on at least one header and detail field")
    h, d = table_ref(c, "header"), table_ref(c, "detail")
    hcols, hvals = ",".join(qi(f["name"]) for f in hf), ",".join(literal_for(f) for f in hf)
    dcols, dvals = ",".join(qi(f["name"]) for f in df), ",".join(literal_for(f) for f in df)
    rel = c["detail"]["foreign_key"]
    return render_header(c, True) + f"""BEGIN TRANSACTION;
BEGIN TRY
    INSERT INTO {h} ({hcols}) VALUES ({hvals});
    INSERT INTO {d} ({dcols}) VALUES ({dvals});
    IF @@ROWCOUNT<>1 THROW 54300,N'明细插入失败。',1;
    ROLLBACK TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT N'CRUD_PASS_ZERO_RESIDUE' AS CrudStatus;
"""


def render_rollback_preflight(c: dict[str, Any]) -> str:
    if not c.get("deployment_ready"):
        return blocked(c, "rollback-preflight.sql")
    return render_header(c) + f"""IF EXISTS (SELECT 1 FROM {table_ref(c,'header')}) THROW 54400,N'表头已有业务数据，拒绝回滚。',1;
IF EXISTS (SELECT 1 FROM {table_ref(c,'detail')}) THROW 54401,N'表体已有业务数据，拒绝回滚。',1;
SELECT N'ROLLBACK_PREFLIGHT_PASS' AS Status;
"""


def render_rollback(c: dict[str, Any]) -> str:
    if not c.get("deployment_ready"):
        return blocked(c, "rollback.sql")
    return render_header(c, True) + f"""IF EXISTS (SELECT 1 FROM {table_ref(c,'header')}) OR EXISTS (SELECT 1 FROM {table_ref(c,'detail')}) THROW 54500,N'存在业务数据，拒绝回滚。',1;
BEGIN TRANSACTION;
BEGIN TRY
    DELETE dbo.SYSWSPACE WHERE SYSWSPACE_MC={qn(c['bill_name'])} OR SYSWSPACE_MC LIKE {qn(c['bill_name'])}+N'%';
    DELETE dbo.SYS_TbColumn WHERE 表名 IN ({qn(c['bill_name'])},{qn(c['bill_name']+'查询')});
    DELETE dbo.IOBDZD WHERE IOBDZD_MC={qn(c['bill_name'])};
    DROP TABLE {table_ref(c,'detail')};
    DROP TABLE {table_ref(c,'header')};
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT N'ROLLBACK_COMPLETE' AS Status;
"""


def render_readme(c: dict[str, Any]) -> str:
    status = "deployment-ready" if c.get("deployment_ready") else "review-blocked"
    return f"""# 复杂 IMES 表单四阶段包：{c.get('bill_name','未命名')}

状态：**{status}** ；类型：`{c.get('form_kind','')}`

## 固化流程

1. **字段契约确认**：表头/表体字段、主键、单号/分录号、外键、元数据类型（物理 `date`/`datetime`/`datetime2` 固定 `D`，其他字段固定 `S`）、普通字段控件默认值（`E`）、凭证类型字段（`*_PJLX`）固定为 `S`、审核字段和布局边界；`IOBDZD_FORMAT` 是 `PRD_GETDANHAO` 的流水号格式，缺失或空白默认 `YYMM####`，不能生成 NULL/空串。
2. **前期只读准备**：执行 `preflight.sql` 和 `reference-evidence.sql`，确认数据库身份、IOBDZD、SYS_TbColumn、查询页、BDJB、SYSWSPACE、标准 `sysmenu` 按钮和动态角色列。
3. **中期事务部署**：仅当 `contract.json` 已闭合且 `deployment_ready=true` 时执行 `forward.sql`；脚本包含表、IOBDZD、元数据、BDJB、工作区和标准 `sysmenu` 按钮的一次事务部署。
4. **后期校验与隔离 CRUD**：依次执行 `verification.sql`、`crud-test.sql`；验证覆盖维护页和查询页的正整数唯一 RID、逐字段运行时契约及 `v_tbcolumn` 投影，CRUD 在事务中回滚，必须零残留。

可见网格字段的 `列宽` 默认按 `标签名` 的完整显示宽度生成：3 个汉字为 `840`，4 个汉字为 `1125`；ASCII 字符按半宽单元计算，最终按 `15` 单位向上取整。显式更窄值会阻断生成，显式更宽值保留，维护页和查询页分别计算。布局控件的 `宽度` 与表格 `列宽` 分开。

编号规则必须按源码核对：客户端把可见单据名（`IOBDZD_MC`）传给 `PRD_GETDANHAO`，过程据此读取 `MARK`、`FORMAT`、`BascData`、`CurMonth`、`ModifyDate` 并更新编号状态；`IOBDZD_BH` 是表头 `PJLX`/数据权限类型，不是编号查找键，`IOBDZD_BILLNO` 也不是当前编号格式入口。支持的格式分支要以过程定义为准（`YYMM`、`YYYYMM`、`YYMMDD` 或 `#` 序号模式），已确认的非空格式不得被默认值覆盖。

审核控件的左坐标、宽度、高度和表头最低宽度不能从 ER 图猜测；必须由同版本有效参考单据证据确认。按稳定字段顺序先尝试把 `SHBZ` 放入当前行，只有完整标签/输入框/帮助 footprint 越过右边界才换行；审核换行时才按“上一行最后一个非固定可见表头字段底边 + 参考自然间距”推导，并将 `natural_gap` 写入契约。带帮助字段的当前 BCG 默认浏览按钮宽度为 20，定制图标按源码实测；普通字段不能越过审核边界，也不能在审核前留下未经证据支持的大空洞。审核底边仍是表头下限，客户端表体顶部按源码规则取审核底边 `+10`。查询页必须注册 `{c.get('bill_name','')}查询`；RID 由部署事务按当前 `MAX(RID)+offset` 分配，不能为 NULL 或固定跨环境值。复杂表单不能降级为 `BTYPE=1/UForm1`。`schema-draft.sql` 是注释式审阅草图，不能执行；部署只执行 `forward.sql`，不要批量执行目录内全部 `.sql`。数据库验证通过后仍需真实重新打开维护页和查询页。

脚本只生成文件，不连接、不写库，也不创建 MFC/C++/RC 资源。
"""


def generate(c: dict[str, Any], output: Path, force: bool = False) -> None:
    if output.exists() and any(output.iterdir()) and not force:
        raise ValueError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    if c.get("deployment_ready"):
        c = normalize(c)
    files = {
        "contract.json": json.dumps(c, ensure_ascii=False, indent=2) + "\n",
        "schema-draft.sql": render_schema(c), "preflight.sql": render_preflight(c),
        "reference-evidence.sql": render_reference_evidence(c), "forward.sql": render_forward(c),
        "verification.sql": render_verification(c), "crud-test.sql": render_crud(c),
        "rollback-preflight.sql": render_rollback_preflight(c), "rollback.sql": render_rollback(c),
        "README.md": render_readme(c),
    }
    for name, text in files.items():
        (output / name).write_text(text, encoding="utf-8", newline="\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--contract", type=Path)
    p.add_argument("--er-svg", type=Path)
    p.add_argument("--header-table")
    p.add_argument("--detail-table")
    p.add_argument("--bill-name", required=True)
    p.add_argument("--form-kind", choices=sorted(FORM_KINDS), default="header_detail_bill")
    p.add_argument("--expected-database")
    p.add_argument("--expected-server")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--force", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.contract:
            c = json.loads(args.contract.read_text(encoding="utf-8"))
            c = normalize(c)
        elif args.er_svg and args.header_table and args.detail_table:
            c = draft_from_er(args)
        else:
            raise ValueError("use --contract or --er-svg with --header-table and --detail-table")
        generate(c, args.output_dir, args.force)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Generated complex-form pack in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
