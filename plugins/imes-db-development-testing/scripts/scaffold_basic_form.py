#!/usr/bin/env python3
"""Generate a reviewable SQL pack for one IMES BTYPE=1 basic-data form.

The generator consumes a small, reviewed JSON contract and never connects to SQL
Server or executes SQL. It is deliberately fail-closed: unsafe identifiers,
ambiguous keys, missing labels, unsupported SQL types, and incomplete workspace
information stop generation before any artifact is written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from metadata_width import label_column_width
except ImportError:  # pragma: no cover
    from .metadata_width import label_column_width

META_COLUMNS = [
    "表名", "PO", "字段名", "主键", "RMark", "显示名", "标签名", "不控", "显示", "列宽", "顺序",
    "合计", "按钮", "只读", "表头", "颜色值", "新增", "更新", "置空", "筛选", "必填", "合并",
    "对齐", "切换", "GLZD", "LMark", "类型", "帮助", "标识", "默认值", "管道字符", "关键字段",
    "左坐标", "顶坐标", "宽度", "高度", "admin", "优先级", "左对齐", "右对齐", "顶对齐", "底对齐",
    "控件", "RID",
]

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TYPE_RE = re.compile(
    r"^(?:bigint|int|smallint|tinyint|bit|date|datetime|datetime2|"
    r"(?:var)?char\((?:MAX|[1-9][0-9]*)\)|decimal\([1-9][0-9]*,[0-9]+\))$",
    re.I,
)
IDENTITY_RE = re.compile(r"\s+identity\s*\(\s*[0-9]+\s*,\s*[0-9]+\s*\)$", re.I)
DEFAULT_RE = re.compile(r"^\((?:-?[0-9]+|N?'[^']*'|GETDATE\(\)|SYSDATETIME\(\))\)$", re.I)

def resolve_column_width(field: dict[str, Any]) -> int:
    label = field.get("label") or "FID"
    minimum = label_column_width(label)
    requested = field.get("column_width", field.get("width"))
    if requested in (None, ""):
        return minimum
    try:
        width = int(requested)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field['name']}: column_width must be an integer") from exc
    if width <= 0:
        raise ValueError(f"{field['name']}: column_width must be positive")
    if not field.get("identity") and width < minimum:
        raise ValueError(
            f"{field['name']}: column_width {width} is smaller than label minimum {minimum}; "
            "first-view labels must be fully visible"
        )
    return width


def qi(value: str) -> str:
    if not IDENT_RE.fullmatch(value):
        raise ValueError(f"unsafe identifier: {value!r}")
    return f"[{value}]"


def qmeta(value: str) -> str:
    """Quote one of the legacy Chinese SYS_TbColumn column names.

    Business/schema identifiers remain ASCII-only and go through ``qi``.
    SYS_TbColumn is an old IMES table whose column names are intentionally
    Chinese, so it gets a separate allow-list rather than weakening the
    identifier rule for every generated object.
    """
    if value not in META_COLUMNS:
        raise ValueError(f"unsupported SYS_TbColumn metadata column: {value!r}")
    escaped = value.replace("]", "]]")
    return "[" + escaped + "]"


def qn(value: str) -> str:
    return "N'" + value.replace("'", "''") + "'"


def qs(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sql_value(value: Any, unicode: bool = True) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return qn(str(value)) if unicode else qs(str(value))


def base_type(sql_type: str) -> str:
    return re.sub(r"\s+identity\s*\([^)]*\)$", "", sql_type, flags=re.I).lower()


def is_numeric(t: str) -> bool:
    return t.startswith(("int", "bigint", "smallint", "tinyint", "decimal"))


def infer_meta_type(field: dict[str, Any]) -> str:
    expected = "D" if base_type(str(field.get("sql", ""))) in {"date", "datetime", "datetime2"} else "S"
    explicit = field.get("type")
    if explicit is not None and str(explicit).strip().upper() != expected:
        raise ValueError(
            f"field {field.get('name', '<unknown>')}: metadata type must be {expected} "
            "for its confirmed physical SQL type"
        )
    return expected


def infer_control(field: dict[str, Any], meta_type: str) -> str:
    explicit = field.get("control")
    if explicit:
        normalized = str(explicit).strip().upper()
        if normalized != "E":
            raise ValueError(
                f"field {field.get('name', '<unknown>')}: new metadata controls must be E; "
                "do not infer special controls from SQL type"
            )
        return normalized
    return "E"


def normalize(contract: dict[str, Any]) -> dict[str, Any]:
    required = ["expected_database", "expected_server", "table", "visible_name", "route", "workspace", "fields"]
    missing = [key for key in required if key not in contract]
    if missing:
        raise ValueError("missing contract keys: " + ", ".join(missing))
    schema = contract.get("schema", "dbo")
    for value in [schema, contract["table"]]:
        if not IDENT_RE.fullmatch(str(value)):
            raise ValueError(f"unsafe identifier: {value!r}")
    route = contract["route"]
    if int(route.get("btype", 1)) != 1:
        raise ValueError("this generator only supports route.btype=1")
    for key in ["bh", "vkey", "byzd"]:
        if not route.get(key):
            raise ValueError(f"route.{key} is required")
    workspace = contract["workspace"]
    for key in ["root_bh", "root_name", "leaf_bh", "leaf_name", "loc"]:
        if not workspace.get(key):
            raise ValueError(f"workspace.{key} is required")
    if not re.fullmatch(r"[0-9]{4,}$", str(workspace["leaf_bh"])):
        raise ValueError("workspace.leaf_bh must be numeric")

    fields = contract["fields"]
    if not fields:
        raise ValueError("fields must not be empty")
    names: set[str] = set()
    pk_fields: list[dict[str, Any]] = []
    unique_fields: list[dict[str, Any]] = []
    for index, field in enumerate(fields):
        name = field.get("name")
        sql = str(field.get("sql", ""))
        if not name or not IDENT_RE.fullmatch(name):
            raise ValueError(f"field {index}: unsafe or missing name")
        if name in names:
            raise ValueError(f"duplicate field: {name}")
        names.add(name)
        if not TYPE_RE.fullmatch(re.sub(r"\s+identity\s*\([^)]*\)$", "", sql, flags=re.I)):
            raise ValueError(f"field {name}: unsupported sql type {sql!r}")
        if "identity" in field and field["identity"] and not IDENTITY_RE.search(sql):
            raise ValueError(f"field {name}: identity=true requires identity(...) in sql")
        if field.get("default") is not None and not DEFAULT_RE.fullmatch(str(field["default"])):
            raise ValueError(f"field {name}: unsafe default expression")
        prefix = name.split("_", 1)[0]
        if prefix != contract["table"]:
            raise ValueError(f"field {name}: legacy BTYPE=1 prefix must match table {contract['table']}")
        if field.get("pk"):
            pk_fields.append(field)
        if field.get("unique"):
            unique_fields.append(field)
        if not field.get("identity") and not field.get("label"):
            raise ValueError(f"field {name}: label is required for visible/non-identity fields")
        if field.get("help") and not field.get("glzd"):
            raise ValueError(f"field {name}: help requires glzd")
        if field.get("glzd") and not field.get("help"):
            raise ValueError(f"field {name}: glzd requires help")
    if len(pk_fields) != 1:
        raise ValueError("exactly one pk field is required")
    if not unique_fields:
        raise ValueError("at least one unique field is required for BTYPE=1 CRUD smoke test")
    if route["vkey"] not in names:
        raise ValueError("route.vkey must name a field")
    if route["vkey"] == pk_fields[0]["name"]:
        raise ValueError("route.vkey must be a business key, not the identity primary key")
    byzd = [x.strip() for x in str(route["byzd"]).split(",") if x.strip()]
    if not byzd or any(x not in names for x in byzd):
        raise ValueError("route.byzd must be a comma-separated list of existing fields")
    for field in fields:
        field["meta_type"] = infer_meta_type(field)
        field["control"] = infer_control(field, field["meta_type"])
        field["column_width"] = resolve_column_width(field)
    contract["schema"] = schema
    return contract


def table_ref(c: dict[str, Any]) -> str:
    return f"{qi(c['schema'])}.{qi(c['table'])}"


def render_columns(c: dict[str, Any]) -> str:
    lines: list[str] = []
    for field in c["fields"]:
        sql = field["sql"]
        nullable = "NULL" if field.get("nullable", True) and not field.get("pk") else "NOT NULL"
        if field.get("identity") and "identity" not in sql.lower():
            sql += " IDENTITY(1,1)"
        default = f" CONSTRAINT {qi('DF_' + c['table'] + '_' + field['name'].split('_', 1)[-1])} DEFAULT {field['default']}" if field.get("default") else ""
        lines.append(f"        {qi(field['name'])} {sql} {nullable}{default}")
    pk = next(field for field in c["fields"] if field.get("pk"))
    lines.append(f"        CONSTRAINT {qi('PK_' + c['table'])} PRIMARY KEY CLUSTERED ({qi(pk['name'])})")
    for field in c["fields"]:
        if field.get("unique"):
            lines.append(f"        CONSTRAINT {qi('UQ_' + c['table'] + '_' + field['name'].split('_', 1)[-1])} UNIQUE ({qi(field['name'])})")
    for field in c["fields"]:
        ref = field.get("references")
        if ref:
            rt = ref.get("table")
            rc = ref.get("column")
            if not rt or not rc or not IDENT_RE.fullmatch(rt) or not IDENT_RE.fullmatch(rc):
                raise ValueError(f"field {field['name']}: invalid references")
            lines.append(f"        CONSTRAINT {qi('FK_' + c['table'] + '_' + field['name'].split('_', 1)[-1])} FOREIGN KEY ({qi(field['name'])}) REFERENCES {qi(c['schema'])}.{qi(rt)}({qi(rc)})")
    return ",\n".join(lines)


def meta_tuple(c: dict[str, Any], field: dict[str, Any], index: int) -> str:
    hidden = bool(field.get("identity"))
    label = field.get("label") or "FID"
    display = 0 if hidden else 1
    column_width = int(field.get("column_width", resolve_column_width(field)))
    control_width = int(field.get("control_width", field.get("width", 1200)))
    left = 0 if hidden else 75
    top = 0 if hidden else 40 + index * 30
    height = 0 if hidden else 22
    required = 0 if hidden else int(field.get("required", not field.get("nullable", True)))
    readonly = int(field.get("readonly", hidden))
    key_field = int(field.get("key_field", bool(field.get("unique") or field.get("pk"))))
    values: list[Any] = [
        c["visible_name"], "1", field["name"], int(bool(field.get("pk"))), None, label, label, 0, display, column_width, index,
        0, 0, readonly, 0, None, 1, 1, 1, int(field.get("filter", 0)), required, 1, 7, 0,
        field.get("glzd"), None, field["meta_type"], field.get("help"), None, field.get("metadata_default"), None,
        key_field, left, top, control_width, height, "1", 0, None, None, None, None, field["control"], f"@RIDBase+{index}",
    ]
    rendered: list[str] = []
    for position, value in enumerate(values):
        if value is None:
            rendered.append("NULL")
        elif position in {0, 1, 2, 4, 5, 6, 24, 25, 26, 27, 28, 29, 30, 36, 38, 39, 40, 41, 42}:
            rendered.append(qn(str(value)))
        else:
            rendered.append(str(value))
    return "(" + ",".join(rendered) + ")"


def workspace_rows(c: dict[str, Any]) -> list[tuple[str, str | None, str, int, int, int]]:
    w = c["workspace"]
    rows: list[tuple[str, str | None, str, int, int, int]] = []
    if w.get("create_root"):
        rows.append((str(w["root_bh"]), None, str(w["root_name"]), 0, 2, 0))
    rows.append((str(w["leaf_bh"]), str(w["root_bh"]), str(w["leaf_name"]), 1, 3, 0))
    operations = w.get("operations", {"10": "新增", "20": "编辑", "80": "删除"})
    for suffix, op_name in operations.items():
        rows.append((str(w["leaf_bh"]) + str(suffix), str(w["leaf_bh"]), str(w["leaf_name"]) + str(op_name), 1, 4, 1))
    return rows


def render_header(c: dict[str, Any], xact: bool = False) -> str:
    text = "SET ANSI_NULLS ON;\nSET QUOTED_IDENTIFIER ON;\nSET NOCOUNT ON;\n"
    if xact:
        text += "SET XACT_ABORT ON;\n"
    text += f"IF DB_NAME() <> {qn(c['expected_database'])} THROW 53000, N'目标数据库不匹配。', 1;\n"
    text += f"IF @@SERVERNAME <> {qn(c['expected_server'])} THROW 53001, N'目标实例不匹配。', 1;\n"
    return text


def render_preflight(c: dict[str, Any]) -> str:
    t = table_ref(c)
    w = c["workspace"]
    ws_codes = ",".join(qn(row[0]) for row in workspace_rows(c))
    return render_header(c) + f"""IF OBJECT_ID(N'{c['schema']}.{c['table']}',N'U') IS NOT NULL THROW 53002,N'目标物理表已存在，拒绝覆盖。',1;
