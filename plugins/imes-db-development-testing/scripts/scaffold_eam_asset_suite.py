#!/usr/bin/env python3
"""Generate the database contract for the EAM asset/parts ER diagram.

The generator is intentionally offline.  It reads the reviewed ER SVG and
emits one guarded deployment pack for the missing basic-data forms and
header/detail bills.  It does not connect to SQL Server or execute SQL.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter
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


SCHEMA = "dbo"
ROOT_BH = "0014"

BASIC_SPECS = [
    ("EAMWLFL", "物料分类", "EAMWLFL_CODE", "EAMWLFL_CODE,EAMWLFL_NAME", "001409"),
    ("EAMCK", "仓库", "EAMCK_CODE", "EAMCK_CODE,EAMCK_NAME", "001410"),
    # The target database already owns the generic "物料" workspace. Keep
    # this ER-backed form distinct so its AutoOpen name and metadata remain
    # resolvable without overwriting the existing form.
    ("EAMWL", "资产物料", "EAMWL_CODE", "EAMWL_CODE,EAMWL_NAME", "001411"),
    ("EAMWLGYS", "物料供应商", "EAMWLGYS_MATERIAL_BH", "EAMWLGYS_MATERIAL_BH,EAMWLGYS_REMARK", "001412"),
    ("EAMSSKCXX", "物料库存信息", "EAMSSKCXX_WLBH", "EAMSSKCXX_WLBH,EAMSSKCXX_CKBH", "001413"),
    ("EAMDJXM", "点检项目", "EAMDJXM_CODE", "EAMDJXM_CODE,EAMDJXM_NAME", "001414"),
    ("EAMBYXM", "保养项目", "EAMBYXM_CODE", "EAMBYXM_CODE,EAMBYXM_NAME", "001415"),
    ("EAMMJSYJL", "模具使用记录", "EAMMJSYJL_MJBH", "EAMMJSYJL_MJBH", "001416"),
]

BILL_SPECS = [
    ("EAMSBLBJQD1", "EAMSBLBJQD2", "设备零部件清单", "EAMSBLBJQD", "EAMSBL", "零部件"),
    ("EAMZCRKD1", "EAMZCRKD2", "资产入库单", "EAMZCRKD", "EAMRK", "资产明细"),
    ("EAMZCJY1", "EAMZCJY2", "资产借用", "EAMZCJY", "EAMJY", "借用明细"),
    ("EAMZCGH1", "EAMZCGH2", "资产归还", "EAMZCGH", "EAMGH", "归还明细"),
    ("EAMZCBFD1", "EAMZCBFD2", "资产报废单", "EAMZCBFD", "EAMBF", "报废明细"),
    ("EAMBYZQJH1", "EAMBYZQJH2", "保养周期计划", "EAMBYZQJH", "EAMBYJH", "保养项目"),
    ("EAMBYJLD1", "EAMBYJLD2", "保养记录单", "EAMBYJLD", "EAMBYJL", "保养记录"),
    ("EAMJDJH1", "EAMJDJH2", "检定计划", "EAMJDJH", "EAMJDJH", "检定项目"),
    ("EAMJDJLD1", "EAMJDJLD2", "检定记录单", "EAMJDJLD", "EAMJDJL", "检定记录"),
    ("EAMBXD1", "EAMBXD2", "报修单", "EAMBXD", "EAMBX", "报修明细"),
    ("EAMWXGD1", "EAMWXGD2", "维修工单", "EAMWXGD", "EAMWX", "维修部件"),
]

REQUIRED_SYSMENU = (
    ("显示关联单据", 0, "3", 40, 0, " ", 0, " "),
    ("保存列宽", 0, "3", 0, 1, "其他", 1, " "),
    ("列配置", 0, "4", 0, 1, "其他", 0, " "),
    ("从EXCEL导入", 0, "5", 0, 1, "其他", 0, " "),
    ("说明", 1, "3", 24, 0, " ", 0, " "),
    ("附件", 0, "3", 24, 0, " ", 0, " "),
    ("复制分录", 1, "3", 40, 0, " ", 0, " "),
)

META_COLUMNS = (
    "表名", "PO", "字段名", "主键", "RMark", "显示名", "标签名", "不控", "显示", "列宽", "顺序",
    "合计", "按钮", "只读", "表头", "颜色值", "新增", "更新", "置空", "筛选", "必填", "合并",
    "对齐", "切换", "GLZD", "LMark", "类型", "帮助", "标识", "默认值", "管道字符", "关键字段",
    "左坐标", "顶坐标", "宽度", "高度", "admin", "优先级", "左对齐", "右对齐", "顶对齐", "底对齐",
    "控件", "RID",
)

# SQL identifiers in this metadata model may be English field names or
# Chinese labels used as derived-column aliases.  Keep the same safe shape
# while allowing Unicode word characters.
IDENT_RE = re.compile(r"^[^\W\d]\w*$", re.UNICODE)
CJK_RE = re.compile(r"[\u3400-\u9fff]")


def qn(value: Any) -> str:
    if value is None:
        return "NULL"
    return "N'" + str(value).replace("'", "''") + "'"


def qs(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def qi(value: str) -> str:
    if not IDENT_RE.fullmatch(value):
        raise ValueError(f"unsafe identifier: {value!r}")
    return f"[{value}]"


def qalias(value: str) -> str:
    """Quote an ER label used as a derived SQL column alias."""
    return "[" + str(value).replace("]", "]]" ) + "]"


def sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return qn(value)


def explicit_label(field: dict[str, Any], context: str, require_cjk: bool = False) -> str:
    """Require a deliberate human-facing label; never fall back to the field name."""
    name = str(field.get("name", "")).strip()
    label = field.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ValueError(f"{context}字段 {name or '<unknown>'} 缺少显示标签，拒绝生成")
    label = label.strip()
    if label == name:
        raise ValueError(f"{context}字段 {name} 的显示标签回退为物理字段名，拒绝生成")
    if require_cjk and not CJK_RE.search(label):
        raise ValueError(f"{context}字段 {name} 缺少中文显示名: {label!r}")
    return label


def type_base(sql: str) -> str:
    return re.sub(r"\s+IDENTITY\([^)]*\)$", "", sql, flags=re.I).lower()


def type_length(sql: str) -> int | None:
    match = re.search(r"\((\d+)\)", sql)
    return int(match.group(1)) if match else None


def normalized_field(field: dict[str, Any], context: str, require_cjk: bool = False) -> dict[str, Any]:
    out = copy.deepcopy(field)
    out["label"] = explicit_label(field, context, require_cjk=require_cjk)
    out["sql"] = str(out["er_type"])
    out["identity"] = bool(out.get("pk"))
    if out["identity"]:
        out["sql"] = "int IDENTITY(1,1)"
        out["nullable"] = False
    else:
        out["nullable"] = True
    return out


def fixed_header_fields(table: str, route_bh: str) -> list[dict[str, Any]]:
    return [
        {"name": f"{table}_ZDR", "label": "制单人", "sql": "varchar(50)", "nullable": True},
        {"name": f"{table}_SHR", "label": "审核人", "sql": "varchar(50)", "nullable": True},
        {"name": f"{table}_SHBZ", "label": "审核", "sql": "bit", "nullable": False, "default": "0"},
        {"name": f"{table}_PJLX", "label": "凭证类型", "sql": "varchar(20)", "nullable": False, "default": route_bh},
        {"name": f"{table}_YWRQ", "label": "制单日期", "sql": "date", "nullable": True},
        {"name": f"{table}_PRINT", "label": "打印次数", "sql": "int", "nullable": False, "default": "0"},
        {"name": f"{table}_ZY", "label": "摘要", "sql": "nvarchar(100)", "nullable": True},
    ]


def make_tables(er: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    basic: dict[str, dict[str, Any]] = {}
    for table, visible, vkey, byzd, leaf in BASIC_SPECS:
        if table not in er:
            raise ValueError(f"ER 图缺少基础表 {table}")
        fields = [normalized_field(f, f"ER表 {table}", require_cjk=True) for f in er[table]["fields"]]
        required_names = set(vkey.split(",")) | set(byzd.split(","))
        for field in fields:
            if field["name"] in required_names:
                field["nullable"] = False
        basic[table] = {
            "table": table,
            "visible_name": visible,
            "route_bh": table,
            "vkey": vkey,
            "byzd": byzd,
            "leaf": leaf,
            "fields": fields,
            "kind": "basic",
        }

    bills: dict[str, dict[str, Any]] = {}
    for index, (header, detail, visible, bh, mark, tab) in enumerate(BILL_SPECS, start=17):
        if header not in er or detail not in er:
            raise ValueError(f"ER 图缺少主从表 {header}/{detail}")
        header_fields = [normalized_field(f, f"ER表 {header}", require_cjk=True) for f in er[header]["fields"]]
        detail_fields = [normalized_field(f, f"ER表 {detail}", require_cjk=True) for f in er[detail]["fields"]]
        header_fields += fixed_header_fields(header, bh)
        for field in header_fields:
            if field["name"] in {f"{header}_SJDH", f"{header}_PJLX"}:
                field["nullable"] = False
        # Saved detail rows always carry both runtime linkage values.
        for f in detail_fields:
            if f["name"].endswith("_SJDH") or f["name"].endswith("_FLH"):
                f["nullable"] = False
        bills[visible] = {
            "header": header,
            "detail": detail,
            "visible_name": visible,
            "route_bh": bh,
            "route_type": "EAM",
            "ioflag": 0,
            "mark": mark,
            "tab": tab,
            "leaf": f"0014{index:02d}",
            "header_fields": header_fields,
            "detail_fields": detail_fields,
            "kind": "bill",
        }
    return basic, bills


def field_by_name(table: dict[str, Any], name: str) -> dict[str, Any]:
    return next(f for f in table.get("fields", table.get("header_fields", []) + table.get("detail_fields", [])) if f["name"] == name)


def add_unique_and_fk(table: dict[str, Any], fields: list[dict[str, Any]]) -> list[tuple[str, str, str, str]]:
    """Return (constraint, local, ref_table, ref_column) for proven-compatible links."""
    result: list[tuple[str, str, str, str]] = []
    names = {f["name"] for f in fields}
    if table["kind"] in {"header", "detail"}:
        header = table["header"]
        detail = table["detail"]
        for f in fields:
            if table["kind"] == "detail" and f["name"] == f"{detail}_SJDH":
                result.append((f"FK_{detail}_SJDH", f["name"], header, f"{header}_SJDH"))
            if table["kind"] == "detail" and f["name"] == f"{detail}_RECORD_BH" and header == "EAMBYJLD1":
                result.append((f"FK_{detail}_RECORD", f["name"], header, f"{header}_SJDH"))
            if table["kind"] == "detail" and f["name"] == f"{detail}_RECORD_BH" and header == "EAMDJJLD1":
                result.append((f"FK_{detail}_RECORD", f["name"], header, f"{header}_JLDH"))
            if f["name"].endswith("_ASSET_TYPE_BH"):
                result.append((f"FK_{table['header']}_{f['name'].split('_', 1)[-1]}", f["name"], "EAMZCLX", "EAMZCLX_CODE"))
            if f["name"].endswith("_ZCLXBH"):
                result.append((f"FK_{table['header']}_{f['name'].split('_', 1)[-1]}", f["name"], "EAMZCLX", "EAMZCLX_CODE"))
            if f["name"].endswith("_ASSET_BH") and type_length(f["sql"]) == 30:
                result.append((f"FK_{table['header']}_{f['name'].split('_', 1)[-1]}", f["name"], "EAMZCDA", "EAMZCDA_CODE"))
            if f["name"].endswith("_ITEM_BH"):
                ref = "EAMBYXM" if table["header"] == "EAMBYZQJH1" else "EAMDJXM"
                result.append((f"FK_{table['detail']}_{f['name'].split('_', 1)[-1]}", f["name"], ref, f"{ref}_CODE"))
            if f["name"] == "EAMBYJLD2_BYXM":
                result.append(("FK_EAMBYJLD2_BYXM", f["name"], "EAMBYXM", "EAMBYXM_CODE"))
            if f["name"] in {"EAMJDJH2_JDXM", "EAMJDJLD2_JDXM"}:
                result.append((f"FK_{f['name']}_CODE", f["name"], "EAMDJXM", "EAMDJXM_CODE"))
            if f["name"] in {"EAMSBLBJQD2_LBJBM", "EAMWXGD2_PART_BH"}:
                result.append((f"FK_{f['name']}_CODE", f["name"], "EAMWL", "EAMWL_CODE"))
            if f["name"] == "EAMBYJLD1_PLAN_BH":
                result.append(("FK_EAMBYJLD1_PLAN", f["name"], "EAMBYZQJH1", "EAMBYZQJH1_SJDH"))
            if f["name"] == "EAMJDJH2_PLAN_BH":
                result.append(("FK_EAMJDJH2_PLAN", f["name"], "EAMJDJH1", "EAMJDJH1_SJDH"))
    else:
        for f in fields:
            mapping = {
                "EAMWL_CATEGORY_BH": ("EAMWLFL", "EAMWLFL_CODE"),
                "EAMWL_LINE_BH": ("EAMXT", "EAMXT_CODE"),
                "EAMWLGYS_MATERIAL_BH": ("EAMWL", "EAMWL_CODE"),
            }.get(f["name"])
            if mapping:
                result.append((f"FK_{table['table']}_{f['name'].split('_', 1)[-1]}", f["name"], mapping[0], mapping[1]))
    # Keep only links whose local and referenced string widths are known to match.
    compatible: list[tuple[str, str, str, str]] = []
    width_map = {
        "EAMZCLX_CODE": 20, "EAMZCDA_CODE": 30, "EAMBYXM_CODE": 30, "EAMDJXM_CODE": 30,
        "EAMWLFL_CODE": 20, "EAMXT_CODE": 20, "EAMWL_CODE": 30,
    }
    for constraint, local, ref_table, ref_column in result:
        if local not in names:
            continue
        local_width = type_length(field_by_name({"fields": fields}, local)["sql"])
        ref_width = width_map.get(ref_column)
        if ref_width is not None and local_width != ref_width:
            continue
        compatible.append((constraint, local, ref_table, ref_column))
    return compatible


def table_fields(table: dict[str, Any]) -> list[dict[str, Any]]:
    if table["kind"] == "basic":
        return table["fields"]
    return table["fields"]


def table_ddl(table: dict[str, Any], all_tables: dict[str, dict[str, Any]]) -> str:
    name = table["table"]
    fields = table_fields(table)
    lines: list[str] = [f"    CREATE TABLE dbo.{name}", "    ("]
    definitions: list[str] = []
    for f in fields:
        nullability = "NOT NULL" if not f.get("nullable", True) or f.get("identity") else "NULL"
        default = ""
        if f.get("default") is not None:
            default = f" CONSTRAINT DF_{name}_{f['name'].split('_', 1)[-1]} DEFAULT ({sql_value(f['default'])})"
        definitions.append(f"        {qi(f['name'])} {f['sql']} {nullability}{default}")
    pk = next(f for f in fields if f.get("pk"))
    definitions.append(f"        CONSTRAINT PK_{name} PRIMARY KEY CLUSTERED ({qi(pk['name'])})")
    if table["kind"] == "basic":
        key = next((f for f in fields if f["name"].endswith("_CODE")), next((f for f in fields if f["name"].endswith("_MJBH")), None))
        if key:
            definitions.append(f"        CONSTRAINT UQ_{name}_{key['name'].split('_', 1)[-1]} UNIQUE ({qi(key['name'])})")
        elif name == "EAMSSKCXX":
            definitions.append("        CONSTRAINT UQ_EAMSSKCXX_WLBH_CKBH UNIQUE ([EAMSSKCXX_WLBH],[EAMSSKCXX_CKBH])")
    else:
        if table["kind"] == "header":
            sjdh = next(f for f in fields if f["name"] == f"{name}_SJDH")
            definitions.append(f"        CONSTRAINT UQ_{name}_SJDH UNIQUE ({qi(sjdh['name'])})")
            if name == "EAMDJJLD1":
                record_key = next((f for f in fields if f["name"] == f"{name}_JLDH"), None)
                if record_key:
                    definitions.append(f"        CONSTRAINT UQ_{name}_JLDH UNIQUE ({qi(record_key['name'])})")
        else:
            sjdh = next(f for f in fields if f["name"].endswith("_SJDH"))
            flh = next(f for f in fields if f["name"].endswith("_FLH"))
            definitions.append(f"        CONSTRAINT UQ_{name}_SJDH_FLH UNIQUE ({qi(sjdh['name'])},{qi(flh['name'])})")
    for constraint, local, ref_table, ref_column in add_unique_and_fk(table, fields):
        definitions.append(f"        CONSTRAINT {constraint} FOREIGN KEY ({qi(local)}) REFERENCES dbo.{ref_table}({qi(ref_column)})")
    lines.append(",\n".join(definitions))
    lines.append("    );")
    return "\n".join(lines)


def lookup_for(field_name: str) -> tuple[str, str, str] | None:
    if field_name.endswith("_PJLX"):
        return "IOBDZD_BH", "PJLXBZ", "r_pjlx"
    if field_name.endswith("_SHBZ"):
        return "LSDJZT_BH", "SHZTBZ", "r_shbz"
    if field_name.endswith("_ASSET_TYPE_BH"):
        return "EAMZCLX_CODE", "EAMZCLX_BZ", "r_zclx"
    if field_name.endswith("_ASSET_BH") and not field_name.startswith("EAMDJJLD2_"):
        return "EAMZCDA_CODE", None, "r_zcda"
    if field_name.endswith("_CATEGORY_BH"):
        return "EAMWLFL_CODE", "EAMWLFL_BZ", "r_wlfl"
    if field_name.endswith("_LINE_BH"):
        return "EAMXT_CODE", "EAMXT_BZ", "r_xt"
    if field_name.endswith("_MATERIAL_BH"):
        return "EAMWL_CODE", "EAMWL_BZ", "r_wl"
    if field_name.endswith("_WLBH"):
        return "EAMWL_CODE", "EAMWL_BZ", "r_wl"
    if field_name.endswith("_CKBH"):
        return "EAMCK_CODE", "EAMCK_BZ", "r_ck"
    if field_name.endswith("_ITEM_BH"):
        ref = "EAMBYXM" if field_name.startswith("EAMBYZQJH2_") else "EAMDJXM"
        return f"{ref}_CODE", f"{ref}_BZ", "r_item"
    if field_name in {"EAMBYJLD2_BYXM"}:
        return "EAMBYXM_CODE", "EAMBYXM_BZ", "r_byxm"
    if field_name in {"EAMJDJH2_JDXM", "EAMJDJLD2_JDXM"}:
        return "EAMDJXM_CODE", "EAMDJXM_BZ", "r_djxm"
    if field_name in {"EAMSBLBJQD2_LBJBM", "EAMWXGD2_PART_BH"}:
        return "EAMWL_CODE", "EAMWL_BZ", "r_wl"
    return None


def row_label(field: dict[str, Any], role: str, query: bool = False) -> str:
    name = field["name"]
    if name.endswith("_ID"):
        return "FID" if role == "detail" else "HID"
    if query and role == "detail" and field.get("label") == "单号":
        return "明细单号"
    if query and role == "detail" and field.get("label") == "备注":
        return "行备注"
    return explicit_label(field, f"{role}元数据 ")


def header_layout(rows: list[dict[str, Any]]) -> None:
    ordinary = [r for r in rows if r["field"].endswith("_ID") is False and r["field"].split("_")[-1] not in {"ZDR", "SHR", "ZY", "SHBZ"}]
    x_positions = (75, 370, 665, 960)
    for index, row in enumerate(ordinary):
        column = index % 4
        line = index // 4
        row["left"] = x_positions[column]
        row["top"] = 120 + line * 35
        row["width"] = 220 if row["label_width"] <= 1125 else 300
        row["height"] = 22
    if ordinary:
        audit_top = max(r["top"] + r["height"] for r in ordinary) + 10
    else:
        audit_top = 187
    for row in rows:
        suffix = row["field"].rsplit("_", 1)[-1]
        if row["field"].endswith("_ID"):
            row.update(left=0, top=0, width=0, height=0)
        elif suffix == "SHBZ":
            row.update(left=1100, top=audit_top, width=100, height=25)
        elif suffix == "ZDR":
            row.update(left=70, top=539, width=100, height=22)
        elif suffix == "SHR":
            row.update(left=220, top=529, width=100, height=22)
        elif suffix == "ZY":
            row.update(left=70, top=843, width=800, height=22)
    # The audit lower bound is the physical bottom of the fixed audit control.
    audit = next(r for r in rows if r["field"].endswith("_SHBZ"))
    audit["audit_bottom"] = audit["top"] + audit["height"]


def metadata_row(table: dict[str, Any], field: dict[str, Any], role: str, po: int, order: int, rid_offset: int, query: bool = False, label_override: str | None = None, key_field: bool = False) -> dict[str, Any]:
    label = label_override or row_label(field, role, query)
    if not label.strip() or label.strip() == field["name"]:
        raise ValueError(f"{table.get('visible_name', table.get('table', '<form>'))} 字段 {field['name']} 缺少有效中文/显示映射")
    glzd_info = lookup_for(field["name"])
    visible = not field["name"].endswith("_ID")
    suffix = field["name"].rsplit("_", 1)[-1]
    readonly = field["name"].endswith("_ID") or suffix in {"SHBZ", "PRINT", "ZDR", "SHR"}
    required = (field["name"].endswith("_SJDH") and role == "header") or field["name"].endswith("_PJLX")
    if table["kind"] == "basic":
        required = not field.get("nullable", True) and not field.get("identity")
    if field.get("identity"):
        required = False
    return {
        "table_name": table.get("visible_name", table.get("visible_name")),
        "field": field["name"],
        "po": po,
        "order": order,
        "primary_key": bool(field.get("pk")),
        "display_name": label,
        "label": label,
        "label_width": label_column_width(label),
        "visible": int(visible),
        "column_width": label_column_width(label),
        "required": int(required),
        "readonly": int(readonly),
        "header": int(role == "header" and not query),
        "new": int(not field.get("identity")),
        "update": int(not field.get("identity") and not (suffix == "SHBZ")),
        "filter": int(visible and (suffix in {"SJDH", "CODE", "MJBH"} or glzd_info is not None)),
        "key_field": int(key_field),
        "glzd": glzd_info[0] if glzd_info else None,
        "help": glzd_info[1] if glzd_info else None,
        "lmark": glzd_info[2] if glzd_info else "",
        "rmark": "",
        "type": "D" if type_base(field["sql"]) in {"date", "datetime", "datetime2"} else "S",
        "control": "S" if field["name"].upper().endswith("_PJLX") else "E",
        "default": field.get("default"),
        "left": 0,
        "top": 0,
        "width": 0,
        "height": 0,
        "admin": "1",
        "rid_offset": rid_offset,
        "physical_role": role,
    }


def make_metadata(basic: dict[str, dict[str, Any]], bills: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    maintain: list[dict[str, Any]] = []
    query: list[dict[str, Any]] = []
    offset = 0
    for table in basic.values():
        rows = [metadata_row(table, f, "basic", 1, i, offset + i - 1) for i, f in enumerate(table["fields"], start=1)]
        for row in rows:
            row["table_name"] = table["visible_name"]
            row["header"] = 0
            row["left"] = 0 if row["field"].endswith("_ID") else 75
            row["top"] = 0 if row["field"].endswith("_ID") else 40 + (row["order"] - 1) * 30
            row["width"] = 0 if row["field"].endswith("_ID") else 320
            row["height"] = 0 if row["field"].endswith("_ID") else 22
        maintain.extend(rows)
        offset += len(rows)

    for bill in bills.values():
        header_rows = [metadata_row(bill, f, "header", 1, i, offset + i - 1) for i, f in enumerate(bill["header_fields"], start=1)]
        detail_business = [f for f in bill["detail_fields"] if not f["name"].endswith(("_ID", "_SJDH", "_FLH"))]
        detail_rows = [metadata_row(bill, f, "detail", 2, i, offset + len(header_rows) + i - 1) for i, f in enumerate(bill["detail_fields"], start=1)]
        if detail_business:
            next(r for r in detail_rows if r["field"] == detail_business[0]["name"])["key_field"] = 1
        header_layout(header_rows)
        maintain.extend(header_rows)
        maintain.extend(detail_rows)
        offset += len(header_rows) + len(detail_rows)

        all_query_fields: list[tuple[dict[str, Any], str]] = [(f, "header") for f in bill["header_fields"]] + [(f, "detail") for f in bill["detail_fields"]]
        used: set[str] = set()
        qrows: list[dict[str, Any]] = []
        for index, (field, role) in enumerate(all_query_fields, start=1):
            label = row_label(field, role, True)
            if label in used:
                label = ("明细" if role == "detail" else "表头") + label
            while label in used:
                label += "_" + str(index)
            used.add(label)
            row = metadata_row(bill, field, role, 1, index, offset + len(qrows), True, label_override=label, key_field=(role == "header" and field["name"].endswith("_SJDH")))
            row["table_name"] = bill["visible_name"] + "查询"
            row["header"] = 0
            row["left"] = row["top"] = row["width"] = row["height"] = 0
            row["primary_key"] = int(role == "header" and field["name"].endswith("_ID"))
            qrows.append(row)
        query.extend(qrows)
        offset += len(qrows)
    return maintain, query


def validate_metadata_closure(
    basic: dict[str, dict[str, Any]],
    bills: dict[str, dict[str, Any]],
    maintain: list[dict[str, Any]],
    query: list[dict[str, Any]],
) -> None:
    """Fail closed when a physical field is missing, duplicated, or has no label map."""
    expected_groups: list[tuple[str, int, list[str]]] = []
    for table in basic.values():
        expected_groups.append((table["visible_name"], 1, [f["name"] for f in table["fields"]]))
    for bill in bills.values():
        expected_groups.append((bill["visible_name"], 1, [f["name"] for f in bill["header_fields"]]))
        expected_groups.append((bill["visible_name"], 2, [f["name"] for f in bill["detail_fields"]]))
        expected_groups.append(
            (
                bill["visible_name"] + "查询",
                1,
                [f["name"] for f in bill["header_fields"] + bill["detail_fields"]],
            )
        )

    for form_name, po, expected in expected_groups:
        rows = [
            row
            for row in (maintain + query)
            if row["table_name"] == form_name and int(row["po"]) == po
        ]
        actual = [row["field"] for row in rows]
        if Counter(actual) != Counter(expected):
            missing = sorted((Counter(expected) - Counter(actual)).elements())
            extra = sorted((Counter(actual) - Counter(expected)).elements())
            raise ValueError(
                f"{form_name} PO={po} 字段集合未闭合；缺失={missing}, 多余={extra}"
            )

    for row in maintain + query:
        display = str(row.get("display_name") or "").strip()
        label = str(row.get("label") or "").strip()
        if not display or not label:
            raise ValueError(f"{row['table_name']} 字段 {row['field']} 缺少显示名/标签名")
        if display == row["field"] or label == row["field"]:
            raise ValueError(f"{row['table_name']} 字段 {row['field']} 使用物理字段名回退显示")

    for form_name in {row["table_name"] for row in query}:
        aliases = [row["display_name"] for row in query if row["table_name"] == form_name]
        labels = [row["label"] for row in query if row["table_name"] == form_name]
        if len(aliases) != len(set(aliases)) or len(labels) != len(set(labels)):
            raise ValueError(f"{form_name} 查询页显示名/标签名不唯一")


def metadata_tuple(row: dict[str, Any]) -> str:
    values: list[Any] = [
        row["table_name"], str(row["po"]), row["field"], int(row["primary_key"]), row["rmark"], row["display_name"], row["label"],
        0, row["visible"], row["column_width"], row["order"], 0, 0, row["readonly"], row["header"], None,
        row["new"], row["update"], 1, row["filter"], row["required"], 1, 7, int(row["glzd"] is not None), row["glzd"], row["lmark"],
        row["type"], row["help"], None, row["default"], None, row["key_field"], row["left"], row["top"], row["width"], row["height"], row["admin"],
        0, None, None, None, None, row["control"], f"@RIDBase+{row['rid_offset']}",
    ]
    text_positions = {0, 1, 2, 4, 5, 6, 24, 25, 26, 27, 28, 29, 30, 36, 38, 39, 40, 41, 42}
    rendered = []
    for index, value in enumerate(values):
        if value is None:
            rendered.append("NULL")
        elif index in text_positions:
            rendered.append(qn(value))
        else:
            rendered.append(str(value))
    return "(" + ",".join(rendered) + ")"


def workspace_rows(basic: dict[str, dict[str, Any]], bills: dict[str, dict[str, Any]]) -> list[tuple[str, str, str | None, str, int, int, int]]:
    rows: list[tuple[str, str, str | None, str, int, int, int]] = []
    for table in basic.values():
        leaf = table["leaf"]
        rows.append(("1", leaf, ROOT_BH, table["visible_name"], 1, 3, 0))
        for suffix, operation in (("10", "新增"), ("20", "编辑"), ("80", "删除")):
            rows.append(("1", leaf + suffix, leaf, table["visible_name"] + operation, 1, 4, 1))
    for bill in bills.values():
        leaf = bill["leaf"]
        rows.append(("1", leaf, ROOT_BH, bill["visible_name"], 1, 3, 0))
        for suffix, operation in (("10", "新增"), ("20", "编辑"), ("30", "复制"), ("40", "审核"), ("50", "取消审核"), ("60", "打印"), ("70", "打印设计"), ("80", "删除")):
            rows.append(("1", leaf + suffix, leaf, bill["visible_name"] + operation, 1, 4, 1))
    return rows


def route_rows(basic: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for table in basic.values():
        rows.append({
            "bh": table["route_bh"], "btype": "1", "mc": table["visible_name"], "table": table["table"],
            "vkey": table["vkey"], "byzd": table["byzd"], "bzmc": table["visible_name"] + "帮助", "bzbh": table["table"] + "_BZ",
        })
    return rows


def header_of(bill: dict[str, Any]) -> dict[str, Any]:
    return {"table": bill["header"], "header": bill["header"], "detail": bill["detail"], "fields": bill["header_fields"], "kind": "header"}


def detail_of(bill: dict[str, Any]) -> dict[str, Any]:
    return {"table": bill["detail"], "header": bill["header"], "detail": bill["detail"], "fields": bill["detail_fields"], "kind": "detail"}


def cross_table(bill: dict[str, Any], maintain: list[dict[str, Any]]) -> str:
    text = f"dbo.{bill['header']} LEFT JOIN dbo.{bill['detail']} ON {bill['header']}_SJDH={bill['detail']}_SJDH"
    aliases: set[str] = set()
    for row in maintain:
        if row["table_name"] != bill["visible_name"] or row["po"] not in (1, 2) or not row["glzd"]:
            continue
        info = lookup_for(row["field"])
        if not info:
            continue
        alias = info[2]
        if alias in aliases:
            continue
        aliases.add(alias)
        table = {"IOBDZD_BH": "IOBDZD", "LSDJZT_BH": "LSDJZT", "EAMZCLX_CODE": "EAMZCLX", "EAMZCDA_CODE": "EAMZCDA", "EAMWLFL_CODE": "EAMWLFL", "EAMXT_CODE": "EAMXT", "EAMWL_CODE": "EAMWL", "EAMCK_CODE": "EAMCK", "EAMBYXM_CODE": "EAMBYXM", "EAMDJXM_CODE": "EAMDJXM"}[info[0]]
        text += f" LEFT JOIN dbo.{table} AS {alias} ON {row['field']}={alias}.{info[0]}"
    return text


def select_list(rows: list[dict[str, Any]], convert: bool = True) -> str:
    fields: list[str] = []
    for row in rows:
        alias = row["label"]
        if convert and row["glzd"]:
            byzd = {
                "IOBDZD_BH": "IOBDZD_MC", "LSDJZT_BH": "LSDJZT_MC", "EAMZCLX_CODE": "EAMZCLX_NAME",
                "EAMZCDA_CODE": "EAMZCDA_CODE", "EAMWLFL_CODE": "EAMWLFL_NAME", "EAMXT_CODE": "EAMXT_NAME",
                "EAMWL_CODE": "EAMWL_NAME", "EAMCK_CODE": "EAMCK_NAME", "EAMBYXM_CODE": "EAMBYXM_NAME", "EAMDJXM_CODE": "EAMDJXM_NAME",
            }[row["glzd"]]
            fields.append(f"{row['lmark']}.{byzd} AS {qalias(alias)}")
        else:
            fields.append(f"{row['field']} AS {qalias(alias)}")
    return ",".join(fields)


def bill_menu_sql(bill_name: str) -> list[str]:
    rows = []
    for button, topfloor, xh, icon, submenu, pmenu, trimenu, uid in REQUIRED_SYSMENU:
        rows.append(
            f"    ({qn(bill_name)},{topfloor},{qn(xh)},{qn(button)},{icon},{submenu},{qn(pmenu)},{trimenu},{qn(uid)})"
        )
    return rows


def render_header(expected_database: str | None = None, expected_server: str | None = None) -> str:
    if not expected_database or not expected_server:
        return """SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET NOCOUNT ON;
