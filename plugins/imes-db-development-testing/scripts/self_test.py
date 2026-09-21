#!/usr/bin/env python3
"""Deterministic smoke tests for the bundled IMES debugging scripts."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import extract_bdjb_rules
import generate_first_pass_sql
import scaffold_dynamic_bill
import scaffold_basic_form
import scaffold_complex_form
import scaffold_eam_asset_suite
import validate_dynamic_bill_artifacts


# The ER-fixture tests need a real project ER diagram. It is supplied by the
# caller rather than vendored here, so this skill carries no customer artifact.
ER_FIXTURE_ENV = "IMES_SKILL_ER_SVG"


def er_fixture_path() -> Path | None:
    """Return the caller-supplied ER diagram, or None when it is not configured."""
    raw = os.environ.get(ER_FIXTURE_ENV, "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def require_er_fixture() -> Path | None:
    """Resolve the ER fixture, printing the skip notice when it is unset."""
    svg = er_fixture_path()
    if svg is None:
        print(f"Skipped ER fixture test: set {ER_FIXTURE_ENV} to an ER diagram SVG to enable it.")
    return svg


def test_first_pass_generator() -> None:
    args = argparse.Namespace(
        bill_type="ordinary report",
        document_no="DOC'001",
        expected_database="MESDB",
        bdjb_table="dbo.BDJB",
        bill_type_column="BDJB_PJLX",
        document_table="dbo.ReportHeader",
        document_column="DocumentNo",
        output=None,
        force=False,
    )
    sql = generate_first_pass_sql.build_sql(args)
    assert "SELECT DB_NAME() AS CurrentDatabase" in sql
    assert "N'DOC''001'" in sql
    assert "FROM [dbo].[BDJB]" in sql
    assert "FROM [dbo].[ReportHeader]" in sql


def test_rule_extractor() -> None:
    audit_sql = """
UPDATE B
SET B.CompletedQty = D.ReportQty
FROM dbo.BatchHeader B
JOIN dbo.ReportDetail D ON D.BatchNo = B.BatchNo
WHERE D.Approved = 1
  AND ISNULL(D.NextProcess, '') = ''
"""
    cancel_sql = """
UPDATE B
SET B.CompletedQty = 0
FROM dbo.BatchHeader B
JOIN dbo.ReportDetail D ON D.BatchNo = B.BatchNo
WHERE D.DocumentNo = @DocumentNo
"""
    audit = extract_bdjb_rules.analyze_sql(audit_sql)[0]
    cancel = extract_bdjb_rules.analyze_sql(cancel_sql)[0]
    assert audit.resolved_target == "dbo.BatchHeader"
    assert audit.assignments[0].mode == "direct-overwrite"
    assert "D.NextProcess" in audit.predicate_fields
    assert cancel.assignments[0].mode == "constant-reset"

    rules = [
        extract_bdjb_rules.RuleAnalysis("1", "audit", "10", "", [audit], []),
        extract_bdjb_rules.RuleAnalysis("2", "cancel", "10", "", [cancel], []),
    ]
    extract_bdjb_rules.add_cross_rule_warnings(rules)
    assert any("partial cancel-audit" in warning for warning in rules[0].warnings)

    case_sql = """