IF OBJECT_ID(N'{c['schema']}.IOJCBDZD',N'U') IS NULL OR OBJECT_ID(N'{c['schema']}.SYS_TbColumn',N'U') IS NULL OR OBJECT_ID(N'{c['schema']}.SYSWSPACE',N'U') IS NULL THROW 53003,N'缺少 IMES 元数据基础表。',1;
IF EXISTS (SELECT 1 FROM {qi(c['schema'])}.{qi('IOJCBDZD')} WHERE IOJCBDZD_BH={qn(c['route']['bh'])}) THROW 53004,N'IOJCBDZD 编号已存在。',1;
IF EXISTS (SELECT 1 FROM {qi(c['schema'])}.{qi('IOJCBDZD')} WHERE IOJCBDZD_MC={qn(c['visible_name'])}) THROW 53005,N'IOJCBDZD 可见名称已存在。',1;
IF EXISTS (SELECT 1 FROM {qi(c['schema'])}.{qi('SYS_TbColumn')} WHERE 表名={qn(c['visible_name'])}) THROW 53006,N'SYS_TbColumn 可见名称已存在。',1;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'{c['schema']}.SYS_TbColumn') AND name=N'nID' AND is_identity=1) THROW 53008,N'SYS_TbColumn.nID 必须是 identity。',1;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'{c['schema']}.SYS_TbColumn') AND name=N'RID') THROW 53009,N'SYS_TbColumn 缺少 RID。',1;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'{c['schema']}.SYSWSPACE') AND name=N'admin') THROW 53010,N'SYSWSPACE 缺少 admin 权限边界。',1;
IF EXISTS (SELECT 1 FROM {qi(c['schema'])}.{qi('SYSWSPACE')} WHERE SYSWSPACE_BH IN ({ws_codes})) THROW 53011,N'工作区编号冲突。',1;
""" + (f"IF NOT EXISTS (SELECT 1 FROM {qi(c['schema'])}.{qi('SYSWSPACE')} WHERE SYSWSPACE_BH={qn(w['root_bh'])}) THROW 53012,N'工作区父节点不存在。',1;\n" if not w.get("create_root") else f"IF EXISTS (SELECT 1 FROM {qi(c['schema'])}.{qi('SYSWSPACE')} WHERE SYSWSPACE_BH={qn(w['root_bh'])}) THROW 53013,N'要求创建的工作区根节点已存在。',1;\n") + "SELECT N'PREFLIGHT_PASS' AS Status;\n"


def render_forward(c: dict[str, Any]) -> str:
    s = render_header(c, True)
    t = table_ref(c)
    meta_cols = ",".join(qmeta(x) for x in META_COLUMNS)
    tuples = ",\n".join("    " + meta_tuple(c, field, index) for index, field in enumerate(c["fields"]))
    route = c["route"]
    rows = workspace_rows(c)
    ws_values = ",\n".join(
        f"    ({qs(c['workspace']['loc'])},{qn(bh)},{'NULL' if pbh is None else qn(pbh)},{qn(name)},{mx},{js},1,0,{btn},1)"
        for bh, pbh, name, mx, js, btn in rows
    )
    s += f"""BEGIN TRANSACTION;