SET XACT_ABORT ON;
THROW 56000,N'未提供 --expected-database/--expected-server，生成包保持 review-blocked。',1;
"""
    return f"""SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF DB_NAME() <> {qn(expected_database)} THROW 56000,N'目标数据库与契约不符。',1;
IF @@SERVERNAME <> {qn(expected_server)} THROW 56001,N'目标实例与契约不符。',1;
"""


def all_new_physical(basic: dict[str, dict[str, Any]], bills: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for table in basic.values():
        result.append(table)
    for bill in bills.values():
        result.extend((header_of(bill), detail_of(bill)))
    return result


def render_preflight(
    basic: dict[str, dict[str, Any]],
    bills: dict[str, dict[str, Any]],
    expected_database: str | None = None,
    expected_server: str | None = None,
) -> str:
    physical = all_new_physical(basic, bills)
    names = [t.get("table") or t.get("header") or t.get("detail") for t in physical]
    visible_names = [t["visible_name"] for t in basic.values()] + [b["visible_name"] for b in bills.values()]
    bill_names = [b["visible_name"] for b in bills.values()]
    workspace_codes = [ROOT_BH] + [x[1] for x in workspace_rows(basic, bills)] + [x[2] for x in workspace_rows(basic, bills) if x[2]]
    unique_codes = list(dict.fromkeys(workspace_codes))
    workspace_names = [x[3] for x in workspace_rows(basic, bills)]
    if len(workspace_names) != len(set(workspace_names)):
        raise ValueError("generated SYSWSPACE_MC names are not unique")
    return render_header(expected_database, expected_server) + f"""SELECT DB_NAME() AS CurrentDatabase,@@SERVERNAME AS CurrentServer,CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(50)) AS ProductVersion;
