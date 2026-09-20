#!/usr/bin/env python3
"""Extract a review matrix from exported BDJB rule SQL.

The parser is intentionally conservative. Its output identifies review candidates; live
database queries must still prove every predicate and aggregate against the exact document.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


FIELD_CANDIDATES = {
    "rule_id": ("rule_id", "bdjb_id", "id"),
    "command": ("command", "bdjb_command", "cmd", "bdjb_ml"),
    "order": ("order", "sequence", "sort", "bdjb_order", "bdjb_xh"),
    "purpose": ("purpose", "description", "name", "bdjb_mc", "bdjb_sm"),
    "sql": ("sql", "script", "text", "bdjb_sql", "bdjb_nr", "bdjb_zxsql", "bdjb_jb"),
}

IDENTIFIER_TOKEN = r"(?:\[[^\]]+\]|[#A-Za-z_][#A-Za-z0-9_$]*)"
QUALIFIED_TOKEN = rf"{IDENTIFIER_TOKEN}(?:\s*\.\s*{IDENTIFIER_TOKEN}){{0,2}}"
SQL_KEYWORDS = {
    "AND", "AS", "BETWEEN", "BY", "CASE", "COALESCE", "ELSE", "END", "EXISTS",
    "FROM", "IN", "INNER", "IS", "ISNULL", "JOIN", "LEFT", "LIKE", "NOT", "NULL",
    "ON", "OR", "OUTER", "RIGHT", "SELECT", "SET", "THEN", "UPDATE", "WHEN", "WHERE",
}


@dataclass
class Assignment:
    column: str
    expression: str
    mode: str


@dataclass
class UpdateAnalysis:
    target: str
    resolved_target: str
    assignments: list[Assignment]
    predicate_fields: list[str]
    where: str
    aggregate_functions: list[str]


@dataclass
class RuleAnalysis:
    rule_id: str
    command: str
    order: str
    purpose: str
    updates: list[UpdateAnalysis]
    warnings: list[str]


def mask_non_code(sql: str) -> str:
    chars = list(sql)
    i = 0
    state = "normal"
    while i < len(chars):
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if state == "normal":
            if ch == "'":
                chars[i] = " "
                state = "single"
            elif ch == '"':
                chars[i] = " "
                state = "double"
            elif ch == "[":
                chars[i] = " "
                state = "bracket"
            elif ch == "-" and nxt == "-":
                chars[i] = chars[i + 1] = " "
                i += 1
                state = "line_comment"
            elif ch == "/" and nxt == "*":
                chars[i] = chars[i + 1] = " "
                i += 1
                state = "block_comment"
        elif state == "single":
            chars[i] = "\n" if ch == "\n" else " "
            if ch == "'" and nxt == "'":
                chars[i + 1] = " "
                i += 1
            elif ch == "'":
                state = "normal"
        elif state == "double":
            chars[i] = "\n" if ch == "\n" else " "
            if ch == '"' and nxt == '"':
                chars[i + 1] = " "
                i += 1
            elif ch == '"':
                state = "normal"
        elif state == "bracket":
            chars[i] = "\n" if ch == "\n" else " "
            if ch == "]" and nxt == "]":
                chars[i + 1] = " "
                i += 1
            elif ch == "]":
                state = "normal"
        elif state == "line_comment":
            chars[i] = "\n" if ch == "\n" else " "
            if ch == "\n":
                state = "normal"
        elif state == "block_comment":
            chars[i] = "\n" if ch == "\n" else " "
            if ch == "*" and nxt == "/":
                chars[i + 1] = " "
                i += 1
                state = "normal"
        i += 1
    return "".join(chars)


def depth_map(mask: str) -> list[int]:
    depths: list[int] = [0] * (len(mask) + 1)
    depth = 0
    for index, ch in enumerate(mask):
        depths[index] = depth
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
    depths[len(mask)] = depth
    return depths


def keyword_matches(mask: str, keyword: str, start: int = 0) -> Iterable[re.Match[str]]:
    pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
    return pattern.finditer(mask, start)


def find_keyword_at_depth(
    mask: str, depths: list[int], keyword: str, start: int, depth: int
) -> int | None:
    for match in keyword_matches(mask, keyword, start):
        if depths[match.start()] == depth:
            return match.start()
    return None


def next_statement_boundary(
    mask: str, depths: list[int], start: int, depth: int
) -> int:
    candidates = []
    for keyword in (
        "UPDATE", "INSERT", "DELETE", "MERGE", "SELECT", "IF", "RETURN",
        "RAISERROR", "THROW",
    ):
        position = find_keyword_at_depth(mask, depths, keyword, start, depth)
        if position is not None:
            candidates.append(position)
    semicolon = mask.find(";", start)
    while semicolon != -1:
        if depths[semicolon] == depth:
            candidates.append(semicolon)
            break
        semicolon = mask.find(";", semicolon + 1)
    return min(candidates) if candidates else len(mask)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_identifier(value: str) -> str:
    parts = [part.strip().strip("[]") for part in re.split(r"\s*\.\s*", value.strip())]
    return ".".join(parts)


def split_top_level(value: str, delimiter: str = ",") -> list[str]:
    mask = mask_non_code(value)
    depth = 0
    start = 0
    parts = []
    for index, ch in enumerate(mask):
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        elif ch == delimiter and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return [part.strip() for part in parts if part.strip()]


def split_assignment(value: str) -> tuple[str, str] | None:
    mask = mask_non_code(value)
    depth = 0
    for index, ch in enumerate(mask):
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        elif ch == "=" and depth == 0:
            return value[:index].strip(), value[index + 1 :].strip()
    return None


def assignment_mode(column: str, expression: str) -> str:
    masked = mask_non_code(expression)
    if re.search(r"\b(?:SUM|COUNT|AVG|MIN|MAX)\s*\(", masked, re.IGNORECASE):
        return "aggregate-recalculation"
    if re.fullmatch(r"\s*(?:0+(?:\.0+)?|NULL|N?'')\s*", expression, re.IGNORECASE):
        return "constant-reset"
    column_name = normalize_identifier(column).split(".")[-1]
    if re.search(rf"\b{re.escape(column_name)}\b\s*[+-]", masked, re.IGNORECASE):
        return "incremental-delta"
    return "direct-overwrite"


def extract_aliases(from_fragment: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    pattern = re.compile(
        rf"\b(?:FROM|JOIN)\s+({QUALIFIED_TOKEN})(?:\s+(?:AS\s+)?({IDENTIFIER_TOKEN}))?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(from_fragment):
        table = normalize_identifier(match.group(1))
        alias = normalize_identifier(match.group(2) or "")
        if alias and alias.upper() not in SQL_KEYWORDS:
            aliases[alias.lower()] = table
    return aliases


def extract_predicate_fields(where_fragment: str) -> list[str]:
    fields: set[str] = set()
    for match in re.finditer(rf"({IDENTIFIER_TOKEN}\s*\.\s*{IDENTIFIER_TOKEN})", where_fragment):
        fields.add(normalize_identifier(match.group(1)))
    wrapped = re.compile(
        rf"\b(?:ISNULL|COALESCE|NULLIF|LTRIM|RTRIM)\s*\(\s*({QUALIFIED_TOKEN})",
        re.IGNORECASE,
    )
    for match in wrapped.finditer(where_fragment):
        fields.add(normalize_identifier(match.group(1)))
    direct = re.compile(
        rf"({QUALIFIED_TOKEN})\s*(?:=|<>|!=|>=|<=|>|<|\bIS\b|\bLIKE\b|\bIN\b|\bBETWEEN\b)",
        re.IGNORECASE,
    )
    for match in direct.finditer(where_fragment):
        candidate = normalize_identifier(match.group(1))
        if candidate.startswith("@") or candidate.upper() in SQL_KEYWORDS:
            continue
        fields.add(candidate)
    return sorted(fields, key=str.lower)


def extract_update_target(raw_target: str) -> str:
    cleaned = re.sub(r"^\s*TOP\s*\([^)]*\)\s*", "", raw_target, flags=re.IGNORECASE)
    match = re.match(rf"\s*({QUALIFIED_TOKEN})", cleaned)
    return normalize_identifier(match.group(1)) if match else normalize_space(cleaned)


def analyze_sql(sql: str) -> list[UpdateAnalysis]:
    mask = mask_non_code(sql)
    depths = depth_map(mask)
    analyses: list[UpdateAnalysis] = []

    for update_match in keyword_matches(mask, "UPDATE"):
        start = update_match.start()
        base_depth = depths[start]
        set_position = find_keyword_at_depth(mask, depths, "SET", update_match.end(), base_depth)
        if set_position is None:
            continue
        earlier_boundary = next_statement_boundary(mask, depths, update_match.end(), base_depth)
        if earlier_boundary < set_position:
            continue
        end = next_statement_boundary(mask, depths, set_position + 3, base_depth)
        from_position = find_keyword_at_depth(mask, depths, "FROM", set_position + 3, base_depth)
        where_position = find_keyword_at_depth(mask, depths, "WHERE", set_position + 3, base_depth)
        if from_position is not None and from_position >= end:
            from_position = None
        if where_position is not None and where_position >= end:
            where_position = None

        set_end = min(
            position for position in (from_position, where_position, end) if position is not None
        )
        raw_target = sql[update_match.end() : set_position]
        target = extract_update_target(raw_target)
        set_fragment = sql[set_position + 3 : set_end]
        from_end = where_position if where_position is not None else end
        from_fragment = sql[from_position + 4 : from_end] if from_position is not None else ""
        where_fragment = sql[where_position + 5 : end] if where_position is not None else ""

        assignments = []
        for item in split_top_level(set_fragment):
            pair = split_assignment(item)
            if pair is None:
                continue
            column, expression = pair
            assignments.append(
                Assignment(
                    column=normalize_identifier(column),
                    expression=normalize_space(expression),
                    mode=assignment_mode(column, expression),
                )
            )

        aliases = extract_aliases("FROM " + from_fragment) if from_fragment else {}
        resolved_target = aliases.get(target.lower(), target)
        statement = sql[start:end]
        aggregate_functions = sorted(
            {
                match.group(1).upper()
                for match in re.finditer(
                    r"\b(SUM|COUNT|AVG|MIN|MAX)\s*\(", mask_non_code(statement), re.IGNORECASE
                )
            }
        )
        analyses.append(
            UpdateAnalysis(
                target=target,
                resolved_target=resolved_target,
                assignments=assignments,
                predicate_fields=extract_predicate_fields(where_fragment),
                where=normalize_space(where_fragment),
                aggregate_functions=aggregate_functions,
            )
        )
    return analyses


def parse_json_rows(content: str) -> list[dict[str, Any]]:
    payload = json.loads(content)
    if isinstance(payload, dict):
        payload = payload.get("rows")
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ValueError("JSON input must be a list of objects or an object with a rows list.")
    return payload


def read_rows(path: Path, input_format: str | None = None) -> list[dict[str, Any]]:
    if str(path) == "-":
        content = sys.stdin.read()
        selected_format = input_format or "json"
        if selected_format == "json":
            return parse_json_rows(content)
        delimiter = "\t" if selected_format == "tsv" else ","
        return list(csv.DictReader(content.splitlines(), delimiter=delimiter))
    if path.suffix.lower() == ".json":
        return parse_json_rows(path.read_text(encoding="utf-8-sig"))
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def choose_field(
    rows: list[dict[str, Any]], requested: str | None, kind: str, required: bool = False
) -> str | None:
    keys = {str(key).lower(): str(key) for row in rows for key in row.keys()}
    if requested:
        match = keys.get(requested.lower())
        if not match:
            raise ValueError(f"Field {requested!r} was not found. Available: {sorted(keys.values())}")
        return match
    for candidate in FIELD_CANDIDATES[kind]:
        if candidate.lower() in keys:
            return keys[candidate.lower()]
    if required:
        raise ValueError(
            f"Could not identify the {kind} field. Pass --{kind.replace('_', '-')}-field. "
            f"Available: {sorted(keys.values())}"
        )
    return None


def row_value(row: dict[str, Any], field: str | None, fallback: str = "") -> str:
    if field is None:
        return fallback
    value = row.get(field, fallback)
    return "" if value is None else str(value)


def analyze_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[RuleAnalysis]:
    if not rows:
        raise ValueError("Input contains no rows.")
    fields = {
        "rule_id": choose_field(rows, args.id_field, "rule_id"),
        "command": choose_field(rows, args.command_field, "command"),
        "order": choose_field(rows, args.order_field, "order"),
        "purpose": choose_field(rows, args.purpose_field, "purpose"),
        "sql": choose_field(rows, args.sql_field, "sql", required=True),
    }
    analyses = []
    for index, row in enumerate(rows, start=1):
        updates = analyze_sql(row_value(row, fields["sql"]))
        warnings = []
        if not updates:
            warnings.append("No UPDATE statement was recognized; inspect this rule manually.")
        for update in updates:
            if not update.where:
                warnings.append(f"{update.resolved_target}: UPDATE has no recognized WHERE clause.")
            for assignment in update.assignments:
                if assignment.mode == "incremental-delta":
                    warnings.append(
                        f"{update.resolved_target}.{assignment.column}: incremental update requires idempotency review."
                    )
        analyses.append(
            RuleAnalysis(
                rule_id=row_value(row, fields["rule_id"], str(index)),
                command=row_value(row, fields["command"]),
                order=row_value(row, fields["order"]),
                purpose=row_value(row, fields["purpose"]),
                updates=updates,
                warnings=warnings,
            )
        )
    add_cross_rule_warnings(analyses)
    return analyses


def add_cross_rule_warnings(rules: list[RuleAnalysis]) -> None:
    targets: dict[str, list[tuple[RuleAnalysis, Assignment]]] = {}
    for rule in rules:
        for update in rule.updates:
            for assignment in update.assignments:
                column = normalize_identifier(assignment.column).split(".")[-1]
                key = f"{update.resolved_target}.{column}".lower()
                targets.setdefault(key, []).append((rule, assignment))

    for key, items in targets.items():
        modes = {assignment.mode for _, assignment in items}
        if "direct-overwrite" in modes and "constant-reset" in modes:
            warning = (
                f"{key}: direct overwrite and constant reset both exist. Prove split-document "
                "audit and partial cancel-audit with cumulative recalculation."
            )
            for rule, _ in items:
                if warning not in rule.warnings:
                    rule.warnings.append(warning)


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_markdown(rules: list[RuleAnalysis]) -> str:
    lines = [
        "# BDJB Static Review Matrix",
        "",
        "> Static candidates only. Validate predicates and counts against the exact database document.",
        "",
        "| Rule | Command | Order | Target | Set columns and modes | Predicate fields |",
        "|---|---|---|---|---|---|",
    ]
    for rule in rules:
        if not rule.updates:
            lines.append(
                f"| {markdown_escape(rule.rule_id)} | {markdown_escape(rule.command)} | "
                f"{markdown_escape(rule.order)} |  |  |  |"
            )
            continue
        for update in rule.updates:
            assignments = "; ".join(
                f"{item.column} [{item.mode}]" for item in update.assignments
            )
            lines.append(
                "| "
                + " | ".join(
                    markdown_escape(value)
                    for value in (
                        rule.rule_id,
                        rule.command,
                        rule.order,
                        update.resolved_target,
                        assignments,
                        ", ".join(update.predicate_fields),
                    )
                )
                + " |"
            )

    lines.extend(["", "## Predicate Fragments", ""])
    for rule in rules:
        for index, update in enumerate(rule.updates, start=1):
            lines.append(
                f"- Rule {rule.rule_id or '?'} update {index} `{update.resolved_target}`: "
                f"`{update.where or '[no WHERE recognized]'}`"
            )

    warnings = [(rule.rule_id, warning) for rule in rules for warning in rule.warnings]
    lines.extend(["", "## Review Warnings", ""])
    if warnings:
        for rule_id, warning in warnings:
            lines.append(f"- Rule {rule_id or '?'}: {warning}")
    else:
        lines.append("- No static warning was detected; live predicate validation is still required.")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract update targets, assignment modes, and predicate fields from BDJB SQL."
    )
    parser.add_argument(
        "--input", type=Path, required=True, help="JSON, CSV, TSV export, or - for stdin."
    )
    parser.add_argument(
        "--input-format", choices=("json", "csv", "tsv"), help="Required only to override stdin JSON."
    )
    parser.add_argument("--id-field")
    parser.add_argument("--command-field")
    parser.add_argument("--order-field")
    parser.add_argument("--purpose-field")
    parser.add_argument("--sql-field")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        rows = read_rows(args.input, args.input_format)
        rules = analyze_rows(rows, args)
        if args.format == "json":
            result = json.dumps([asdict(rule) for rule in rules], ensure_ascii=False, indent=2) + "\n"
        else:
            result = render_markdown(rules)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output:
        if args.output.exists() and not args.force:
            print(f"error: output already exists: {args.output}", file=sys.stderr)
            return 2
        if not args.output.parent.exists():
            print(f"error: output directory does not exist: {args.output.parent}", file=sys.stderr)
            return 2
        args.output.write_text(result, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