BEGIN TRY
    CREATE TABLE {t}
    (
{render_columns(c)}
    );
    INSERT {qi(c['schema'])}.{qi('IOJCBDZD')}
    (IOJCBDZD_BH,IOJCBDZD_BTYPE,IOJCBDZD_MC,IOJCBDZD_Table,IOJCBDZD_Vkey,IOJCBDZD_BYZD,IOJCBDZD_JSZD,IOJCBDZD_YXBZZD,IOJCBDZD_Filter,IOJCBDZD_BZMC,IOJCBDZD_BZBH,IOJCBDZD_TOP,IOJCBDZD_SXXS,IOJCBDZD_LBTABLE,IOJCBDZD_LBNAME)
    VALUES ({qn(route['bh'])},N'1',{qn(c['visible_name'])},{qn(c['table'])},{qn(route['vkey'])},{qn(route['byzd'])},NULL,NULL,NULL,{qn(c['visible_name'])},{qn(route['bh'])},0,0,NULL,NULL);
    DECLARE @RIDBase int = ISNULL((SELECT MAX(RID) FROM {qi(c['schema'])}.{qi('SYS_TbColumn')}),0)+1;
    CREATE TABLE #NewMeta(nID int NOT NULL);
    INSERT {qi(c['schema'])}.{qi('SYS_TbColumn')} ({meta_cols})
    OUTPUT inserted.nID INTO #NewMeta(nID)
    VALUES
{tuples};
    DECLARE @sql nvarchar(max), @metaSet nvarchar(max);
    SELECT @metaSet=STUFF((SELECT N','+QUOTENAME(c.name)+N'=1' FROM sys.columns c WHERE c.object_id=OBJECT_ID(N'{c['schema']}.SYS_TbColumn') AND c.system_type_id=104 AND c.column_id>(SELECT column_id FROM sys.columns WHERE object_id=OBJECT_ID(N'{c['schema']}.SYS_TbColumn') AND name=N'RID') ORDER BY c.column_id FOR XML PATH(''),TYPE).value('.','nvarchar(max)'),1,1,N'');
    IF NULLIF(@metaSet,N'') IS NOT NULL BEGIN SET @sql=N'UPDATE m SET '+@metaSet+N' FROM {qi(c['schema'])}.{qi('SYS_TbColumn')} m JOIN #NewMeta n ON n.nID=m.nID;'; EXEC sys.sp_executesql @sql; END;
    CREATE TABLE #NewWorkspace(SYSWSPACE_ID int NOT NULL);
    INSERT {qi(c['schema'])}.{qi('SYSWSPACE')} (SYSWSPACE_LOC,SYSWSPACE_BH,SYSWSPACE_PBH,SYSWSPACE_MC,SYSWSPACE_MX,SYSWSPACE_JS,SYSWSPACE_JDBZ,SYSWSPACE_QCYWBZ,SYSWSPACE_BTN,admin)
    OUTPUT inserted.SYSWSPACE_ID INTO #NewWorkspace(SYSWSPACE_ID)
    VALUES
{ws_values};
    SELECT @sql=NULL;
    SELECT @sql=STUFF((SELECT N','+QUOTENAME(c.name)+N'='+CASE WHEN c.system_type_id IN (167,175,231,239) THEN N'N''1''' ELSE N'1' END FROM sys.columns c WHERE c.object_id=OBJECT_ID(N'{c['schema']}.SYSWSPACE') AND (c.name=N'admin' OR (c.system_type_id=104 AND c.column_id>ISNULL((SELECT column_id FROM sys.columns WHERE object_id=OBJECT_ID(N'{c['schema']}.SYSWSPACE') AND name=N'admin'),0))) AND c.name<>N'SYSWSPACE_ID' ORDER BY c.column_id FOR XML PATH(''),TYPE).value('.','nvarchar(max)'),1,1,N'');
    IF NULLIF(@sql,N'') IS NOT NULL BEGIN SET @metaSet=@sql; SET @sql=N'UPDATE w SET '+@metaSet+N' FROM {qi(c['schema'])}.{qi('SYSWSPACE')} w JOIN #NewWorkspace n ON n.SYSWSPACE_ID=w.SYSWSPACE_ID;'; EXEC sys.sp_executesql @sql; END;
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT N'FORWARD_COMPLETE' AS DeployStatus;
"""
    return s


def render_verification(c: dict[str, Any]) -> str:
    t = table_ref(c)
    meta_table = f"{qi(c['schema'])}.{qi('SYS_TbColumn')}"
    meta_name = qmeta("表名")
    meta_field = qmeta("字段名")
    meta_marker = qmeta("标识")
    meta_type = qmeta("类型")
    meta_control = qmeta("控件")
    names = ",".join(qn(field["name"]) for field in c["fields"])
    ws_codes = ",".join(qn(row[0]) for row in workspace_rows(c))
    expected_meta = len(c["fields"])
    return render_header(c) + f"""IF OBJECT_ID(N'{c['schema']}.{c['table']}',N'U') IS NULL THROW 53100,N'物理表不存在。',1;