SELECT ISNULL(MAX(RID),0) AS CurrentMaxRID FROM dbo.SYS_TbColumn;
SELECT name AS ExistingTargetTable FROM sys.tables WHERE name IN ({','.join(qn(x) for x in names)}) ORDER BY name;
SELECT 表名,字段名,类型,控件,列宽 FROM dbo.SYS_TbColumn WHERE 表名 IN ({','.join(qn(x) for x in visible_names)}) ORDER BY 表名,顺序;
SELECT IOBDZD_MC,IOBDZD_BH,IOBDZD_MARK,IOBDZD_FORMAT,IOBDZD_HTABLE,IOBDZD_FTABLE FROM dbo.IOBDZD WHERE IOBDZD_MC IN ({','.join(qn(x) for x in bill_names)}) ORDER BY IOBDZD_MC;
SELECT SYSWSPACE_BH,SYSWSPACE_PBH,SYSWSPACE_MC FROM dbo.SYSWSPACE WHERE SYSWSPACE_BH IN ({','.join(qn(x) for x in unique_codes)}) ORDER BY SYSWSPACE_BH;
SELECT SYSWSPACE_ID,SYSWSPACE_BH,SYSWSPACE_PBH,SYSWSPACE_MC FROM dbo.SYSWSPACE WHERE SYSWSPACE_MC IN ({','.join(qn(x) for x in workspace_names)}) ORDER BY SYSWSPACE_MC,SYSWSPACE_BH;
SELECT IOJCBDZD_BH,IOJCBDZD_MC,IOJCBDZD_TABLE,IOJCBDZD_VKEY,IOJCBDZD_BZBH FROM dbo.IOJCBDZD WHERE IOJCBDZD_BH IN ({','.join(qn(x) for x in [r['bh'] for r in route_rows(basic)])}) OR IOJCBDZD_BZBH IN ({','.join(qn(x["table"] + "_BZ") for x in basic.values())});
IF OBJECT_ID(N'dbo.IOJCBDZD',N'U') IS NULL OR OBJECT_ID(N'dbo.IOBDZD',N'U') IS NULL OR OBJECT_ID(N'dbo.SYS_TbColumn',N'U') IS NULL OR OBJECT_ID(N'dbo.SYSWSPACE',N'U') IS NULL OR OBJECT_ID(N'dbo.BDJB',N'U') IS NULL OR OBJECT_ID(N'dbo.sysmenu',N'U') IS NULL THROW 56002,N'缺少 IMES 元数据基础对象。',1;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.SYS_TbColumn') AND name=N'RID') THROW 56003,N'SYS_TbColumn 缺少 RID。',1;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.SYSWSPACE') AND name=N'admin') THROW 56004,N'SYSWSPACE 缺少 admin 权限边界。',1;
IF EXISTS (SELECT 1 FROM sys.tables WHERE name IN ({','.join(qn(x) for x in names)})) THROW 56005,N'目标物理表已存在，拒绝覆盖。',1;
IF EXISTS (SELECT 1 FROM dbo.IOJCBDZD WHERE IOJCBDZD_BH IN ({','.join(qn(r['bh']) for r in route_rows(basic))})) THROW 56006,N'目标基础资料路由已存在。',1;
IF EXISTS (SELECT 1 FROM dbo.IOJCBDZD WHERE IOJCBDZD_MC IN ({','.join(qn(x) for x in visible_names)})) THROW 56016,N'目标表单可见名已被基础资料路由占用。',1;
IF EXISTS (SELECT 1 FROM dbo.IOBDZD WHERE IOBDZD_MC IN ({','.join(qn(x) for x in visible_names)})) THROW 56017,N'目标表单可见名已被动态单据路由占用。',1;
IF EXISTS (SELECT 1 FROM dbo.IOBDZD WHERE IOBDZD_BH IN ({','.join(qn(x['route_bh']) for x in bills.values())})) THROW 56014,N'目标动态单据 BH 已存在。',1;
IF EXISTS (SELECT 1 FROM dbo.IOBDZD WHERE IOBDZD_MARK IN ({','.join(qn(x['mark']) for x in bills.values())})) THROW 56015,N'目标动态单据 MARK 已存在。',1;
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名 IN ({','.join(qn(x) for x in visible_names)})) THROW 56008,N'目标维护页元数据已存在。',1;
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名 IN ({','.join(qn(x + '查询') for x in bill_names)})) THROW 56009,N'目标查询页元数据已存在。',1;
IF EXISTS (SELECT 1 FROM dbo.SYSWSPACE WHERE SYSWSPACE_BH IN ({','.join(qn(x) for x in unique_codes if x != ROOT_BH)})) THROW 56010,N'目标工作区编号已存在。',1;
IF EXISTS (SELECT 1 FROM dbo.SYSWSPACE WHERE SYSWSPACE_MC IN ({','.join(qn(x) for x in workspace_names)})) THROW 56018,N'目标工作区名称已存在。',1;
IF NOT EXISTS (SELECT 1 FROM dbo.IOJCBDZD WHERE IOJCBDZD_VKEY=N'IOBDZD_BH' AND IOJCBDZD_TOP=1) THROW 56011,N'缺少凭证类型转换路由。',1;
IF NOT EXISTS (SELECT 1 FROM dbo.IOJCBDZD WHERE IOJCBDZD_VKEY=N'LSDJZT_BH' AND IOJCBDZD_TOP=1) THROW 56012,N'缺少审核状态转换路由。',1;
SELECT N'PREFLIGHT_PASS' AS Status;
"""


def render_forward(
    basic: dict[str, dict[str, Any]],
    bills: dict[str, dict[str, Any]],
    maintain: list[dict[str, Any]],
    query: list[dict[str, Any]],
    expected_database: str | None = None,
    expected_server: str | None = None,
) -> str:
    physical = all_new_physical(basic, bills)
    # Create each header before its detail and retain the dependency order in the spec list.
    ddl = []
    for table in basic.values():
        ddl.append(table_ddl(table, {}))
    for bill in bills.values():
        ddl.append(table_ddl(header_of(bill), {}))
        ddl.append(table_ddl(detail_of(bill), {}))
    route_values = []
    for row in route_rows(basic):
        route_values.append(f"    ({qn(row['bh'])},N'1',{qn(row['mc'])},{qn(row['table'])},{qn(row['vkey'])},{qn(row['byzd'])},NULL,NULL,NULL,{qn(row['bzmc'])},{qn(row['bzbh'])},1,0,NULL,NULL)")
    meta_values = [metadata_tuple(r) for r in maintain + query]
    iobdzd_values = []
    for bill in bills.values():
        iobdzd_values.append(
            f"    ({qn(bill['route_bh'])},{qn(bill['visible_name'])},{qn(bill['route_type'])},{int(bill['ioflag'])},"
            f"{qn(bill['header'])},{qn(bill['detail'])},{qn(bill['header'] + '_SJDH')},{qn(bill['detail'] + '_SJDH')},"
            f"{qn(bill['mark'])},{qn('资产管理主从单据')},{qn(bill['tab'])},NULL,NULL,NULL,0,"
            f"CONVERT(date,GETDATE()),N'YYMM####',CONVERT(varchar(7),GETDATE(),111))"
        )
    ws = workspace_rows(basic, bills)
    ws_values = [f"    ({qs(loc)},{qs(bh)},{'NULL' if pbh is None else qs(pbh)},{qs(name)}, {mx},{js},1,0,{btn},1)" for loc,bh,pbh,name,mx,js,btn in ws]
    menus = []
    for bill in bills.values():
        menus.extend(bill_menu_sql(bill["visible_name"]))
    bdjb = []
    for bill in bills.values():
        h, sjdh, shbz, shr = bill["header"], f"{bill['header']}_SJDH", f"{bill['header']}_SHBZ", f"{bill['header']}_SHR"
        audit_guard = f"IF EXISTS (SELECT 1 FROM dbo.{h} WHERE {sjdh}='@SJDH' AND {shbz}=1) RAISERROR(N'本单据已审核',16,1)"
        cancel_guard = f"IF EXISTS (SELECT 1 FROM dbo.{h} WHERE {sjdh}='@SJDH' AND {shbz}=0) RAISERROR(N'本单据已处于未审核状态',16,1)"
        audit_update = f"UPDATE dbo.{h} SET {shbz}=1,{shr}='@USERNAME' WHERE {sjdh}='@SJDH'"
        cancel_update = f"UPDATE dbo.{h} SET {shbz}=0,{shr}='' WHERE {sjdh}='@SJDH'"
        bdjb.extend([
            f"    ({qn(bill['visible_name'])},N'审核',1,0,1,N'检查审核状态',0,{qn(audit_guard)})",
            f"    ({qn(bill['visible_name'])},N'取消审核',1,0,1,N'检查审核状态',0,{qn(cancel_guard)})",
            f"    ({qn(bill['visible_name'])},N'审核',0,1,1,N'更新审核状态',0,{qn(audit_update)})",
            f"    ({qn(bill['visible_name'])},N'取消审核',0,1,1,N'恢复未审核状态',0,{qn(cancel_update)})",
        ])
    ddl_sql = "\n".join(ddl)
    route_sql = ",\n".join(route_values)
    iobdzd_sql = ",\n".join(iobdzd_values)
    meta_sql = ",\n".join("    " + value for value in meta_values)
    workspace_sql = ",\n".join(ws_values)
    bdjb_sql = ",\n".join(bdjb)
    menu_sql = ",\n".join(menus)
    return render_header(expected_database, expected_server) + f"""BEGIN TRANSACTION;
