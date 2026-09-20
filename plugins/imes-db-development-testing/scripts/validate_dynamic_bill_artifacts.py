#!/usr/bin/env python3
"""Static checks for generated IMES dynamic-bill SQL artifacts.

This validator is deliberately SQL-server-free. It catches the common review
mistake where a SYS_TbColumn tuple has a missing value, RID values drift, or a
CRUD INSERT column list does not match its VALUES rows.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

try:
    from metadata_width import label_column_width
except ImportError:  # pragma: no cover
    from .metadata_width import label_column_width

FIXED_HEADER_SUFFIXES = ("_SHBZ", "_PJLX", "_ZDR", "_SHR", "_ZY")
# Proven by the active BCGPEdit implementation.  A custom browse image may
# increase this to max(20, image_width + 8); callers can pass that measurement.
DEFAULT_BROWSE_BUTTON_WIDTH = 20
MIN_LAYOUT_GAP = 10
# IOBDZD_MARK is the document-number prefix consumed by PRD_GETDANHAO.  The
# confirmed convention is exactly two ASCII letters, unique across IOBDZD.
IOBDZD_MARK_RE = re.compile(r"^[A-Za-z]{2}$")


def extract_tuples(text: str) -> list[str]:
    tuples: list[str] = []
    i = 0
    while i < len(text):
        if text[i] != "(":
            i += 1
            continue
        start = i
        depth = 0
        quoted = False
        while i < len(text):
            char = text[i]
            if quoted:
                if char == "'":
                    if i + 1 < len(text) and text[i + 1] == "'":
                        i += 2
                        continue
                    quoted = False
            else:
                if char == "'":
                    quoted = True
                elif char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        tuples.append(text[start : i + 1])
                        break
            i += 1
        i += 1
    return tuples


def split_values(tuple_text: str) -> list[str]:
    body = tuple_text[1:-1]
    values: list[str] = []
    start = 0
    quoted = False
    depth = 0
    i = 0
    while i < len(body):
        char = body[i]
        if quoted:
            if char == "'":
                if i + 1 < len(body) and body[i + 1] == "'":
                    i += 2
                    continue
                quoted = False
        else:
            if char == "'":
                quoted = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                values.append(body[start:i].strip())
                start = i + 1
        i += 1
    values.append(body[start:].strip())
    return values


def _sql_string_value(token: str) -> str:
    """Return the text of a simple SQL string literal, if one is present."""
    value = token.strip()
    if len(value) >= 3 and value[:2].upper() == "N'" and value[-1] == "'":
        return value[2:-1].replace("''", "'")
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _integer_literal(token: str) -> int | None:
    value = _sql_string_value(token).strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return None


def is_fixed_header_anchor(field_name: str) -> bool:
    upper_name = str(field_name).upper()
    return any(upper_name.endswith(suffix) for suffix in FIXED_HEADER_SUFFIXES)


def is_runtime_moved_header_anchor(field_name: str) -> bool:
    """Return anchors relocated by CBill::OnSize before collision checks."""
    upper_name = str(field_name).upper()
    return upper_name.endswith(("_PJLX", "_ZDR", "_SHR", "_ZY"))


def expected_metadata_control(field_name: str) -> str:
    """PJLX is the voucher-type selector; other generated fields use E."""
    return "S" if str(field_name).upper().endswith("_PJLX") else "E"


def physical_date_fields(sql: str) -> set[str]:
    """Return physical fields declared as date/datetime/datetime2 in the pack.

    The SQL artifact itself is the source of truth for a new form.  This keeps
    the static check from guessing a date control from a label or a suffix.
    Existing-metadata repair scripts that do not contain DDL remain unable to
    prove a new D type and therefore fail closed for such a tuple.
    """
    pattern = re.compile(
        r"(?:\(|,)\s*\[?([A-Za-z_][A-Za-z0-9_]*)\]?\s+"
        r"(?:date|datetime|datetime2)\b",
        flags=re.IGNORECASE,
    )
    return {match.group(1).upper() for match in pattern.finditer(sql)}


def _statement_end(sql: str, start: int) -> int:
    quoted = False
    depth = 0
    i = start
    while i < len(sql):
        char = sql[i]
        if quoted:
            if char == "'":
                if i + 1 < len(sql) and sql[i + 1] == "'":
                    i += 2
                    continue
                quoted = False
        else:
            if char == "'":
                quoted = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == ";" and depth == 0:
                return i
        i += 1
    return len(sql)


def _column_name(token: str) -> str:
    value = token.strip()
    if value.startswith("[") and value.endswith("]"):
        return value[1:-1].replace("]]", "]")
    return value


def _sys_tbcolumn_inserts(sql: str) -> list[tuple[list[str], str]]:
    pattern = re.compile(
        r"INSERT\s+(?:INTO\s+)?(?:\[dbo\]|dbo)\.(?:\[SYS_TbColumn\]|SYS_TbColumn)\s*"
        r"\((.*?)\)\s*(?:OUTPUT\b.*?\bINTO\b.*?\)\s*)?VALUES",
        flags=re.IGNORECASE | re.DOTALL,
    )
    inserts: list[tuple[list[str], str]] = []
    for match in pattern.finditer(sql):
        columns = [_column_name(value) for value in split_values("(" + match.group(1) + ")")]
        end = _statement_end(sql, match.end())
        inserts.append((columns, sql[match.end():end]))
    return inserts


def _iobdzd_inserts(sql: str) -> list[tuple[list[str], str]]:
    pattern = re.compile(
        r"INSERT\s+(?:INTO\s+)?(?:\[dbo\]|dbo)\.(?:\[IOBDZD\]|IOBDZD)\s*\((.*?)\)\s*VALUES",
        flags=re.IGNORECASE | re.DOTALL,
    )
    inserts: list[tuple[list[str], str]] = []
    for match in pattern.finditer(sql):
        columns = [_column_name(value) for value in split_values("(" + match.group(1) + ")")]
        end = _statement_end(sql, match.end())
        inserts.append((columns, sql[match.end():end]))
    return inserts


def validate_forward(path: Path, expected_rid_start: int | None = None, expected_rid_end: int | None = None,
                     expected_audit_width: int | None = None, expected_audit_left: int | None = None,
                     expected_audit_top: int | None = None, expected_audit_height: int | None = None,
                     expected_audit_gap: int | None = None,
                     help_button_width: int | None = None) -> list[str]:
    sql = path.read_text(encoding="utf-8")
    errors: list[str] = []
    browse_button_width = DEFAULT_BROWSE_BUTTON_WIDTH if help_button_width is None else help_button_width
    if browse_button_width <= 0:
        errors.append(f"帮助按钮宽度必须为正整数，实际{browse_button_width}")
    date_fields = physical_date_fields(sql)
    route_inserts = _iobdzd_inserts(sql)
    if not route_inserts:
        errors.append("forward.sql 没有 IOBDZD INSERT")
    seen_marks: dict[str, int] = {}
    for insert_no, (columns, chunk) in enumerate(route_inserts, 1):
        if "IOBDZD_FORMAT" not in columns:
            errors.append(f"IOBDZD INSERT {insert_no}: 缺少 IOBDZD_FORMAT")
        if "IOBDZD_MARK" not in columns:
            errors.append(f"IOBDZD INSERT {insert_no}: 缺少 IOBDZD_MARK")
        rows = extract_tuples(chunk)
        if not rows:
            errors.append(f"IOBDZD INSERT {insert_no}: 没有 VALUES 行")
            continue
        format_index = columns.index("IOBDZD_FORMAT") if "IOBDZD_FORMAT" in columns else None
        mark_index = columns.index("IOBDZD_MARK") if "IOBDZD_MARK" in columns else None
        for row_no, row in enumerate(rows, 1):
            values = split_values(row)
            if len(values) != len(columns):
                errors.append(f"IOBDZD INSERT {insert_no} tuple {row_no}: 列清单{len(columns)}项，实际{len(values)}项")
                continue
            if format_index is not None:
                format_token = values[format_index]
                if format_token.strip().upper() == "NULL" or not _sql_string_value(format_token).strip():
                    errors.append(f"IOBDZD INSERT {insert_no} tuple {row_no}: IOBDZD_FORMAT 不能为 NULL、空串或空格")
            if mark_index is not None:
                mark = _sql_string_value(values[mark_index])
                if not IOBDZD_MARK_RE.fullmatch(mark):
                    errors.append(f"IOBDZD INSERT {insert_no} tuple {row_no}: IOBDZD_MARK 必须是恰好两个英文字母，实际{values[mark_index].strip()}")
                elif mark in seen_marks:
                    errors.append(f"IOBDZD INSERT {insert_no} tuple {row_no}: IOBDZD_MARK {mark} 与 tuple {seen_marks[mark]} 重复")
                else:
                    seen_marks[mark] = row_no
    inserts = _sys_tbcolumn_inserts(sql)
    if not inserts:
        errors.append("forward.sql 没有 SYS_TbColumn INSERT")
        return errors

    rids: list[int] = []
    rid_offsets: list[int] = []
    metadata_groups: dict[tuple[str, str], dict[str, object]] = {}
    query_aliases: dict[str, list[str]] = {}
    query_key_counts: dict[str, int] = {}
    query_row_count = 0
    header_layout: dict[str, list[dict[str, int | str | bool]]] = {}
    for insert_no, (columns, chunk) in enumerate(inserts, 1):
        column_index = {name: index for index, name in enumerate(columns)}
        required_columns = {
            "表名", "PO", "字段名", "主键", "显示名", "关键字段", "控件", "顺序",
            "显示", "标签名", "列宽", "类型", "标识", "左坐标", "顶坐标", "宽度", "高度", "RID",
        }
        missing = sorted(required_columns - set(column_index))
        if missing:
            errors.append(f"SYS_TbColumn INSERT {insert_no}: 缺少列 {','.join(missing)}")
            continue
        rows = extract_tuples(chunk)
        for row_no, row in enumerate(rows, 1):
            values = split_values(row)
            if len(values) != len(columns):
                errors.append(f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: 列清单{len(columns)}项，实际{len(values)}项")
                continue
            # 标识是 FF_BS 的触发器；普通动态单据字段必须保持 NULL。
            marker = values[column_index["标识"]]
            if marker.upper() != "NULL":
                errors.append(f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: 标识必须为 NULL，实际{marker}")

            table_name = _sql_string_value(values[column_index["表名"]])
            po = _sql_string_value(values[column_index["PO"]])
            field_name = _sql_string_value(values[column_index["字段名"]])
            order_token = _sql_string_value(values[column_index["顺序"]])
            try:
                order = int(order_token)
            except (TypeError, ValueError):
                order = None
                errors.append(f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: 顺序必须是整数，实际{order_token or '<空>'}")
            primary = values[column_index["主键"]].strip()
            key_field = values[column_index["关键字段"]].strip()
            control = _sql_string_value(values[column_index["控件"]]).upper()
            if primary not in {"0", "1"}:
                errors.append(f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: 主键必须为 0/1，实际{primary}")
            if key_field not in {"0", "1"}:
                errors.append(f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: 关键字段必须为 0/1，实际{key_field}")
            metadata_type = _sql_string_value(values[column_index["类型"]]).upper()
            expected_type = "D" if field_name.upper() in date_fields else "S"
            if metadata_type != expected_type:
                errors.append(
                    f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: 字段 {field_name} "
                    f"类型必须为 {expected_type}，实际{metadata_type or '<空>'}"
                )
            expected_control = expected_metadata_control(field_name)
            if control != expected_control:
                errors.append(
                    f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: 新生成元数据控件必须为 {expected_control}，"
                    f"字段 {field_name} 实际{control or '<空>'}"
                )
            visible_token = values[column_index["显示"]].strip()
            if visible_token == "1":
                label = _sql_string_value(values[column_index["标签名"]])
                if not label:
                    errors.append(f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: 可见字段标签名不能为空")
                else:
                    width_token = _sql_string_value(values[column_index["列宽"]])
                    try:
                        width = int(width_token)
                    except (TypeError, ValueError):
                        errors.append(
                            f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: 可见字段列宽必须是整数，实际{width_token or '<空>'}"
                        )
                    else:
                        minimum = label_column_width(label)
                        if width < minimum:
                            errors.append(
                                f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: 字段 {field_name} 列宽{width}"
                                f"小于标签最小宽度{minimum}，首屏字段名会被截断"
                            )
            if not table_name.endswith("查询") and po == "1":
                top = _integer_literal(values[column_index["顶坐标"]])
                height = _integer_literal(values[column_index["高度"]])
                if top is not None and height is not None:
                    header_layout.setdefault(table_name, []).append({
                        "field": field_name,
                        "visible": visible_token == "1",
                        "left": _integer_literal(values[column_index["左坐标"]]),
                        "width": _integer_literal(values[column_index["宽度"]]),
                        "top": top,
                        "height": height,
                        "help": (
                            bool(_sql_string_value(values[column_index["帮助"]]).strip())
                            and _sql_string_value(values[column_index["帮助"]]).strip().upper() != "NULL"
                        ) if "帮助" in column_index else False,
                    })
            group = metadata_groups.setdefault((table_name, po), {"primary": 0, "key": 0, "orders": []})
            orders = group["orders"]
            assert isinstance(orders, list)
            orders.append(order)
            if primary == "1":
                group["primary"] += 1
            if key_field == "1":
                group["key"] += 1
            if table_name.endswith("查询"):
                query_row_count += 1
                query_key_counts[table_name] = query_key_counts.get(table_name, 0) + (key_field == "1")
                alias = _sql_string_value(values[column_index["显示名"]])
                query_aliases.setdefault(table_name, []).append(alias)
                if not alias:
                    errors.append(f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: 查询显示名不能为空")

            # 审核矩形必须保留参考尺寸；其是否同行由下面的装箱校验决定。
            if (
                not table_name.endswith("查询")
                and field_name.upper().endswith("_SHBZ")
                and _sql_string_value(values[column_index["PO"]]) == "1"
                and values[column_index["显示"]] == "1"
            ):
                for label, column, expected in (
                    ("左坐标", "左坐标", expected_audit_left), ("顶坐标", "顶坐标", expected_audit_top),
                    ("宽度", "宽度", expected_audit_width), ("高度", "高度", expected_audit_height),
                ):
                    actual = values[column_index[column]]
                    if expected is not None and actual != str(expected):
                        errors.append(f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: 审核{label}期望{expected}，实际{actual}")

            rid = values[column_index["RID"]]
            dynamic = re.fullmatch(r"@RIDBase\s*\+\s*(\d+)", rid, flags=re.IGNORECASE)
            if re.fullmatch(r"-?\d+", rid):
                rids.append(int(rid))
            elif dynamic:
                rid_offsets.append(int(dynamic.group(1)))
            else:
                errors.append(f"SYS_TbColumn INSERT {insert_no} tuple {row_no}: RID 不是整数或 @RIDBase+offset: {rid}")

    for table_name, rows in sorted(header_layout.items()):
        audits = [row for row in rows if str(row["field"]).upper().endswith("_SHBZ") and row["visible"]]
        ordinary = [
            row for row in rows
            if row["visible"] and not is_fixed_header_anchor(str(row["field"]))
        ]
        if not audits:
            continue
        audit = audits[0]
        audit_top = int(audit["top"])
        audit_bottom = audit_top + int(audit["height"])
        audit_left = audit.get("left")
        audit_width = audit.get("width")
        if audit_left is not None and audit_width is not None and int(audit_width) <= 0:
            errors.append(f"SYS_TbColumn {table_name}/PO=1: 审核宽度必须为正数")

        # Every visible field, including SHBZ, must have a positive outer
        # rectangle.  A non-empty help value reserves the measured browse
        # button width in that outer rectangle.
        for row in rows:
            if not row["visible"]:
                continue
            left = row.get("left")
            width = row.get("width")
            if left is None or width is None or int(width) <= 0:
                errors.append(f"SYS_TbColumn {table_name}/PO=1: 字段 {row['field']} 可见外框尺寸无效")
            elif row.get("help") and int(width) <= browse_button_width:
                errors.append(
                    f"SYS_TbColumn {table_name}/PO=1: 字段 {row['field']} 带帮助但宽度{width}"
                    f"未为浏览按钮保留{browse_button_width}"
                )
            if int(row["top"]) < 0 or int(row["height"]) <= 0:
                errors.append(
                    f"SYS_TbColumn {table_name}/PO=1: 字段 {row['field']} 顶坐标必须非负且高度必须为正"
                )
            if left is not None and int(left) < 0:
                errors.append(
                    f"SYS_TbColumn {table_name}/PO=1: 字段 {row['field']} 左坐标必须非负"
                )

        # Same-row rectangle collision check.  This intentionally uses the
        # full input outer rectangle; label-inclusive measurements are a
        # contract input and are checked by the client-shaped review pack.
        visible_rows = [
            row for row in rows
            if row["visible"]
            and not is_runtime_moved_header_anchor(str(row["field"]))
            and row.get("left") is not None
            and row.get("width") is not None
        ]
        for index, first in enumerate(visible_rows):
            for second in visible_rows[index + 1:]:
                if int(first["top"]) != int(second["top"]):
                    continue
                first_right = int(first["left"]) + int(first["width"])
                second_right = int(second["left"]) + int(second["width"])
                if int(first["left"]) < second_right and int(second["left"]) < first_right:
                    errors.append(
                        f"SYS_TbColumn {table_name}/PO=1: 同行字段 {first['field']} 与 {second['field']} 外框重叠"
                    )

        same_row_ordinary = [row for row in ordinary if int(row["top"]) == audit_top]
        earlier_ordinary = [
            row for row in ordinary
            if int(row["top"]) < audit_top
            and int(row["top"]) + int(row["height"]) <= audit_top
        ]
        crossing_ordinary = [
            row for row in ordinary
            if int(row["top"]) < audit_top
            and int(row["top"]) + int(row["height"]) > audit_top
        ]
        if crossing_ordinary:
            errors.append(f"SYS_TbColumn {table_name}/PO=1: 非固定字段与审核行垂直交叠")
        if any(int(row["top"]) + int(row["height"]) > audit_bottom for row in ordinary):
            errors.append(f"SYS_TbColumn {table_name}/PO=1: 非固定字段越过审核底边")
        if earlier_ordinary:
            last_bottom = max(int(row["top"]) + int(row["height"]) for row in earlier_ordinary)
            gap = audit_top - last_bottom
            if gap < MIN_LAYOUT_GAP:
                errors.append(f"SYS_TbColumn {table_name}/PO=1: 换行审核前自然间距必须至少为 {MIN_LAYOUT_GAP}，实际{gap}")
            if expected_audit_gap is not None and gap != expected_audit_gap:
                errors.append(
                    f"SYS_TbColumn {table_name}/PO=1: 审核前自然间距期望{expected_audit_gap}，实际{gap}（审核换行场景）"
                )
        elif not same_row_ordinary and ordinary:
            errors.append(f"SYS_TbColumn {table_name}/PO=1: 审核既未同行也没有上一行字段可推导自然间距")

    for (table_name, po), counts in sorted(metadata_groups.items()):
        orders = counts["orders"]
        assert isinstance(orders, list)
        expected_orders = list(range(1, len(orders) + 1))
        if sorted(order for order in orders if isinstance(order, int)) != expected_orders or len(orders) != len([order for order in orders if isinstance(order, int)]):
            errors.append(
                f"SYS_TbColumn {table_name}/PO={po}: 顺序必须从 1 连续编号，实际{orders}"
            )
        if counts["primary"] != 1:
            errors.append(
                f"SYS_TbColumn {table_name}/PO={po}: 必须恰好一个主键=1，"
                f"实际{counts['primary']}"
            )
        if counts["key"] > 1:
            errors.append(
                f"SYS_TbColumn {table_name}/PO={po}: 关键字段=1 不能超过一个，"
                f"实际{counts['key']}"
            )
    if query_row_count == 0:
        errors.append("forward.sql 没有独立查询页 SYS_TbColumn 字段集")
    else:
        for table_name, key_count in sorted(query_key_counts.items()):
            if key_count != 1:
                errors.append(f"查询页 {table_name} 关键字段必须恰好一个，实际{key_count}")
        for table_name, aliases in sorted(query_aliases.items()):
            duplicate_aliases = sorted(alias for alias, count in Counter(aliases).items() if count > 1)
            if duplicate_aliases:
                errors.append(f"查询页 {table_name} 显示名重复: " + ",".join(duplicate_aliases))

    if rids and len(rids) != len(set(rids)):
        errors.append("SYS_TbColumn RID 存在重复")
    if rid_offsets and len(rid_offsets) != len(set(rid_offsets)):
        errors.append("SYS_TbColumn RID offset 存在重复")
    if rids and rid_offsets:
        errors.append("SYS_TbColumn RID 混用固定整数和运行时 offset")
    if rid_offsets:
        if sorted(rid_offsets) != list(range(len(rid_offsets))):
            errors.append("SYS_TbColumn RID offset 必须从 0 连续覆盖全部维护页和查询页元数据")
        declaration = re.search(r"DECLARE\s+@RIDBase\s+int\s*=\s*ISNULL\s*\(\s*\(\s*SELECT\s+MAX\s*\(\s*TRY_CONVERT\s*\(\s*int\s*,\s*RID\s*\)\s*\)\s+FROM\s+dbo\.SYS_TbColumn\s*\)\s*,\s*0\s*\)\s*\+\s*1", sql, flags=re.IGNORECASE | re.DOTALL)
        if not declaration:
            errors.append("forward.sql 缺少基于当前 MAX(RID)+1 的 @RIDBase 声明")
        if not re.search(r"IF\s+@RIDBase\s*<=\s*0\s+THROW", sql, flags=re.IGNORECASE):
            errors.append("forward.sql 缺少 @RIDBase 正整数门禁")
    if expected_rid_start is not None and expected_rid_end is not None:
        if rid_offsets:
            errors.append("运行时 RID 策略不能同时使用固定 expected-rid-start/end")
        expected = list(range(expected_rid_start, expected_rid_end + 1))
        if sorted(rids) != expected:
            errors.append(f"SYS_TbColumn RID 未完整覆盖 {expected_rid_start}-{expected_rid_end}")
    return errors


def validate_crud(path: Path) -> list[str]:
    sql = path.read_text(encoding="utf-8")
    errors: list[str] = []
    pattern = re.compile(
        r"INSERT\s+INTO\s+(?:\[dbo\]|dbo)\.(?:\[([A-Za-z_][A-Za-z0-9_]*)\]|([A-Za-z_][A-Za-z0-9_]*))\s*\((.*?)\)\s*VALUES\s*(.*?);",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(sql):
        table_name = match.group(1) or match.group(2)
        columns = [value.strip() for value in match.group(3).split(",") if value.strip()]
        for row_no, row in enumerate(extract_tuples(match.group(4)), 1):
            values = split_values(row)
            if len(columns) != len(values):
                errors.append(
                    f"{table_name} INSERT tuple {row_no}: 列清单{len(columns)}项，值{len(values)}项"
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forward", type=Path, required=True)
    parser.add_argument("--crud", type=Path)
    parser.add_argument("--expected-rid-start", type=int)
    parser.add_argument("--expected-rid-end", type=int)
    parser.add_argument("--expected-audit-left", type=int, help="Optional maintenance-page SHBZ left coordinate.")
    parser.add_argument("--expected-audit-top", type=int, help="Optional maintenance-page SHBZ top coordinate.")
    parser.add_argument("--expected-audit-width", type=int, help="Optional maintenance-page SHBZ width.")
    parser.add_argument("--expected-audit-height", type=int, help="Optional maintenance-page SHBZ height.")
    parser.add_argument("--expected-audit-gap", type=int, help="Optional gap from the previous row bottom to a wrapped SHBZ row; ignored when SHBZ shares a row with ordinary fields.")
    parser.add_argument("--help-button-width", type=int, default=DEFAULT_BROWSE_BUTTON_WIDTH, help="Measured browse-button width for non-empty 帮助 fields (default: 20).")
    args = parser.parse_args(argv)

    errors: list[str] = []
    errors.extend(validate_forward(
        args.forward,
        expected_rid_start=args.expected_rid_start,
        expected_rid_end=args.expected_rid_end,
        expected_audit_width=args.expected_audit_width,
        expected_audit_left=args.expected_audit_left,
        expected_audit_top=args.expected_audit_top,
        expected_audit_height=args.expected_audit_height,
        expected_audit_gap=args.expected_audit_gap,
        help_button_width=args.help_button_width,
    ))
    if args.crud:
        errors.extend(validate_crud(args.crud))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: dynamic-bill SQL artifacts are structurally consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