IF (SELECT COUNT(*) FROM sys.columns WHERE object_id=OBJECT_ID(N'{c['schema']}.{c['table']}')) <> {len(c['fields'])} THROW 53101,N'物理字段数量不符。',1;
IF (SELECT COUNT(*) FROM {qi(c['schema'])}.{qi('IOJCBDZD')} WHERE IOJCBDZD_BH={qn(c['route']['bh'])} AND IOJCBDZD_BTYPE=N'1' AND IOJCBDZD_MC={qn(c['visible_name'])}) <> 1 THROW 53102,N'BTYPE=1 路由不唯一。',1;
IF (SELECT COUNT(*) FROM {meta_table} WHERE {meta_name}={qn(c['visible_name'])}) <> {expected_meta} THROW 53103,N'SYS_TbColumn 行数不符。',1;
 IF EXISTS (SELECT 1 FROM {meta_table} WHERE {meta_name}={qn(c['visible_name'])} GROUP BY {qmeta('PO')} HAVING MIN(TRY_CONVERT(int,{qmeta('顺序')}))<>0 OR MAX(TRY_CONVERT(int,{qmeta('顺序')}))<>COUNT(*)-1 OR COUNT(DISTINCT TRY_CONVERT(int,{qmeta('顺序')}))<>COUNT(*) OR SUM(CASE WHEN TRY_CONVERT(int,{qmeta('顺序')}) IS NULL THEN 1 ELSE 0 END)>0) THROW 53110,N'BTYPE=1 每个表名与 PO 的顺序必须从 0 连续编号。',1;