BEGIN TRY
{ddl_sql}
    CREATE INDEX IX_EAM_ASSET_SUITE_DETAIL_SJDH ON dbo.EAMZCRKD2(EAMZCRKD2_SJDH);
    CREATE INDEX IX_EAM_ASSET_SUITE_PART_SJDH ON dbo.EAMWXGD2(EAMWXGD2_SJDH);
    INSERT dbo.IOJCBDZD
    (IOJCBDZD_BH,IOJCBDZD_BTYPE,IOJCBDZD_MC,IOJCBDZD_Table,IOJCBDZD_Vkey,IOJCBDZD_BYZD,IOJCBDZD_JSZD,IOJCBDZD_YXBZZD,IOJCBDZD_Filter,IOJCBDZD_BZMC,IOJCBDZD_BZBH,IOJCBDZD_TOP,IOJCBDZD_SXXS,IOJCBDZD_LBTABLE,IOJCBDZD_LBNAME)
    VALUES
{route_sql};
    INSERT dbo.IOBDZD
    (IOBDZD_BH,IOBDZD_MC,IOBDZD_Type,IOBDZD_IoFlag,IOBDZD_HTable,IOBDZD_FTable,IOBDZD_HVKey,IOBDZD_FVKey,IOBDZD_MARK,IOBDZD_BZ,IOBDZD_TAB1,IOBDZD_TAB2,IOBDZD_TAB3,IOBDZD_BILLNO,IOBDZD_BascData,IOBDZD_ModifyDate,IOBDZD_FORMAT,IOBDZD_CurMonth)
    VALUES
{iobdzd_sql};
    DECLARE @RIDBase int = ISNULL((SELECT MAX(TRY_CONVERT(int,RID)) FROM dbo.SYS_TbColumn),0)+1;
    IF @RIDBase<=0 THROW 56013,N'无法分配正整数 RID。',1;
    CREATE TABLE #NewMeta(nID int NOT NULL);
    INSERT dbo.SYS_TbColumn ({','.join(qi(x) for x in META_COLUMNS)})
    OUTPUT inserted.nID INTO #NewMeta(nID)
    VALUES
{meta_sql};
    DECLARE @sql nvarchar(max),@set nvarchar(max);
    SELECT @set=STUFF((SELECT N','+QUOTENAME(c.name)+N'=1' FROM sys.columns c WHERE c.object_id=OBJECT_ID(N'dbo.SYS_TbColumn') AND c.system_type_id=104 AND c.column_id>(SELECT column_id FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.SYS_TbColumn') AND name=N'RID') ORDER BY c.column_id FOR XML PATH(''),TYPE).value('.','nvarchar(max)'),1,1,N'');
    IF NULLIF(@set,N'') IS NOT NULL BEGIN SET @sql=N'UPDATE m SET '+@set+N' FROM dbo.SYS_TbColumn m JOIN #NewMeta n ON n.nID=m.nID;'; EXEC sys.sp_executesql @sql; END;
    CREATE TABLE #NewWorkspace(SYSWSPACE_ID int NOT NULL);
    INSERT dbo.SYSWSPACE (SYSWSPACE_LOC,SYSWSPACE_BH,SYSWSPACE_PBH,SYSWSPACE_MC,SYSWSPACE_MX,SYSWSPACE_JS,SYSWSPACE_JDBZ,SYSWSPACE_QCYWBZ,SYSWSPACE_BTN,admin)
    OUTPUT inserted.SYSWSPACE_ID INTO #NewWorkspace(SYSWSPACE_ID)
    VALUES
{workspace_sql};
    SELECT @set=STUFF((SELECT N','+QUOTENAME(c.name)+N'=1' FROM sys.columns c WHERE c.object_id=OBJECT_ID(N'dbo.SYSWSPACE') AND c.system_type_id=104 AND c.column_id>(SELECT column_id FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.SYSWSPACE') AND name=N'admin') ORDER BY c.column_id FOR XML PATH(''),TYPE).value('.','nvarchar(max)'),1,1,N'');
    IF NULLIF(@set,N'') IS NOT NULL BEGIN SET @sql=N'UPDATE w SET '+@set+N' FROM dbo.SYSWSPACE w JOIN #NewWorkspace n ON n.SYSWSPACE_ID=w.SYSWSPACE_ID;'; EXEC sys.sp_executesql @sql; END;
    INSERT dbo.BDJB (BDJB_PJLX,BDJB_CMD,BDJB_QZJC,BDJB_ORDER,BDJB_YX,BDJB_BZ,BDJB_TYPE,BDJB_SQL)
    VALUES
{bdjb_sql};
    INSERT dbo.sysmenu (SYSMENU_BDMC,SYSMENU_TOPFLOOR,SYSMENU_XH,SYSMENU_BUTTONNAME,SYSMENU_ICON,SYSMENU_SUBMENU,SYSMENU_PMENU,SYSMENU_TRIMENU,SYSMENU_UID)
    VALUES
{menu_sql};
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT N'FORWARD_COMPLETE' AS DeployStatus,DB_NAME() AS CurrentDatabase,@@SERVERNAME AS CurrentServer;
"""


def render_verification(
    basic: dict[str, dict[str, Any]],
    bills: dict[str, dict[str, Any]],
    maintain: list[dict[str, Any]],
    query: list[dict[str, Any]],
    expected_database: str | None = None,
    expected_server: str | None = None,
) -> str:
    physical = all_new_physical(basic, bills)
    visible = [t["visible_name"] for t in basic.values()] + [b["visible_name"] for b in bills.values()]
    query_names = [b["visible_name"] + "查询" for b in bills.values()]
    all_meta_names = visible + query_names
    total_meta = len(maintain) + len(query)
    expected_types = ",\n".join(
        f"    ({qn(row['table_name'])},{qn(row['field'])},{qn(row['type'])})"
        for row in maintain + query
    )
    checks = []
    closure_checks = []
    for table in physical:
        name = table.get("table") or table.get("header") or table.get("detail")
        fields = table_fields(table)
        checks.append(f"IF OBJECT_ID(N'dbo.{name}',N'U') IS NULL THROW 56100,N'物理表 {name} 缺失。',1;")
        checks.append(f"IF (SELECT COUNT(*) FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.{name}'))<>{len(fields)} THROW 56101,N'物理表 {name} 字段数量不符。',1;")
    cross_checks = []
    width_checks = []
    for row in maintain + query:
        if row["visible"]:
            width_checks.append(
                f"IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名={qn(row['table_name'])} AND 字段名={qn(row['field'])} AND 显示=1 AND 列宽<{row['column_width']}) THROW 56109,N'字段 {row['field']} 列宽不足以显示完整标签。',1;"
            )

    for table in basic.values():
        form = table["visible_name"]
        fields = table["fields"]
        closure_checks.extend(
            [
                f"IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名={qn(form)} AND PO=N'1')<>{len(fields)} THROW 56130,N'{form} 维护字段数量不完整。',1;",
                f"IF EXISTS (SELECT 1 FROM sys.columns sc WHERE sc.object_id=OBJECT_ID(N'dbo.{table['table']}',N'U') AND NOT EXISTS (SELECT 1 FROM dbo.v_tbcolumn c WHERE c.[表名]={qn(form)} AND c.PO=N'1' AND c.[字段名]=sc.name)) THROW 56131,N'{form} 存在物理字段未映射到元数据。',1;",
                f"IF EXISTS (SELECT 1 FROM dbo.v_tbcolumn c WHERE c.[表名]={qn(form)} AND c.PO=N'1' AND NOT EXISTS (SELECT 1 FROM sys.columns sc WHERE sc.object_id=OBJECT_ID(N'dbo.{table['table']}',N'U') AND sc.name=c.[字段名])) THROW 56132,N'{form} 存在元数据悬空字段。',1;",
            ]
        )

    for bill in bills.values():
        for form, po, physical_name, fields in (
            (bill["visible_name"], 1, bill["header"], bill["header_fields"]),
            (bill["visible_name"], 2, bill["detail"], bill["detail_fields"]),
        ):
            closure_checks.extend(
                [
                    f"IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名={qn(form)} AND PO=N'{po}')<>{len(fields)} THROW 56130,N'{form} PO={po} 维护字段数量不完整。',1;",
                    f"IF EXISTS (SELECT 1 FROM sys.columns sc WHERE sc.object_id=OBJECT_ID(N'dbo.{physical_name}',N'U') AND NOT EXISTS (SELECT 1 FROM dbo.v_tbcolumn c WHERE c.[表名]={qn(form)} AND c.PO=N'{po}' AND c.[字段名]=sc.name)) THROW 56131,N'{form} PO={po} 存在物理字段未映射到元数据。',1;",
                    f"IF EXISTS (SELECT 1 FROM dbo.v_tbcolumn c WHERE c.[表名]={qn(form)} AND c.PO=N'{po}' AND NOT EXISTS (SELECT 1 FROM sys.columns sc WHERE sc.object_id=OBJECT_ID(N'dbo.{physical_name}',N'U') AND sc.name=c.[字段名])) THROW 56132,N'{form} PO={po} 存在元数据悬空字段。',1;",
                ]
            )
        query_form = bill["visible_name"] + "查询"
        query_fields = bill["header_fields"] + bill["detail_fields"]
        closure_checks.extend(
            [
                f"IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名={qn(query_form)} AND PO=N'1')<>{len(query_fields)} THROW 56133,N'{query_form} 查询字段数量不完整。',1;",
                f"IF EXISTS (SELECT 1 FROM (SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.{bill['header']}',N'U') UNION ALL SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.{bill['detail']}',N'U')) sc WHERE NOT EXISTS (SELECT 1 FROM dbo.v_tbcolumn c WHERE c.[表名]={qn(query_form)} AND c.PO=N'1' AND c.[字段名]=sc.name)) THROW 56134,N'{query_form} 存在物理字段未投影到查询页。',1;",
                f"IF EXISTS (SELECT 1 FROM dbo.v_tbcolumn c WHERE c.[表名]={qn(query_form)} AND c.PO=N'1' AND NOT EXISTS (SELECT 1 FROM sys.columns sc WHERE sc.object_id IN (OBJECT_ID(N'dbo.{bill['header']}',N'U'),OBJECT_ID(N'dbo.{bill['detail']}',N'U')) AND sc.name=c.[字段名])) THROW 56135,N'{query_form} 存在查询页悬空字段。',1;",
            ]
        )

    expected_label_values = ",\n".join(
        f"    ({qn(row['table_name'])},{qn(row['field'])},{qn(row['display_name'])},{qn(row['label'])})"
        for row in maintain + query
    )
    for bill in bills.values():
        mrows = [r for r in maintain if r["table_name"] == bill["visible_name"]]
        qrows = [r for r in query if r["table_name"] == bill["visible_name"] + "查询"]
        cross = cross_table(bill, maintain)
        cross_checks.append(f"SELECT {select_list(qrows)} FROM {cross} WHERE 1=2; SELECT * FROM (SELECT {select_list(qrows)} FROM {cross} WHERE 1=2) t WHERE 1=2;")
        cross_checks.append(f"IF (SELECT COUNT(*) FROM dbo.IOBDZD WHERE IOBDZD_MC={qn(bill['visible_name'])} AND IOBDZD_BH={qn(bill['route_bh'])} AND IOBDZD_Type={qn(bill['route_type'])} AND IOBDZD_IoFlag={int(bill['ioflag'])} AND IOBDZD_MARK={qn(bill['mark'])} AND NULLIF(LTRIM(RTRIM(IOBDZD_FORMAT)),N'') IS NOT NULL AND IOBDZD_FORMAT=N'YYMM####' AND IOBDZD_BascData IS NOT NULL AND IOBDZD_ModifyDate IS NOT NULL AND NULLIF(LTRIM(RTRIM(IOBDZD_CurMonth)),N'') IS NOT NULL AND IOBDZD_HTABLE={qn(bill['header'])} AND IOBDZD_FTABLE={qn(bill['detail'])})<>1 THROW 56120,N'动态单据路由或编号初始状态不完整。',1;")
        cross_checks.append(f"IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名={qn(bill['visible_name'])} AND PO=N'1' AND 字段名={qn(bill['header']+'_PJLX')} AND 切换=1 AND GLZD=N'IOBDZD_BH' AND 必填=1 AND 控件=N'S' AND 类型=N'S')<>1 THROW 56121,N'凭证类型固定字段不完整。',1;")
        cross_checks.append(f"IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名={qn(bill['visible_name'])} AND PO=N'1' AND 字段名={qn(bill['header']+'_SHBZ')} AND 切换=1 AND GLZD=N'LSDJZT_BH' AND 控件=N'E' AND 类型=N'S')<>1 THROW 56122,N'审核固定字段不完整。',1;")
        cross_checks.append(f"IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名={qn(bill['visible_name']+'查询')} AND PO=N'1' AND 关键字段=1)<>1 THROW 56123,N'查询页关键字段不唯一。',1;")
        cross_checks.append(f"IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名={qn(bill['visible_name']+'查询')})<>{len(qrows)} THROW 56124,N'查询页字段集不完整。',1;")
        cross_checks.append(
            f"IF (SELECT COUNT(*) FROM dbo.BDJB WHERE BDJB_PJLX={qn(bill['visible_name'])} AND BDJB_YX=1 AND BDJB_CMD=N'审核' AND BDJB_QZJC=1 AND ISNULL(BDJB_ORDER,0)=0)<>1 OR "
            f"(SELECT COUNT(*) FROM dbo.BDJB WHERE BDJB_PJLX={qn(bill['visible_name'])} AND BDJB_YX=1 AND BDJB_CMD=N'审核' AND BDJB_QZJC=0 AND ISNULL(BDJB_ORDER,0)=0)<>1 OR "
            f"(SELECT COUNT(*) FROM dbo.BDJB WHERE BDJB_PJLX={qn(bill['visible_name'])} AND BDJB_YX=1 AND BDJB_CMD=N'取消审核' AND BDJB_QZJC=1 AND ISNULL(BDJB_ORDER,0)=0)<>1 OR "
            f"(SELECT COUNT(*) FROM dbo.BDJB WHERE BDJB_PJLX={qn(bill['visible_name'])} AND BDJB_YX=1 AND BDJB_CMD=N'取消审核' AND BDJB_QZJC=0 AND ISNULL(BDJB_ORDER,0)=0)<>1 "
            f"THROW 56125,N'审核和取消审核四条基础规则不完整。',1;"
        )
        cross_checks.append(f"IF (SELECT COUNT(*) FROM dbo.sysmenu WHERE SYSMENU_BDMC={qn(bill['visible_name'])})<>{len(REQUIRED_SYSMENU)} THROW 56126,N'主从单据标准按钮不完整。',1;")
    workspace_codes = list(dict.fromkeys([x[1] for x in workspace_rows(basic, bills)] + [x[2] for x in workspace_rows(basic, bills) if x[2]]))
    return render_header(expected_database, expected_server) + f"""SELECT DB_NAME() AS CurrentDatabase,@@SERVERNAME AS CurrentServer;
{chr(10).join(checks)}
IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名 IN ({','.join(qn(x) for x in all_meta_names)}))<>{total_meta} THROW 56102,N'元数据总行数不符。',1;
DECLARE @ExpectedType TABLE(表名 nvarchar(100) NOT NULL,字段名 nvarchar(100) NOT NULL,类型 nchar(1) NOT NULL,PRIMARY KEY(表名,字段名));
INSERT @ExpectedType(表名,字段名,类型) VALUES
{expected_types};
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn m JOIN @ExpectedType e ON e.表名=m.表名 AND e.字段名=m.字段名 WHERE COALESCE(m.类型,N'')<>e.类型 OR COALESCE(m.控件,N'')<>CASE WHEN RIGHT(UPPER(m.字段名),5)=N'_PJLX' THEN N'S' ELSE N'E' END OR m.标识 IS NOT NULL OR m.RID IS NULL OR m.RID<=0) THROW 56103,N'新生成日期元数据必须为 D，其他字段为 S；普通字段控件 E，PJLX 控件 S，标识 NULL，RID 正数。',1;
IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名 IN ({','.join(qn(x) for x in all_meta_names)}))<>(SELECT COUNT(DISTINCT RID) FROM dbo.SYS_TbColumn WHERE 表名 IN ({','.join(qn(x) for x in all_meta_names)})) THROW 56104,N'新生成元数据 RID 重复。',1;
IF EXISTS (SELECT 表名,PO FROM dbo.SYS_TbColumn WHERE 表名 IN ({','.join(qn(x) for x in all_meta_names)}) GROUP BY 表名,PO HAVING MIN(顺序)<>1 OR MAX(顺序)<>COUNT(*) OR COUNT(DISTINCT 顺序)<>COUNT(*) OR SUM(CASE WHEN 顺序 IS NULL THEN 1 ELSE 0 END)>0) THROW 56105,N'每个表名与 PO 的顺序必须从 1 连续编号。',1;
IF EXISTS (SELECT 表名,PO FROM dbo.SYS_TbColumn WHERE 表名 IN ({','.join(qn(x) for x in all_meta_names)}) GROUP BY 表名,PO HAVING SUM(CASE WHEN 主键=1 THEN 1 ELSE 0 END)<>1) THROW 56106,N'每个表名与 PO 必须只有一个主键。',1;
IF EXISTS (SELECT 表名,PO,显示名 FROM dbo.SYS_TbColumn WHERE 表名 IN ({','.join(qn(x) for x in query_names)}) GROUP BY 表名,PO,显示名 HAVING COUNT(*)>1) THROW 56107,N'查询页显示别名重复。',1;
IF EXISTS (SELECT 表名,PO,标签名 FROM dbo.SYS_TbColumn WHERE 表名 IN ({','.join(qn(x) for x in query_names)}) GROUP BY 表名,PO,标签名 HAVING COUNT(*)>1) THROW 56115,N'查询页标签名重复。',1;
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn m LEFT JOIN dbo.v_tbcolumn v ON v.nID=m.nID WHERE m.表名 IN ({','.join(qn(x) for x in all_meta_names)}) AND v.nID IS NULL) THROW 56108,N'v_tbcolumn 投影缺失。',1;
{chr(10).join(width_checks)}
IF EXISTS (SELECT 1 FROM dbo.v_tbcolumn WHERE 表名 IN ({','.join(qn(x) for x in all_meta_names)}) AND NULLIF(LTRIM(RTRIM(ISNULL(GLZD,N''))),N'') IS NOT NULL AND (IOJCBDZD_Table IS NULL OR IOJCBDZD_Vkey IS NULL OR LMark IS NULL OR RMark IS NULL)) THROW 56110,N'GLZD 关联映射不闭合；LMark/RMark 的 NULL 必须改为空字符串。',1;
IF EXISTS (SELECT 1 FROM dbo.v_tbcolumn WHERE 表名 IN ({','.join(qn(x) for x in all_meta_names)}) AND (NULLIF(LTRIM(RTRIM(ISNULL(显示名,N''))),N'') IS NULL OR NULLIF(LTRIM(RTRIM(ISNULL(标签名,N''))),N'') IS NULL OR 显示名=字段名 OR 标签名=字段名)) THROW 56116,N'元数据存在空显示名/标签名或物理字段名回退。',1;
DECLARE @ExpectedLabels TABLE(表名 nvarchar(100) NOT NULL,字段名 sysname NOT NULL,显示名 nvarchar(200) NOT NULL,标签名 nvarchar(100) NOT NULL,PRIMARY KEY(表名,字段名));
INSERT @ExpectedLabels(表名,字段名,显示名,标签名) VALUES
{expected_label_values};
IF EXISTS (SELECT 1 FROM @ExpectedLabels e LEFT JOIN dbo.v_tbcolumn c ON c.[表名]=e.[表名] AND c.[字段名]=e.[字段名] AND c.[显示名]=e.[显示名] AND c.[标签名]=e.[标签名] WHERE c.[字段名] IS NULL) THROW 56117,N'物理字段到中文显示名/标签名映射不一致。',1;
{chr(10).join(closure_checks)}
IF (SELECT COUNT(*) FROM dbo.SYSWSPACE WHERE SYSWSPACE_BH IN ({','.join(qn(x) for x in workspace_codes)}))<>{len(workspace_codes)} THROW 56111,N'工作区节点不完整。',1;
IF EXISTS (SELECT 1 FROM dbo.SYSWSPACE c WHERE c.SYSWSPACE_BH IN ({','.join(qn(x) for x in workspace_codes)}) AND c.SYSWSPACE_PBH IS NOT NULL AND NOT EXISTS (SELECT 1 FROM dbo.SYSWSPACE p WHERE p.SYSWSPACE_BH=c.SYSWSPACE_PBH)) THROW 56112,N'工作区父节点悬空。',1;
IF EXISTS (SELECT 1 FROM dbo.SYSWSPACE WHERE SYSWSPACE_BH IN ({','.join(qn(x) for x in workspace_codes)}) AND ISNULL(admin,0)<>1) THROW 56113,N'工作区 admin 权限未授权。',1;
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名 IN ({','.join(qn(x) for x in visible)}) AND (列宽 IS NULL OR 列宽<=0)) THROW 56114,N'基础资料列宽缺失。',1;
{chr(10).join(cross_checks)}
{chr(10).join(f"{render_basic_query(t, maintain)}" for t in basic.values())}
SELECT N'VERIFICATION_PASS' AS VerificationStatus;
"""


def render_basic_query(table: dict[str, Any], maintain: list[dict[str, Any]]) -> str:
    rows = [r for r in maintain if r["table_name"] == table["visible_name"]]
    from_text = f"dbo.{table['table']}"
    aliases = set()
    for row in rows:
        if not row["glzd"]:
            continue
        info = lookup_for(row["field"])
        if not info or info[2] in aliases:
            continue
        aliases.add(info[2])
        ref_table = {"EAMWLFL_CODE": "EAMWLFL", "EAMXT_CODE": "EAMXT", "EAMWL_CODE": "EAMWL", "EAMCK_CODE": "EAMCK", "EAMBYXM_CODE": "EAMBYXM", "EAMDJXM_CODE": "EAMDJXM"}.get(info[0])
        if ref_table:
            from_text += f" LEFT JOIN dbo.{ref_table} AS {info[2]} ON {row['field']}={info[2]}.{info[0]}"
    return f"SELECT {select_list(rows)} FROM {from_text} WHERE 1=2;"


def test_value(table: dict[str, Any], field: dict[str, Any], bill_number: str | None = None) -> str | None:
    name = field["name"]
    if field.get("identity"):
        return None
    if bill_number and name.endswith("_SJDH"):
        return bill_number
    if name in {"EAMSBLBJQD2_LBJBM", "EAMWXGD2_PART_BH"}:
        return "__EAM_WL__"
    if name in {"EAMJDJH2_JDXM", "EAMJDJLD2_JDXM"}:
        return "__EAM_DJXM__"
    if name == "EAMBYJLD1_PLAN_BH":
        return "__EAM_EAMBYZQJH__"
    if name == "EAMJDJH2_PLAN_BH":
        return "__EAM_EAMJDJH__"
    if name == "EAMBYJLD2_RECORD_BH":
        return "__EAM_EAMBYJLD__"
    if name.endswith("_PJLX"):
        return table.get("route_bh")
    if name.endswith(("_CATEGORY_BH", "_LINE_BH", "_MATERIAL_BH", "_WLBH", "_CKBH", "_ITEM_BH", "_ASSET_TYPE_BH", "_ASSET_BH", "_ZCLXBH")) and field.get("nullable", True):
        return None
    if name.endswith("_SHBZ") or name.endswith("_PRINT"):
        return "0"
    if name in {"EAMWL_CATEGORY_BH", "EAMWLFL_CODE"}:
        return "__EAM_WLFL__"
    if name == "EAMWL_CODE" or name == "EAMWLGYS_MATERIAL_BH" or name == "EAMSSKCXX_WLBH":
        return "__EAM_WL__"
    if name == "EAMCK_CODE" or name == "EAMSSKCXX_CKBH":
        return "__EAM_CK__"
    if name == "EAMDJXM_CODE" or name == "EAMDJMB2_ITEM_BH":
        return "__EAM_DJXM__"
    if name == "EAMBYXM_CODE" or name == "EAMBYZQJH2_ITEM_BH":
        return "__EAM_BYXM__"
    if name == "EAMMJSYJL_MJBH":
        return "__EAM_MJ__"
    base = type_base(field["sql"])
    if base == "bit":
        return "0"
    if base.startswith(("int", "smallint", "bigint", "tinyint", "decimal")):
        return "1"
    if base in {"date", "datetime", "datetime2"}:
        return "2026-08-28"
    length = type_length(field["sql"])
    value = "__EAM_TEST__"
    return value[:length] if length else value


def render_crud(
    basic: dict[str, dict[str, Any]],
    bills: dict[str, dict[str, Any]],
    expected_database: str | None = None,
    expected_server: str | None = None,
) -> str:
    statements: list[str] = []
    # Basic dependencies are inserted in the same order as the DDL.
    for table in basic.values():
        fields = [f for f in table["fields"] if not f.get("identity")]
        cols, vals = [], []
        for f in fields:
            value = test_value(table, f)
            if value is not None:
                cols.append(qi(f["name"]))
                vals.append("0" if type_base(f["sql"]) == "bit" else value if re.fullmatch(r"-?\d+(?:\.\d+)?", str(value)) else qn(value))
        statements.append(f"    INSERT dbo.{table['table']} ({','.join(cols)}) VALUES ({','.join(vals)});")
    for bill in bills.values():
        number = "__EAM_" + bill["route_bh"] + "__"
        h = header_of(bill); d = detail_of(bill)
        hfields = [f for f in h["fields"] if not f.get("identity")]
        dfields = [f for f in d["fields"] if not f.get("identity")]
        hcols, hvals = [], []
        for f in hfields:
            value = test_value(bill, f, number)
            if value is not None:
                hcols.append(qi(f["name"]))
                hvals.append("0" if type_base(f["sql"]) == "bit" else value if re.fullmatch(r"-?\d+(?:\.\d+)?", str(value)) else qn(value))
        dcols, dvals = [], []
        for f in dfields:
            value = test_value(bill, f, number)
            if f["name"].endswith("_FLH"):
                value = "1"
            if value is not None:
                dcols.append(qi(f["name"]))
                dvals.append("0" if type_base(f["sql"]) == "bit" else value if re.fullmatch(r"-?\d+(?:\.\d+)?", str(value)) else qn(value))
        statements.append(f"    INSERT dbo.{bill['header']} ({','.join(hcols)}) VALUES ({','.join(hvals)});")
        statements.append(f"    INSERT dbo.{bill['detail']} ({','.join(dcols)}) VALUES ({','.join(dvals)});")
    # The entire smoke test is transactional and leaves no business rows behind.
    return render_header(expected_database, expected_server) + f"""IF @@TRANCOUNT<>0 THROW 56200,N'CRUD 测试要求干净事务。',1;
BEGIN TRANSACTION;
BEGIN TRY
{chr(10).join(statements)}
    ROLLBACK TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT N'CRUD_PASS_ZERO_RESIDUE' AS CrudStatus;
"""


def render_rollback(
    basic: dict[str, dict[str, Any]],
    bills: dict[str, dict[str, Any]],
    expected_database: str | None = None,
    expected_server: str | None = None,
) -> str:
    physical = all_new_physical(basic, bills)
    checks = []
    for table in physical:
        name = table.get("table") or table.get("header") or table.get("detail")
        checks.append(f"IF EXISTS (SELECT 1 FROM dbo.{name}) THROW 56300,N'表 {name} 已有业务数据，拒绝回滚。',1;")
    visible = [t["visible_name"] for t in basic.values()] + [b["visible_name"] for b in bills.values()]
    qnames = [b["visible_name"] + "查询" for b in bills.values()]
    routes = [t["route_bh"] for t in basic.values()]
    ws = list(dict.fromkeys([x[1] for x in workspace_rows(basic, bills)] + [x[2] for x in workspace_rows(basic, bills) if x[2]]))
    drop = []
    for bill in reversed(list(bills.values())):
        drop.append(f"    DROP TABLE dbo.{bill['detail']};")
        drop.append(f"    DROP TABLE dbo.{bill['header']};")
    for table in reversed(list(basic.values())):
        drop.append(f"    DROP TABLE dbo.{table['table']};")
    return render_header(expected_database, expected_server) + f"""{chr(10).join(checks)}
BEGIN TRANSACTION;
BEGIN TRY
    DELETE dbo.sysmenu WHERE SYSMENU_BDMC IN ({','.join(qn(x) for x in [b['visible_name'] for b in bills.values()])});
    DELETE dbo.BDJB WHERE BDJB_PJLX IN ({','.join(qn(x) for x in [b['visible_name'] for b in bills.values()])});
    DELETE dbo.SYSWSPACE WHERE SYSWSPACE_BH IN ({','.join(qn(x) for x in ws if x != ROOT_BH)});
    DELETE dbo.SYS_TbColumn WHERE 表名 IN ({','.join(qn(x) for x in visible + qnames)});
    DELETE dbo.IOBDZD WHERE IOBDZD_MC IN ({','.join(qn(x) for x in [b['visible_name'] for b in bills.values()])});
    DELETE dbo.IOJCBDZD WHERE IOJCBDZD_BH IN ({','.join(qn(x) for x in routes)});
{chr(10).join(drop)}
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT N'ROLLBACK_COMPLETE' AS RollbackStatus;
"""


def render_legacy_repair(
    expected_database: str | None = None,
    expected_server: str | None = None,
) -> tuple[str, str]:
    names = "N'资产车间',N'资产线体',N'资产供应商',N'资产状态',N'资产类型',N'资产档案'"
    sql = render_header(expected_database, expected_server) + f"""SELECT 表名,字段名,类型,控件 FROM dbo.SYS_TbColumn WHERE 表名 IN ({names}) AND (类型<>N'S' OR 控件<>N'E') ORDER BY 表名,顺序;
IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn WHERE 表名 IN ({names}) AND (类型<>N'S' OR 控件<>N'E'))<>6 THROW 56400,N'资产基础资料旧元数据数量不是已确认的 6 条，拒绝盲改。',1;
BEGIN TRANSACTION;
BEGIN TRY
    UPDATE dbo.SYS_TbColumn SET 类型=N'S',控件=N'E'
    WHERE 表名 IN ({names}) AND (类型<>N'S' OR 控件<>N'E');
    IF @@ROWCOUNT<>6 THROW 56401,N'资产基础资料 S/E 修复影响行数不是 6。',1;
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT N'LEGACY_SE_REPAIR_COMPLETE' AS RepairStatus;
"""
    rollback = render_header(expected_database, expected_server) + f"""IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn WHERE 表名 IN ({names}) AND 类型=N'S' AND 控件=N'E' AND 字段名 IN (N'EAMZCDA_TCRQ',N'EAMZWGYS_YXBZ',N'EAMZWGYS_CREATETIME',N'EAMZCLX_SYNX',N'EAMZCLX_SFFJ',N'EAMZCLX_SFQZBY'))