UPDATE B
SET B.CompletedFlag = CASE WHEN B.CompletedQty > 0 THEN 1 ELSE 0 END
FROM dbo.BatchHeader B
WHERE B.BatchNo = @BatchNo
"""
    case_update = extract_bdjb_rules.analyze_sql(case_sql)[0]
    assert case_update.assignments[0].column == "B.CompletedFlag"
    assert "CASE WHEN" in case_update.assignments[0].expression
    assert case_update.where == "B.BatchNo = @BatchNo"



def test_dynamic_bill_contract_and_artifacts() -> None:
    baseline = {
        "source": "old.svg",
        "tables": [{"table": "H1", "fields": [{"name": "OLD_CODE", "label": "编号"}]}],
    }
    current = {
        "source": "new.svg",
        "tables": [{"table": "H1", "fields": [{"name": "NEW_CODE", "label": "编号"}]}],
    }
    diff = scaffold_dynamic_bill.contract_diff(baseline, current)
    assert diff["changed"] is True
    assert diff["likely_renames"] == [{"table": "H1", "from": "OLD_CODE", "to": "NEW_CODE", "label": "编号"}]

    rows = validate_dynamic_bill_artifacts.extract_tuples("(N'a,b',NULL,1),(2,3,4)")
    assert len(rows) == 2
    assert validate_dynamic_bill_artifacts.split_values(rows[0]) == ["N'a,b'", "NULL", "1"]

    manifest = {"source": "new.svg", "reference_bill_name": "点检模板", "tables": []}
    evidence = scaffold_dynamic_bill.render_reference_evidence(manifest)
    assert "@ReferenceBillName" in evidence
    assert "IOBDZD_MC = @ReferenceBillName" in evidence
    assert "RIGHT(字段名, 5) = N'_SHBZ'" in evidence
    assert "last-non-fixed-header-bottom" in evidence
    assert "try the current row first" in evidence
    assert "RequiredBrowseButtonWidth" in evidence

    no_reference = scaffold_dynamic_bill.render_reference_evidence({"tables": []})
    assert "No --reference-bill-name was supplied" in no_reference

    values = ["NULL"] * len(scaffold_complex_form.META_COLUMNS)
    values[1] = "N'1'"
    values[2] = "N'TEST_SHBZ'"
    values[3] = "1"
    values[5] = "N'审核'"
    values[6] = "N'审核'"
    values[8] = "1"
    values[10] = "1"
    values[28] = "NULL"
    values[31] = "0"
    values[32] = "720"
    values[33] = "190"
    values[34] = "100"
    values[35] = "25"
    values[26] = "N'S'"
    values[42] = "N'E'"
    values[43] = "@RIDBase + 0"
    columns = list(scaffold_complex_form.META_COLUMNS)
    for position, name in {0: "表名", 1: "PO", 2: "字段名", 3: "主键", 5: "显示名", 6: "标签名", 8: "显示", 28: "标识", 31: "关键字段", 32: "左坐标", 33: "顶坐标", 34: "宽度", 35: "高度", 42: "控件", 43: "RID"}.items():
        columns[position] = name
    bad_audit_sql = (
        "INSERT INTO dbo.SYS_TbColumn (" + ",".join(f"[{name}]" for name in columns) + ") VALUES ("
        + ",".join(values)
        + ");\n"
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad-forward.sql"
        bad_path.write_text(bad_audit_sql, encoding="utf-8")
        errors = validate_dynamic_bill_artifacts.validate_forward(
            bad_path, expected_audit_width=150
        )
    assert any("审核宽度期望150，实际100" in error for error in errors)

    values[6] = "N'点检记录'"
    values[9] = "100"
    values[26] = "N'D'"
    with tempfile.TemporaryDirectory() as temp_dir:
        narrow_path = Path(temp_dir) / "narrow-label.sql"
        narrow_path.write_text(
            "INSERT INTO dbo.SYS_TbColumn (" + ",".join(f"[{name}]" for name in columns) + ") VALUES ("
            + ",".join(values)
            + ");\n",
            encoding="utf-8",
        )
        narrow_errors = validate_dynamic_bill_artifacts.validate_forward(narrow_path)
    assert any("首屏字段名会被截断" in error for error in narrow_errors)
    assert any("字段 TEST_SHBZ 类型必须为 S" in error for error in narrow_errors)

    invalid_geometry_values = list(values)
    invalid_geometry_values[33] = "-1"
    invalid_geometry_values[35] = "0"
    with tempfile.TemporaryDirectory() as temp_dir:
        geometry_path = Path(temp_dir) / "invalid-geometry.sql"
        geometry_path.write_text(
            "INSERT INTO dbo.SYS_TbColumn (" + ",".join(f"[{name}]" for name in columns) + ") VALUES ("
            + ",".join(invalid_geometry_values)
            + ");\n",
            encoding="utf-8",
        )
        geometry_errors = validate_dynamic_bill_artifacts.validate_forward(geometry_path)
    assert any("顶坐标必须非负且高度必须为正" in error for error in geometry_errors)

    date_values = list(values)
    date_values[2] = "N'TEST_YWRQ'"
    date_values[26] = "N'D'"
    with tempfile.TemporaryDirectory() as temp_dir:
        date_path = Path(temp_dir) / "date-forward.sql"
        date_path.write_text(
            "CREATE TABLE dbo.TEST_DATE ([TEST_YWRQ] date NOT NULL);\n"
            + "INSERT INTO dbo.SYS_TbColumn (" + ",".join(f"[{name}]" for name in columns) + ") VALUES ("
            + ",".join(date_values)
            + ");\n",
            encoding="utf-8",
        )
        date_errors = validate_dynamic_bill_artifacts.validate_forward(date_path)
    assert not any("字段 TEST_YWRQ 类型必须为" in error for error in date_errors)

    with tempfile.TemporaryDirectory() as temp_dir:
        crud_path = Path(temp_dir) / "generic-crud.sql"
        crud_path.write_text(
            "INSERT INTO [dbo].[TEST_HEADER] ([CODE],[NAME]) VALUES (N'C-1',N'Header');\n"
            "INSERT INTO dbo.TEST_DETAIL ([CODE]) VALUES (N'D-1');\n",
            encoding="utf-8",
        )
        assert validate_dynamic_bill_artifacts.validate_crud(crud_path) == []

    values[26] = "N'S'"
    values[10] = "0"
    bad_order_sql = (
        "INSERT INTO dbo.SYS_TbColumn (" + ",".join(f"[{name}]" for name in columns) + ") VALUES ("
        + ",".join(values)
        + ");\n"
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        bad_order_path = Path(temp_dir) / "bad-order.sql"
        bad_order_path.write_text(bad_order_sql, encoding="utf-8")
        order_errors = validate_dynamic_bill_artifacts.validate_forward(bad_order_path)
    assert any("顺序必须从 1 连续编号" in error for error in order_errors)

    # CreateDlgItemWithArrayDateTime locates runtime anchors by substring on
    # 字段名, so a second row carrying the same substring wins silently.
    anchor_values = list(values)
    anchor_values[0] = "N'TESTBILL'"
    anchor_values[1] = "N'1'"
    anchor_values[2] = "N'TESTBILL_SJDH'"
    anchor_values[3] = "1"
    anchor_values[5] = "N'单号'"
    anchor_values[6] = "N'单号'"
    anchor_values[8] = "0"
    anchor_values[10] = "1"
    anchor_values[28] = "NULL"
    anchor_values[31] = "1"
    duplicate_anchor = list(anchor_values)
    duplicate_anchor[2] = "N'TESTBILL_SJDH_X'"
    duplicate_anchor[10] = "2"
    with tempfile.TemporaryDirectory() as temp_dir:
        anchor_path = Path(temp_dir) / "duplicate-anchor.sql"
        anchor_path.write_text(
            "INSERT INTO dbo.SYS_TbColumn (" + ",".join(f"[{name}]" for name in columns) + ") VALUES ("
            + ",".join(anchor_values) + "),(" + ",".join(duplicate_anchor) + ");\n",
            encoding="utf-8",
        )
        anchor_errors = validate_dynamic_bill_artifacts.validate_forward(anchor_path)
    assert any("锚点 _SJDH 命中多条字段" in error for error in anchor_errors)

    # GetCrossTable concatenates the alias columns straight into the LEFT JOIN;
    # a NULL alias breaks the generated FROM clause.
    alias_values = list(anchor_values)
    alias_values[24] = "N'物料信息'"
    alias_values[25] = "NULL"
    with tempfile.TemporaryDirectory() as temp_dir:
        alias_path = Path(temp_dir) / "null-alias.sql"
        alias_path.write_text(
            "INSERT INTO dbo.SYS_TbColumn (" + ",".join(f"[{name}]" for name in columns) + ") VALUES ("
            + ",".join(alias_values)
            + ");\n",
            encoding="utf-8",
        )
        alias_errors = validate_dynamic_bill_artifacts.validate_forward(alias_path)
    assert any("LMark 必须写空字符串" in error for error in alias_errors)


def test_basic_form_scaffold() -> None:
    assert scaffold_basic_form.label_column_width("分录号") == 840
    assert scaffold_basic_form.label_column_width("点检记录") == 1125
    assert scaffold_basic_form.label_column_width("ABCD") == 570
    assert scaffold_basic_form.label_column_width("A中B") == 570
    assert scaffold_basic_form.label_column_width("  ") == 15
    assert scaffold_basic_form.resolve_column_width(
        {"name": "TST_NAME", "label": "点检记录", "column_width": 1500}
    ) == 1500
    assert scaffold_complex_form.label_column_width("分录号") == 840
    assert scaffold_complex_form.label_column_width("点检记录") == 1125
    assert scaffold_complex_form.label_column_width("ABCD") == 570
    assert scaffold_complex_form.label_column_width("A中B") == 570
    assert scaffold_complex_form.resolve_column_width(
        {"name": "TST_NAME", "label": "点检记录"}, {"column_width": 1500}, True
    ) == 1500

    try:
        scaffold_basic_form.resolve_column_width(
            {"name": "TST_NAME", "label": "点检记录", "column_width": 100}
        )
    except ValueError as exc:
        assert "label minimum" in str(exc)
    else:
        raise AssertionError("basic-form narrow label width was accepted")
    try:
        scaffold_complex_form.resolve_column_width(
            {"name": "TST_NAME", "label": "点检记录"}, {"column_width": 100}, True
        )
    except ValueError as exc:
        assert "label minimum" in str(exc)
    else:
        raise AssertionError("complex-form narrow label width was accepted")

    contract = {
        "expected_database": "TEST_DB",
        "expected_server": "TEST_SERVER",
        "schema": "dbo",
        "table": "TSTCJ",
        "visible_name": "TestWorkshop",
        "route": {
            "bh": "TSTCJ",
            "btype": 1,
            "vkey": "TSTCJ_CODE",
            "byzd": "TSTCJ_CODE,TSTCJ_NAME",
        },
        "workspace": {
            "root_bh": "0099",
            "root_name": "Test",
            "leaf_bh": "009901",
            "leaf_name": "TestWorkshop",
            "loc": "1",
            "create_root": False,
        },
        "fields": [
            {
                "name": "TSTCJ_ID",
                "sql": "int identity(1,1)",
                "pk": True,
                "identity": True,
                "nullable": False,
                "visible": False,
            },
            {
                "name": "TSTCJ_CODE",
                "sql": "varchar(20)",
                "nullable": False,
                "unique": True,
                "label": "Code",
                "test_value": "TST-001",
            },
            {
                "name": "TSTCJ_NAME",
                "sql": "varchar(50)",
                "nullable": False,
                "label": "Name",
                "test_value": "Test",
            },
            {
                "name": "TSTCJ_ENABLED",
                "sql": "bit",
                "nullable": False,
                "default": "(1)",
                "label": "Enabled",
                "test_value": 1,
            },
            {
                "name": "TSTCJ_DATE",
                "sql": "datetime",
                "nullable": True,
                "label": "Date",
                "test_value": "2026-08-26",
            },
        ],
    }
    normalized = scaffold_basic_form.normalize(contract)
    # 类型 defaults come from the physical SQL type (contract 9.1): identity int
    # is numeric, bit is a flag, datetime is a date.  A numeric column left as S
    # makes the client write '' and the insert fails on conversion.
    assert [(field["name"], field["meta_type"], field["control"]) for field in normalized["fields"]] == [
        ("TSTCJ_ID", "N", "E"),
        ("TSTCJ_CODE", "S", "E"),
        ("TSTCJ_NAME", "S", "E"),
        ("TSTCJ_ENABLED", "S", "E"),
        ("TSTCJ_DATE", "D", "E"),
    ]
    # The physical-type default is a hard rule, so prove each mapping directly.
    assert scaffold_basic_form.default_meta_type("int identity(1,1)") == "N"
    assert scaffold_basic_form.default_meta_type("decimal(18,2)") == "N"
    assert scaffold_basic_form.default_meta_type("varchar(50)") == "S"
    assert scaffold_basic_form.default_meta_type("datetime") == "D"
    assert scaffold_basic_form.default_meta_type("bit") == "S"
    forward = scaffold_basic_form.render_forward(normalized)
    assert "[表名]" in forward and "[字段名]" in forward and "[RID]" in forward
    assert "INSERT [dbo].[SYS_TbColumn] (nID" not in forward
    assert "OUTPUT inserted.nID INTO #NewMeta(nID)" in forward
    assert ",," not in forward
    assert "FF_BS" not in forward
    assert "name=N'RID'" in forward
    assert "SET [admin]=1" not in forward  # role columns are discovered dynamically
    assert "column_id>ISNULL((SELECT column_id" in forward
    verification = scaffold_basic_form.render_verification(normalized)
    assert "[标识] IS NOT NULL" in verification
    assert "新生成元数据控件必须全部为 E" in verification
    assert "新生成元数据类型必须与物理日期类型一致" in verification
    assert "BTYPE=1 每个表名与 PO 的顺序必须从 0 连续编号" in verification
    # LoadGridSet falls back to width 100 when 列宽 is 0, silently truncating the
    # label, so a visible field with a non-positive width must fail verification.
    assert "可见字段列宽必须显式给出正整数" in verification
    assert "TRY_CONVERT(int,[显示])=1" in verification
    assert "IF EXISTS (SELECT 1 FROM [dbo].[SYS_TbColumn] WHERE [表名]=N'TestWorkshop' AND COALESCE([控件]" in verification
    assert ",420,0,0,0," in scaffold_basic_form.meta_tuple(normalized, normalized["fields"][0], 0)
    assert ",570,1,0,0," in scaffold_basic_form.meta_tuple(normalized, normalized["fields"][1], 1)

    with tempfile.TemporaryDirectory() as temp_dir:
        output = Path(temp_dir) / "pack"
        scaffold_basic_form.generate(contract, output)
        expected = {
            "contract.json",
            "preflight.sql",
            "forward.sql",
            "verification.sql",
            "crud-test.sql",
            "rollback-preflight.sql",
            "rollback.sql",
            "README.md",
        }
        assert {path.name for path in output.iterdir()} == expected
        assert "PREFLIGHT_PASS" in (output / "preflight.sql").read_text(encoding="utf-8")
        assert "CRUD_PASS" in (output / "crud-test.sql").read_text(encoding="utf-8")
        readme = (output / "README.md").read_text(encoding="utf-8")
        assert "角色列和 `admin` 后工作区权限列默认全部授权为 `1`" in readme
        assert "sqlcmd -S <server>" in readme



def complex_fixture() -> dict:
    return {
        "expected_database": "TEST_DB", "expected_server": "TEST_SERVER", "schema": "dbo",
        "bill_name": "点检记录单", "form_kind": "inspection_record",
        "header": {"table": "EAMDJJLD1", "fields": [
            {"name": "EAMDJJLD1_ID", "sql": "int IDENTITY(1,1)", "pk": True, "identity": True, "nullable": False},
             {"name": "EAMDJJLD1_SJDH", "sql": "varchar(30)", "nullable": False, "label": "单据号", "test_value": "DJ-TEST-001"},
             {"name": "EAMDJJLD1_PJLX", "sql": "varchar(20)", "nullable": False, "label": "凭证类型", "test_value": "EAMDJJLD"},
             {"name": "EAMDJJLD1_SHBZ", "sql": "bit", "nullable": False, "label": "审核标志", "test_value": 0},
        ]},
        "detail": {"table": "EAMDJJLD2", "foreign_key": {"field": "EAMDJJLD2_SJDH", "references_table": "EAMDJJLD1", "references_field": "EAMDJJLD1_SJDH"}, "fields": [
            {"name": "EAMDJJLD2_ID", "sql": "int IDENTITY(1,1)", "pk": True, "identity": True, "nullable": False},
            {"name": "EAMDJJLD2_SJDH", "sql": "varchar(30)", "nullable": False, "label": "单据号", "test_value": "DJ-TEST-001"},
            {"name": "EAMDJJLD2_FLH", "sql": "int", "nullable": False, "label": "分录号", "test_value": 1},
        ]},
        "route": {"bh": "EAMDJJLD", "mark": "AB", "htable": "EAMDJJLD1", "ftable": "EAMDJJLD2", "vkey": "EAMDJJLD1_SJDH", "byzd": "EAMDJJLD1_SJDH", "fvkey": "EAMDJJLD2_SJDH", "tab1": "表头", "tab2": "表体", "tab3": ""},
        "metadata": {
            "rid_strategy": "runtime-max-plus-offset",
            "layout_source": {"reference_bill_name": "点检模板"},
             "audit": {"field": "EAMDJJLD1_SHBZ", "left": 600, "top": 140, "width": 700, "height": 22, "bottom": 162, "min_header_width": 1400, "natural_gap": 78},
            "maintain_fields": [
                {"table_role": "header", "field": "EAMDJJLD1_ID", "po": 1, "visible": 0, "top": 0, "height": 0},
                {"table_role": "header", "field": "EAMDJJLD1_SJDH", "po": 1, "top": 40, "height": 22},
                 {"table_role": "header", "field": "EAMDJJLD1_PJLX", "po": 1, "top": 70, "height": 22},
                 {"table_role": "header", "field": "EAMDJJLD1_SHBZ", "po": 1, "left": 600, "top": 140, "width": 700, "height": 22},
                {"table_role": "detail", "field": "EAMDJJLD2_ID", "po": 2, "visible": 0, "top": 0, "height": 0},
                {"table_role": "detail", "field": "EAMDJJLD2_SJDH", "po": 2, "top": 40, "height": 22},
                {"table_role": "detail", "field": "EAMDJJLD2_FLH", "po": 2, "top": 70, "height": 22},
            ],
            "query_fields": [
                 {"table_role": "header", "field": "EAMDJJLD1_SJDH", "po": 1, "top": 40, "height": 22, "primary_key": True, "key_field": True},
                 {"table_role": "header", "field": "EAMDJJLD1_PJLX", "po": 1, "top": 70, "height": 22},
                 {"table_role": "header", "field": "EAMDJJLD1_SHBZ", "po": 1, "top": 70, "height": 22},
            ],
        },
        "bdjb": {"rows": [{"BDJB_PJLX": "点检记录单", "BDJB_BH": "1", "BDJB_MC": "审核", "BDJB_SQL": "SELECT 1"}]},
        "workspace": {"rows": [{"SYSWSPACE_LOC": "1", "SYSWSPACE_BH": "9901", "SYSWSPACE_PBH": None, "SYSWSPACE_MC": "点检记录单", "SYSWSPACE_MX": 1, "SYSWSPACE_JS": 3, "SYSWSPACE_JDBZ": 1, "SYSWSPACE_QCYWBZ": 0, "SYSWSPACE_BTN": 0, "admin": 1}]},
    }


def test_complex_form_scaffold() -> None:
    svg = require_er_fixture()
    if svg is None:
        return
    tables = scaffold_dynamic_bill.parse_tables(svg)
    assert {"EAMDJMB1", "EAMDJMB2", "EAMDJJLD1", "EAMDJJLD2"}.issubset(tables)
    draft = scaffold_complex_form.draft_from_er(argparse.Namespace(er_svg=svg, header_table="EAMDJMB1", detail_table="EAMDJMB2", bill_name="点检模板", form_kind="inspection_template", expected_database="TEST_DB", expected_server="TEST_SERVER"))
    assert draft["deployment_ready"] is False
    with tempfile.TemporaryDirectory() as temp_dir:
        out = Path(temp_dir) / "draft"
        scaffold_complex_form.generate(draft, out)
        assert "THROW 54090" in (out / "forward.sql").read_text(encoding="utf-8")
        assert "review-blocked" in (out / "README.md").read_text(encoding="utf-8")
    c = scaffold_complex_form.normalize(complex_fixture())
    assert scaffold_complex_form.meta_type({"name": "EAMDJJLD1_YWRQ", "sql": "date"}) == "D"
    assert scaffold_complex_form.meta_type({"name": "EAMDJJLD2_FLH", "sql": "int"}) == "N"
    assert scaffold_complex_form.meta_type({"name": "EAMDJJLD2_SJDH", "sql": "varchar(30)"}) == "S"
    try:
        scaffold_complex_form.meta_type({"name": "EAMDJJLD1_YWRQ", "sql": "date", "type": "S"})
    except ValueError as exc:
        assert "metadata type must be D" in str(exc)
    else:
        raise AssertionError("date metadata type must fail closed when declared as S")
    assert c["deployment_ready"] is True
    assert c["route"]["format"] == "YYMM####"
    blank_format = complex_fixture()
    blank_format["route"]["format"] = "   "
    assert scaffold_complex_form.normalize(blank_format)["route"]["format"] == "YYMM####"
    assert c["route"]["mark"] == "AB"
    # IOBDZD_MARK is the document-number prefix: exactly two ASCII letters and
    # unique across the whole table.  There is no safe default, so every
    # malformed shape must fail closed instead of being normalized away.
    for bad_mark in ("", "   ", "1", "12", "ABC", "中文", "A1", "1A", "A "):
        broken = complex_fixture()
        broken["route"]["mark"] = bad_mark
        try:
            scaffold_complex_form.normalize(broken)
        except ValueError as exc:
            assert "IOBDZD_MARK" in str(exc)
        else:
            raise AssertionError(f"route.mark {bad_mark!r} must fail closed")
    missing_mark = complex_fixture()
    del missing_mark["route"]["mark"]
    try:
        scaffold_complex_form.normalize(missing_mark)
    except ValueError as exc:
        assert "IOBDZD_MARK" in str(exc)
    else:
        raise AssertionError("a missing route.mark must fail closed rather than default to '1'")
    invalid_format = complex_fixture()
    invalid_format["route"]["format"] = "MMYY####"
    try:
        scaffold_complex_form.normalize(invalid_format)
    except ValueError as exc:
        assert "route.format" in str(exc)
    else:
        raise AssertionError("unsupported IOBDZD_FORMAT must fail closed")
    audit_row = next(row for row in c["metadata"]["maintain_fields"] if row["field"] == "EAMDJJLD1_SHBZ")
    assert audit_row["width"] == 700
    assert audit_row["column_width"] == 1125
    assert c["metadata"]["audit"]["natural_gap"] == 78
    case_variant = complex_fixture()
    case_variant["metadata"]["maintain_fields"][1]["type"] = "s"
    case_variant["metadata"]["maintain_fields"][1]["control"] = "e"
    normalized_case_variant = scaffold_complex_form.normalize(case_variant)
    assert normalized_case_variant["metadata"]["maintain_fields"][1]["type"] == "S"
    assert normalized_case_variant["metadata"]["maintain_fields"][1]["control"] == "E"
    for rows in (c["metadata"]["maintain_fields"], c["metadata"]["query_fields"]):
        for po in sorted({row["po"] for row in rows}):
            assert [row["order"] for row in rows if row["po"] == po] == list(range(1, sum(row["po"] == po for row in rows) + 1))
    for kind in ("inspection_template", "inspection_record", "audit_bill", "header_detail_bill"):
        variant = complex_fixture()
        variant["form_kind"] = kind
        assert scaffold_complex_form.normalize(variant)["form_kind"] == kind
    assert c["header"]["fields"][2]["control"] == "S"
    assert c["header"]["fields"][3]["control"] == "E"
    schema_draft = scaffold_complex_form.render_schema(c)
    assert "CREATE TABLE" in schema_draft
    assert not any(line.lstrip().upper().startswith("CREATE TABLE") for line in schema_draft.splitlines())
    assert not any(line.lstrip().upper().startswith("SET ") for line in schema_draft.splitlines())
    forward = scaffold_complex_form.render_forward(c)
    assert "INSERT dbo.SYS_TbColumn (nID" not in forward
    assert "标识" in forward and "RID" in forward
    assert "SET dbo.SYS_TbColumn" not in forward
    assert "SYS_TbColumn" in forward and "点检记录单查询" in forward
    assert "IOBDZD_FORMAT" in forward and "N'YYMM####'" in forward
    for button in ("显示关联单据", "保存列宽", "列配置", "从EXCEL导入", "说明", "附件", "复制分录"):
        assert button in forward
    expected_menu_spaces = {"显示关联单据", "说明", "附件", "复制分录"}
    for row in scaffold_complex_form.required_sysmenu_rows("点检记录单"):
        assert row["sysmenu_uid"] == " "
        assert row["sysmenu_pmenu"] == (" " if row["sysmenu_buttonname"] in expected_menu_spaces else "其他")
    assert "标准 `sysmenu` 按钮" in (scaffold_complex_form.render_readme(c))
    assert "#NewWorkspace" in forward and "name=N'admin'" in forward
    assert "DECLARE @RIDBase int" in forward
    assert "@RIDBase + 0" in forward
    assert "@RIDBase + 1" in forward
    assert "RID=NULL" not in forward.upper()
    verification = scaffold_complex_form.render_verification(c)
    assert "查询页字段集不完整" in verification
    assert "审核控件坐标或尺寸不符合契约" in verification
    assert "审核与最后一个非固定表头字段之间的自然间距不符合契约" in verification
    assert "表名=N'点检记录单查询'" in verification
    assert "表名=N'点检记录单'查询" not in verification
    assert "审核推导的最低宽度" in verification
    assert "表头表体外键缺失" in verification
    assert "工作区节点不完整" in verification
    assert "系统按钮参数未按销售订单参考契约设置" in verification
    assert "RID 为空或不是正整数" in verification
    assert "RID 在维护页或查询页中重复" in verification
    assert "顺序必须从 1 连续编号" in verification
    assert "v_tbcolumn 不满足客户端控件初始化读取契约" in verification
    with tempfile.TemporaryDirectory() as temp_dir:
        forward_path = Path(temp_dir) / "forward.sql"
        forward_path.write_text(forward, encoding="utf-8")
        assert validate_dynamic_bill_artifacts.validate_forward(forward_path) == []
        assert validate_dynamic_bill_artifacts.validate_forward(forward_path, expected_audit_gap=78) == []
        gap_errors = validate_dynamic_bill_artifacts.validate_forward(forward_path, expected_audit_gap=10)
        assert any("审核前自然间距期望10，实际78" in error for error in gap_errors)
        missing_format = forward.replace(",IOBDZD_FORMAT,", ",", 1)
        missing_format_path = Path(temp_dir) / "missing-format.sql"
        missing_format_path.write_text(missing_format, encoding="utf-8")
        assert any("缺少 IOBDZD_FORMAT" in error for error in validate_dynamic_bill_artifacts.validate_forward(missing_format_path))
        missing_mark = forward.replace(",IOBDZD_MARK,", ",", 1)
        missing_mark_path = Path(temp_dir) / "missing-mark.sql"
        missing_mark_path.write_text(missing_mark, encoding="utf-8")
        assert any("缺少 IOBDZD_MARK" in error for error in validate_dynamic_bill_artifacts.validate_forward(missing_mark_path))
        assert ",N'AB'," in forward, "the fixture must render its two-letter mark for the negative cases below"
        for index, bad_mark in enumerate(("N'1'", "N'ABC'", "N'中文'", "N'A1'", "NULL")):
            bad_path = Path(temp_dir) / f"bad-mark-{index}.sql"
            bad_path.write_text(forward.replace(",N'AB',", f",{bad_mark},", 1), encoding="utf-8")
            bad_errors = validate_dynamic_bill_artifacts.validate_forward(bad_path)
            assert any("IOBDZD_MARK" in error for error in bad_errors), bad_mark

    same_row_contract = complex_fixture()
    same_row_contract["metadata"]["audit"].update({"top": 40, "bottom": 62})
    for row in same_row_contract["metadata"]["maintain_fields"]:
        if row["field"] == "EAMDJJLD1_SJDH":
            row.update({"left": 0, "top": 40, "width": 500, "height": 22})
        elif row["field"] == "EAMDJJLD1_SHBZ":
            row.update({"left": 600, "top": 40, "width": 700, "height": 22})
    same_row_normalized = scaffold_complex_form.normalize(same_row_contract)
    same_row_forward = scaffold_complex_form.render_forward(same_row_normalized)
    with tempfile.TemporaryDirectory() as temp_dir:
        same_row_path = Path(temp_dir) / "same-row-forward.sql"
        same_row_path.write_text(same_row_forward, encoding="utf-8")
        assert validate_dynamic_bill_artifacts.validate_forward(same_row_path, expected_audit_gap=78) == []

    help_contract = complex_fixture()
    help_contract["metadata"]["layout_source"]["browse_button_width"] = 24
    for row in help_contract["metadata"]["maintain_fields"]:
        if row["field"] == "EAMDJJLD1_SJDH":
            row.update({"left": 0, "top": 40, "width": 500, "height": 22, "help": "WLBH"})
    help_normalized = scaffold_complex_form.normalize(help_contract)
    help_forward = scaffold_complex_form.render_forward(help_normalized)
    with tempfile.TemporaryDirectory() as temp_dir:
        help_path = Path(temp_dir) / "help-forward.sql"
        help_path.write_text(help_forward, encoding="utf-8")
        assert validate_dynamic_bill_artifacts.validate_forward(help_path, help_button_width=24) == []

    too_narrow_help = complex_fixture()
    too_narrow_help["metadata"]["layout_source"]["browse_button_width"] = 24
    for row in too_narrow_help["metadata"]["maintain_fields"]:
        if row["field"] == "EAMDJJLD1_SJDH":
            row.update({"width": 24, "help": "WLBH"})
    try:
        scaffold_complex_form.normalize(too_narrow_help)
    except ValueError as exc:
        assert "browse-button width" in str(exc)
    else:
        raise AssertionError("help-bearing field narrower than browse button must fail closed")

    with tempfile.TemporaryDirectory() as temp_dir:
        out = Path(temp_dir) / "full"
        scaffold_complex_form.generate(complex_fixture(), out)
        assert {p.name for p in out.iterdir()} == {"contract.json", "schema-draft.sql", "preflight.sql", "reference-evidence.sql", "forward.sql", "verification.sql", "crud-test.sql", "rollback-preflight.sql", "rollback.sql", "README.md"}


def test_eam_asset_pjlx_contract() -> None:
    svg = require_er_fixture()
    if svg is None:
        return
    er_tables = scaffold_dynamic_bill.parse_tables(svg)
    required_asset_tables = {spec[0] for spec in scaffold_eam_asset_suite.BASIC_SPECS}
    missing_asset_tables = sorted(required_asset_tables - set(er_tables))
    if missing_asset_tables:
        # The current project ER fixture intentionally reuses ERP material
        # tables instead of carrying the optional EAM material master block.
        # The generic complex-form tests above still exercise the same PJLX
        # type/control contract; do not fabricate missing ER tables here.
        assert "EAMWLFL" in missing_asset_tables
        print("Skipped EAM asset-suite fixture: " + ", ".join(missing_asset_tables))
        return
    contract = scaffold_eam_asset_suite.build_contract(svg)
    pjlx_rows = [
        row for row in contract["maintain_metadata"] + contract["query_metadata"]
        if row["field"].upper().endswith("_PJLX")
    ]
    ordinary_rows = [
        row for row in contract["maintain_metadata"] + contract["query_metadata"]
        if not row["field"].upper().endswith("_PJLX")
    ]
    assert pjlx_rows and all(row["type"] == "S" and row["control"] == "S" for row in pjlx_rows)
    assert all(row["type"] in {"S", "D"} and row["control"] == "E" for row in ordinary_rows)
    assert any(row["field"].endswith("_YWRQ") and row["type"] == "D" for row in ordinary_rows)
    bills = {bill["visible_name"]: bill for bill in contract["bills"]}
    repair, rollback = scaffold_eam_asset_suite.render_pjlx_control_repair(bills)
    assert "56504" in repair and "@@ROWCOUNT<>25" in repair
    assert "56512" in rollback and "@@ROWCOUNT<>25" in rollback


def test_eam_asset_field_closure_and_labels() -> None:
    assert "--expected-database/--expected-server" in scaffold_eam_asset_suite.render_header()
    assert "N'TEST_DB'" in scaffold_eam_asset_suite.render_header("TEST_DB", "TEST_SERVER")
    # render_header must emit exactly the caller's values, never a hardcoded default.
    assert "CANARY_DB" not in scaffold_eam_asset_suite.render_header("TEST_DB", "TEST_SERVER")

    try:
        scaffold_eam_asset_suite.explicit_label({"name": "EAMTEST_CODE"}, "ER表 EAMTEST", require_cjk=True)
    except ValueError as exc:
        assert "缺少显示标签" in str(exc)
    else:
        raise AssertionError("missing ER label must fail closed")

    try:
        scaffold_eam_asset_suite.explicit_label(
            {"name": "EAMTEST_CODE", "label": "EAMTEST_CODE"},
            "ER表 EAMTEST",
            require_cjk=True,
        )
    except ValueError as exc:
        assert "物理字段名" in str(exc)
    else:
        raise AssertionError("physical field name cannot be used as a display label")

    basic = {
        "TST": {
            "visible_name": "测试基础资料",
            "fields": [{"name": "TST_ID", "label": "主键"}],
        }
    }
    maintain = [
        {
            "table_name": "测试基础资料",
            "po": 1,
            "field": "TST_ID",
            "display_name": "主键",
            "label": "主键",
        }
    ]
    scaffold_eam_asset_suite.validate_metadata_closure(basic, {}, maintain, [])
    try:
        scaffold_eam_asset_suite.validate_metadata_closure(basic, {}, [], [])
    except ValueError as exc:
        assert "字段集合未闭合" in str(exc)
    else:
        raise AssertionError("missing metadata field must fail closed")


def test_live_audit_script_structure() -> None:
    """The live audit is the only check that sees already-deployed metadata.

    It cannot be executed here (it needs a real target database), so guard its
    structure instead: every expected check present, no check pinned to one
    customer's column name, and the script still read-only.
    """
    import re

    sql = (Path(__file__).resolve().parent / "audit_live_dynamic_bills.sql").read_text(
        encoding="utf-8"
    )

    required = [
        "ROUTE_VALUE", "ROUTE_MARK", "ROUTE_OBJECT",
        "META_DATASET", "MAINT_HEADER_ORDER", "MAINT_DETAIL_ORDER", "QUERY_ORDER",
        "META_PHYSICAL_FIELD", "FIELD_CLOSURE", "META_MARKER",
        "META_NULL_RUNTIME_VALUE", "TYPE_CONTROL", "DATE_INIT",
        "DETAIL_ALIAS", "QUERY_ANCHOR", "QUERY_ALIAS_DUPLICATE",
        "RELATION_ROUTE", "RELATION_OBJECT", "RELATION_NULL_ALIAS",
        "BDJB_BASE", "BDJB_SQL", "WORKSPACE", "SYSMENU",
        "MIGRATED_REF_IN_BDJB", "MIGRATED_REF_IN_MODULE",
        "MIGRATED_REF_IN_METADATA", "MIGRATED_REF_IN_RELATION",
        "BDJB_UNKNOWN_IDENTIFIER",
    ]
    missing = [code for code in required if "'%s'" % code not in sql]
    assert not missing, "live audit lost checks: %s" % missing

    # A rename dependency must not be pinned to one customer's column name.
    assert "OLD_PHYSICAL_FIELD" not in sql, "hardcoded single-column check came back"
    assert "@MigratedColumns" in sql, "migration dependency map is missing"
    executable = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    assert "INSERT @MigratedColumns" not in executable, (
        "the audit must not ship one customer's renamed columns as a default"
    )

    # The unknown-identifier sweep must be a real identifier run-scan.
    assert "SUBSTRING(s.Txt,b.n,1) LIKE N'[A-Za-z_]'" in sql
    assert "NOT LIKE N'[A-Za-z0-9_]'" in sql

    # @Nums has exactly one column, n. Correlating on any other alias makes the
    # script fail to compile, so every @Nums reference must use n.
    nums_body = re.search(r"DECLARE @Nums TABLE\s*\(([^)]*)\)", sql, re.S)
    assert nums_body, "@Nums declaration missing"
    nums_first_column = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)", nums_body.group(1))
    assert nums_first_column and nums_first_column.group(1) == "n", (
        "@Nums must be keyed on a single column named n"
    )
    assert "," not in nums_body.group(1), "@Nums must declare exactly one column"
    for ref in re.findall(r"SUBSTRING\(s\.Txt,b\.n\+([A-Za-z_][A-Za-z0-9_]*),1\)", sql):
        assert ref == "n", (
            "@Nums is correlated on %r but its only column is n" % ref
        )

    # Detail-page checks must cover every detail PO, not just PO=2.
    assert "TRY_CONVERT(int,c.PO)>1" in sql, "detail checks are pinned to PO=2"

    # Each detail tab has its own physical table, so the document-number column
    # differs per PO.  Matching on IOBDZD_FTABLE flags every tab after the first.
    assert "f.DetailTable+N'_SJDH'" not in sql, (
        "detail alias check must match the alias, not the first detail table"
    )
    assert "[字段名] LIKE N'%[_]SJDH'" in sql

    # Scope must be caller-declared, not hardcoded to one module.
    assert "DECLARE @Scope TABLE" in sql, "audit scope is not parameterized"
    assert "@Scope" in sql and "FROM @Scope AS s" in sql
    for pinned in ("LIKE N'EAM%'", "LIKE N'%设备%'"):
        assert pinned not in sql, "audit scope is pinned to one module: %s" % pinned

    # 标识 triggers FF_BS only when non-empty; an empty string behaves as NULL.
    assert "NULLIF(c.[标识],N'') IS NOT NULL" in sql, (
        "marker check must ignore empty-string markers"
    )

    # Reporting must not be suppressed by a trailing THROW.
    assert "AuditStatus" in sql
    assert "THROW" not in executable, (
        "a THROW would hide the findings the caller needs"
    )

    for verb in ("INSERT INTO dbo.", "UPDATE dbo.", "DELETE FROM dbo.", "DROP "):
        assert verb not in sql, "live audit is not read-only: %s" % verb


def main() -> int:
    test_first_pass_generator()
    test_rule_extractor()
    test_dynamic_bill_contract_and_artifacts()
    test_basic_form_scaffold()
    test_complex_form_scaffold()
    test_eam_asset_pjlx_contract()
    test_eam_asset_field_closure_and_labels()
    test_live_audit_script_structure()
    print("All IMES database development and testing skill script tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