IF EXISTS (SELECT 1 FROM {meta_table} WHERE {meta_name}={qn(c['visible_name'])} AND {meta_field} NOT IN ({names})) THROW 53104,N'存在多余元数据字段。',1;
IF EXISTS (SELECT 1 FROM {meta_table} WHERE {meta_name}={qn(c['visible_name'])} AND {meta_marker} IS NOT NULL AND LTRIM(RTRIM({meta_marker}))<>N'') THROW 53105,N'标识非空，可能触发 FF_BS。',1;
IF EXISTS (SELECT 1 FROM {meta_table} WHERE {meta_name}={qn(c['visible_name'])} AND COALESCE({meta_control},N'')<>N'E') THROW 53106,N'新生成元数据控件必须全部为 E（生成契约值；UForm1 的 LoadGridSet 不读该列）。',1;
IF EXISTS (SELECT 1 FROM {meta_table} WHERE {meta_name}={qn(c['visible_name'])} AND TRY_CONVERT(int,{qmeta('显示')})=1 AND (TRY_CONVERT(int,{qmeta('列宽')}) IS NULL OR TRY_CONVERT(int,{qmeta('列宽')})<=0)) THROW 53112,N'可见字段列宽必须显式给出正整数：LoadGridSet 对 0 回退到 100，字段名会被截断。',1;
IF EXISTS (
    SELECT 1
    FROM {meta_table} m
    JOIN sys.columns c ON c.object_id=OBJECT_ID(N'{c['schema']}.{c['table']}') AND c.name=m.{meta_field}
    WHERE m.{meta_name}={qn(c['visible_name'])}
      AND COALESCE(m.{meta_type},N'')<>CASE WHEN TYPE_NAME(c.user_type_id) IN (N'date',N'datetime',N'datetime2') THEN N'D' ELSE N'S' END
) THROW 53111,N'新生成元数据类型必须与物理日期类型一致。',1;
IF EXISTS (SELECT 1 FROM {meta_table} m WHERE m.{meta_name}={qn(c['visible_name'])} AND NOT EXISTS (SELECT 1 FROM sys.columns c WHERE c.object_id=OBJECT_ID(N'{c['schema']}.{c['table']}') AND c.name=m.{meta_field})) THROW 53107,N'存在悬空元数据字段。',1;
IF (SELECT COUNT(*) FROM {qi(c['schema'])}.{qi('SYSWSPACE')} WHERE SYSWSPACE_BH IN ({ws_codes})) <> {len(workspace_rows(c))} THROW 53108,N'工作区节点不完整。',1;
IF EXISTS (SELECT 1 FROM {qi(c['schema'])}.{qi('SYSWSPACE')} w WHERE w.SYSWSPACE_BH IN ({ws_codes}) AND w.SYSWSPACE_PBH IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {qi(c['schema'])}.{qi('SYSWSPACE')} p WHERE p.SYSWSPACE_BH=w.SYSWSPACE_PBH)) THROW 53109,N'工作区父节点悬空。',1;
SELECT {", ".join(qi(field['name']) for field in c['fields'])} FROM {t} WHERE 1=0;
SELECT N'VERIFICATION_PASS' AS VerificationStatus;
"""


def test_literal(field: dict[str, Any]) -> str:
    if "test_value" not in field:
        raise ValueError(f"field {field['name']}: test_value is required for CRUD generation")
    value = field["test_value"]
    t = base_type(field["sql"]).lower()
    if t == "bit":
        if value not in (0, 1, True, False, "0", "1"):
            raise ValueError(f"field {field['name']}: bit test_value must be 0/1")
        return "1" if str(value) in {"1", "True", "true"} else "0"
    if is_numeric(t):
        if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", str(value)):
            raise ValueError(f"field {field['name']}: numeric test_value required")
        return str(value)
    return qn(str(value))


def render_crud(c: dict[str, Any]) -> str:
    t = table_ref(c)
    insert_fields = [field for field in c["fields"] if not field.get("identity") and "test_value" in field]
    if not insert_fields:
        raise ValueError("at least one non-identity test_value is required")
    cols = ",".join(qi(f["name"]) for f in insert_fields)
    vals = ",".join(test_literal(f) for f in insert_fields)
    unique = next(f for f in c["fields"] if f.get("unique"))
    unique_value = test_literal(unique)
    update_field = next((f for f in insert_fields if f["name"] != unique["name"] and not f.get("pk")), unique)
    update_value = test_literal(update_field)
    return render_header(c, True) + f"""DECLARE @residue int;