BEGIN TRANSACTION;
BEGIN TRY
    UPDATE dbo.SYS_TbColumn SET 类型=CASE WHEN 字段名 IN (N'EAMZWGYS_YXBZ',N'EAMZCLX_SFFJ',N'EAMZCLX_SFQZBY') THEN N'C' WHEN 字段名 IN (N'EAMZCLX_SYNX') THEN N'N' ELSE N'D' END,
        控件=CASE WHEN 字段名 IN (N'EAMZWGYS_YXBZ',N'EAMZCLX_SFFJ',N'EAMZCLX_SFQZBY') THEN N'C' ELSE N'E' END
    WHERE 表名 IN ({names}) AND 字段名 IN (N'EAMZCDA_TCRQ',N'EAMZWGYS_YXBZ',N'EAMZWGYS_CREATETIME',N'EAMZCLX_SYNX',N'EAMZCLX_SFFJ',N'EAMZCLX_SFQZBY') AND 类型=N'S' AND 控件=N'E';
    IF @@ROWCOUNT<>6 THROW 56402,N'资产基础资料 S/E 回滚影响行数不是 6。',1;
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
END;
SELECT N'LEGACY_SE_ROLLBACK_COMPLETE' AS RollbackStatus;
"""
    return sql, rollback


def pjlx_repair_targets(bills: dict[str, dict[str, Any]]) -> list[tuple[str, str, str]]:
    targets: list[tuple[str, str, str]] = []
    for bill in bills.values():
        targets.append((bill["visible_name"], bill["header"] + "_PJLX", "E"))
        targets.append((bill["visible_name"] + "查询", bill["header"] + "_PJLX", "E"))
    # These two existing inspection bills are part of the same EAM CBill
    # contract. Preserve the already-correct template maintenance row so the
    # repair can assert and restore the exact pre-change state.
    targets.extend([
        ("点检模板", "EAMDJMB1_PJLX", "S"),
        ("点检模板查询", "EAMDJMB1_PJLX", "E"),
        ("点检记录单", "EAMDJJLD1_PJLX", "E"),
        ("点检记录单查询", "EAMDJJLD1_PJLX", "E"),
    ])
    return targets


def render_pjlx_control_repair(
    bills: dict[str, dict[str, Any]],
    expected_database: str | None = None,
    expected_server: str | None = None,
) -> tuple[str, str]:
    targets = pjlx_repair_targets(bills)
    values = ",\n".join(f"    ({qn(table_name)},{qn(field_name)},{qn(old_control)})" for table_name, field_name, old_control in targets)
    expected_total = len(targets)
    expected_updates = sum(1 for _, _, old_control in targets if old_control == "E")
    table_values = f"""DECLARE @Expected TABLE (表名 nvarchar(100) NOT NULL,字段名 nvarchar(100) NOT NULL,旧控件 nvarchar(20) NOT NULL);