BEGIN TRANSACTION;
BEGIN TRY
    INSERT INTO {t} ({cols}) VALUES ({vals});
    UPDATE {t} SET {qi(update_field['name'])}={update_value} WHERE {qi(unique['name'])}={unique_value};
    IF @@ROWCOUNT<>1 THROW 53200,N'CRUD 更新行数不为 1。',1;
    SAVE TRANSACTION BeforeDuplicate;
    BEGIN TRY
        INSERT INTO {t} ({cols}) VALUES ({vals});
        THROW 53201,N'重复唯一键未被拒绝。',1;
    END TRY
    BEGIN CATCH
        IF ERROR_NUMBER() NOT IN (2601,2627) THROW;
        IF XACT_STATE()=1 ROLLBACK TRANSACTION BeforeDuplicate;
    END CATCH;
    ROLLBACK TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT @residue=COUNT(*) FROM {t} WHERE {qi(unique['name'])}={unique_value};
IF @residue<>0 THROW 53202,N'CRUD 测试残留数据。',1;
SELECT N'CRUD_PASS' AS CrudStatus;
"""


def render_rollback_preflight(c: dict[str, Any]) -> str:
    t = table_ref(c)
    return render_header(c) + f"""IF OBJECT_ID(N'{c['schema']}.{c['table']}',N'U') IS NULL THROW 53300,N'物理表不存在，拒绝回滚。',1;
IF EXISTS (SELECT 1 FROM {t}) THROW 53301,N'物理表已有业务数据，拒绝回滚。',1;
SELECT N'ROLLBACK_PREFLIGHT_PASS' AS Status;
"""


def render_rollback(c: dict[str, Any]) -> str:
    t = table_ref(c)
    meta_table = f"{qi(c['schema'])}.{qi('SYS_TbColumn')}"
    codes = ",".join(qn(row[0]) for row in workspace_rows(c))
    return render_header(c, True) + f"""IF EXISTS (SELECT 1 FROM {t}) THROW 53400,N'物理表已有业务数据，拒绝回滚。',1;
BEGIN TRANSACTION;
BEGIN TRY
    DELETE FROM {qi(c['schema'])}.{qi('SYSWSPACE')} WHERE SYSWSPACE_BH IN ({codes});
    DELETE FROM {meta_table} WHERE {qmeta("表名")}={qn(c['visible_name'])};
    DELETE FROM {qi(c['schema'])}.{qi('IOJCBDZD')} WHERE IOJCBDZD_BH={qn(c['route']['bh'])} AND IOJCBDZD_MC={qn(c['visible_name'])};
    DROP TABLE {t};
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT N'ROLLBACK_COMPLETE' AS RollbackStatus;
"""


def render_readme(c: dict[str, Any]) -> str:
    return f"""# BTYPE=1 单表基础资料脚本包