INSERT @Expected (表名,字段名,旧控件) VALUES
{values};
IF (SELECT COUNT(*) FROM @Expected)<>{expected_total} THROW 56500,N'PJLX 修复契约行数不符。',1;
IF (SELECT COUNT(*) FROM dbo.SYS_TbColumn m JOIN @Expected e ON e.表名=m.表名 AND e.字段名=m.字段名)<>{expected_total} THROW 56501,N'PJLX 目标元数据行不完整或重复，拒绝修复。',1;
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn m JOIN @Expected e ON e.表名=m.表名 AND e.字段名=m.字段名 WHERE m.类型<>N'S' OR m.控件<>e.旧控件) THROW 56502,N'PJLX 目标行当前值与已确认旧值不一致，拒绝盲改。',1;
SELECT m.表名,m.PO,m.字段名,m.类型,m.控件,e.旧控件 AS 预期旧控件 FROM dbo.SYS_TbColumn m JOIN @Expected e ON e.表名=m.表名 AND e.字段名=m.字段名 ORDER BY m.表名,m.PO,m.字段名;"""
    repair = render_header(expected_database, expected_server) + table_values + f"""
BEGIN TRANSACTION;
BEGIN TRY
    IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn m JOIN @Expected e ON e.表名=m.表名 AND e.字段名=m.字段名 WHERE m.类型<>N'S' OR m.控件<>e.旧控件) THROW 56503,N'PJLX 事务内旧值发生变化，拒绝修复。',1;
    UPDATE m SET 控件=N'S'
    FROM dbo.SYS_TbColumn m JOIN @Expected e ON e.表名=m.表名 AND e.字段名=m.字段名
    WHERE e.旧控件=N'E' AND m.控件=N'E';
    IF @@ROWCOUNT<>{expected_updates} THROW 56504,N'PJLX 控件修复影响行数不符。',1;
    IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn m JOIN @Expected e ON e.表名=m.表名 AND e.字段名=m.字段名 WHERE m.控件<>N'S') THROW 56505,N'PJLX 修复后仍存在非 S 控件。',1;
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT N'PJLX_CONTROL_REPAIR_COMPLETE' AS RepairStatus;
"""
    rollback = render_header(expected_database, expected_server) + table_values + f"""
IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn m JOIN @Expected e ON e.表名=m.表名 AND e.字段名=m.字段名 WHERE m.控件<>N'S') THROW 56510,N'PJLX 回滚前目标行不是全 S，拒绝回滚。',1;
BEGIN TRANSACTION;
BEGIN TRY
    UPDATE m SET 控件=e.旧控件
    FROM dbo.SYS_TbColumn m JOIN @Expected e ON e.表名=m.表名 AND e.字段名=m.字段名
    WHERE e.旧控件=N'E';
    IF @@ROWCOUNT<>{expected_updates} THROW 56511,N'PJLX 控件回滚影响行数不符。',1;
    IF EXISTS (SELECT 1 FROM dbo.SYS_TbColumn m JOIN @Expected e ON e.表名=m.表名 AND e.字段名=m.字段名 WHERE m.类型<>N'S' OR m.控件<>e.旧控件) THROW 56512,N'PJLX 回滚后未恢复精确旧值。',1;
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT N'PJLX_CONTROL_ROLLBACK_COMPLETE' AS RollbackStatus;
"""
    return repair, rollback


def render_readme(
    basic: dict[str, dict[str, Any]],
    bills: dict[str, dict[str, Any]],
    expected_database: str | None = None,
    expected_server: str | None = None,
) -> str:
    database_text = expected_database or "<未指定>"
    server_text = expected_server or "<未指定>"
    return f"""# EAM 资产及备件管理数据库交付包