- 物理表：`{c['schema']}.{c['table']}`
- 可见名称：`{c['visible_name']}`
- 路由：`{c['route']['bh']}` / BTYPE=1
- 工作区：`{c['workspace']['root_bh']}/{c['workspace']['leaf_bh']}`
- 目标：`{c['expected_database']}` / `{c['expected_server']}`

## 执行顺序

1. `preflight.sql`（只读）
2. `forward.sql`（仅在授权的测试库执行）
3. `verification.sql`（只读）
4. `crud-test.sql`（隔离事务，必须零残留）
5. `rollback-preflight.sql`、`rollback.sql`（仅在明确回滚且无业务数据时）

脚本不包含凭据、不创建 MFC/C++ 资源。新生成元数据中，物理 `date`/`datetime`/`datetime2` 字段固定为 `类型=D`，其他字段固定为 `类型=S`；普通字段控件为 `E`，不从 bit、数值精度、标签或其他 SQL 类型推导特殊控件，标识为 NULL；`BTYPE=1/UForm1` 的 `顺序` 按客户端列下标从 `0..n-1` 生成，动态单据不使用此快速通道；可见字段的 `列宽` 默认按 `标签` 完整显示宽度生成（3 个汉字为 `840`、4 个汉字为 `1125`，ASCII 按半宽单元计算并按 `15` 单位向上取整），显式更窄值会阻断，显式更宽值保留；`RID` 后真实角色列和 `admin` 后工作区权限列默认全部授权为 `1`；如需不同规则，必须有单独的源码证据和修复契约。

推荐执行（连接参数由环境安全注入）：`sqlcmd -S <server> -d <database> -b -f 65001 -i <script.sql>`。
"""


def generate(contract: dict[str, Any], output: Path, force: bool = False) -> None:
    c = normalize(contract)
    if output.exists() and any(output.iterdir()) and not force:
        raise ValueError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "contract.json": json.dumps(c, ensure_ascii=False, indent=2) + "\n",
        "preflight.sql": render_preflight(c),
        "forward.sql": render_forward(c),
        "verification.sql": render_verification(c),
        "crud-test.sql": render_crud(c),
        "rollback-preflight.sql": render_rollback_preflight(c),
        "rollback.sql": render_rollback(c),
        "README.md": render_readme(c),
    }
    for name, content in files.items():
        (output / name).write_text(content, encoding="utf-8", newline="\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
        generate(contract, args.output_dir, args.force)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Generated BTYPE=1 basic-form SQL pack in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