目标：`{database_text}` / `{server_text}`

本包来自 ER 图，包含 8 个 BTYPE=1 基础资料和 11 组 IOBDZD 主从单据。新建元数据中物理 `date`/`datetime`/`datetime2` 字段为 `类型=D`，其他字段为 `类型=S`；普通字段 `控件=E`、`*_PJLX` 凭证类型字段 `控件=S`、`标识=NULL`，可见列宽按标签完整显示宽度生成（3 个汉字 `840`、4 个汉字 `1125`），RID 在目标库当前最大值后运行时分配。

目标库已有通用“物料”工作区，因此 ER 图中的 `EAMWL` 表单使用业务限定名“资产物料”；该名称已同步到 `IOJCBDZD`、`SYS_TbColumn`、工作区、帮助和验证脚本，未覆盖既有“物料”功能。

主从单据固定生成：独立 `<单据名>查询` 字段集、PJLX/SHBZ/ZDR/SHR/ZY 等 CBill 运行字段、审核/撤审 BDJB、工作区权限、销售订单同参数的 7 个 sysmenu 按钮和交叉查询验证。

ER 图中没有供应商编码、库存数量等字段，且部分外键字段长度不一致。本包只建立证据充分且长度兼容的外键；未证明的关系保留字段并在 `contract.json`/验证结果中不冒充已闭合关系。

## 执行顺序

1. `preflight.sql`
2. `forward.sql`
3. `verification.sql`
4. `crud-test.sql`
5. `legacy-se-repair.sql`（把已存在资产基础资料的 6 条旧 C/N/D 元数据精确统一为 S/E）
6. `pjlx-control-repair.sql`（将 11 组新建单据及点检模板/点检记录单的 26 行 PJLX 元数据统一为 `控件=S`；当前基线已有 1 行正确，因此本次预期更新 25 行）

只在确认没有业务数据且明确需要撤销时执行 `rollback-preflight.sql`（如存在）和 `rollback.sql`；`legacy-se-rollback.sql` 和 `pjlx-control-rollback.sql` 只用于对应修复的补偿。
"""


def build_contract(
    er_path: Path,
    expected_database: str | None = None,
    expected_server: str | None = None,
) -> dict[str, Any]:
    er = parse_tables(er_path)
    basic, bills = make_tables(er)
    maintain, query = make_metadata(basic, bills)
    validate_metadata_closure(basic, bills, maintain, query)
    return {
        "source": str(er_path),
        "expected_database": expected_database,
        "expected_server": expected_server,
        "schema": SCHEMA,
        "defaults": {"metadata_type": "D for date/datetime/datetime2, otherwise S", "metadata_control": "E except PJLX=S", "ordinary_metadata_control": "E", "pjlx_control": "S", "number_format": "YYMM####", "column_width": "metadata_width.py", "rid": "runtime-max-plus-offset"},
        "basic_forms": list(basic.values()), "bills": list(bills.values()), "maintain_metadata": maintain, "query_metadata": query,
        "er_notes": [
            "EAMWLGYS 未提供供应商编码，保留 ER 字段，不虚构供应商列。",
            "EAMSSKCXX 未提供库存数量，且物料/仓库编码长度与父表不一致，不添加伪造数量或不兼容外键。",
            "动态表单只建立与字段长度和关系语义均兼容的外键。",
        ],
    }


def generate(
    er_path: Path,
    output: Path,
    force: bool = False,
    expected_database: str | None = None,
    expected_server: str | None = None,
) -> None:
    contract = build_contract(er_path, expected_database, expected_server)
    basic = {x["table"]: x for x in contract["basic_forms"]}
    bills = {x["visible_name"]: x for x in contract["bills"]}
    maintain = contract["maintain_metadata"]
    query = contract["query_metadata"]
    if output.exists() and any(output.iterdir()) and not force:
        raise ValueError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "contract.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "preflight.sql").write_text(render_preflight(basic, bills, expected_database, expected_server), encoding="utf-8")
    (output / "forward.sql").write_text(render_forward(basic, bills, maintain, query, expected_database, expected_server), encoding="utf-8")
    (output / "verification.sql").write_text(render_verification(basic, bills, maintain, query, expected_database, expected_server), encoding="utf-8")
    (output / "crud-test.sql").write_text(render_crud(basic, bills, expected_database, expected_server), encoding="utf-8")
    (output / "rollback.sql").write_text(render_rollback(basic, bills, expected_database, expected_server), encoding="utf-8")
    legacy, legacy_rollback = render_legacy_repair(expected_database, expected_server)
    (output / "legacy-se-repair.sql").write_text(legacy, encoding="utf-8")
    (output / "legacy-se-rollback.sql").write_text(legacy_rollback, encoding="utf-8")
    pjlx_repair, pjlx_rollback = render_pjlx_control_repair(bills, expected_database, expected_server)
    (output / "pjlx-control-repair.sql").write_text(pjlx_repair, encoding="utf-8")
    (output / "pjlx-control-rollback.sql").write_text(pjlx_rollback, encoding="utf-8")
    (output / "README.md").write_text(render_readme(basic, bills, expected_database, expected_server), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--er-svg", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-database", help="confirmed target database; omit only to generate a review-blocked pack")
    parser.add_argument("--expected-server", help="confirmed @@SERVERNAME; omit only to generate a review-blocked pack")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv or sys.argv[1:])
    try:
        if not args.er_svg.is_file():
            raise ValueError(f"ER SVG not found: {args.er_svg}")
        generate(args.er_svg, args.output_dir, args.force, args.expected_database, args.expected_server)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Generated EAM asset suite pack in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
