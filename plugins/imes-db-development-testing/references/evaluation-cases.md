# Skill Evaluation Cases

Use these cases only when modifying or validating this skill. Evaluate the first actions and decision gates, not whether the agent eventually reaches a plausible answer.

## Exact BDJB Entry

Prompt shape: the user names an environment, document number, and exact `SELECT * FROM BDJB WHERE BDJB_PJLX=...` query.

Pass criteria:

- selects the project-mapped database tool and verifies database identity;
- executes the supplied query before schema-wide or module-wide searches;
- names candidate rules, targets, and predicates in the first investigation update;
- evaluates those predicates against the exact document.

## Ambiguous Environment

Prompt shape: the user reports a backfill issue but multiple customer databases can match.

Pass criteria: asks one environment question before connecting and does not substitute a convenient database.

## Ambiguous UI Status

Prompt shape: the user says a displayed completion or generation status is wrong without naming its column.

Pass criteria: proves the UI-to-column mapping from the returned dataset or source definition, or asks one focused question when read-only evidence cannot distinguish the fields.

## Split Reporting And Cancel-Audit

Prompt shape: an audit rule overwrites a header quantity from the current document and cancel-audit clears it.

Pass criteria:

- identifies current-document overwrite and unconditional reset as review warnings;
- builds the complete transition matrix;
- tests split audit, repeat audit, partial cancel, final cancel, and re-audit;
- requires cumulative recalculation when confirmed by business semantics.

## Production Write Request

Prompt shape: the project marks the production database tool read-only and the user requests a deployment or repair.

Pass criteria: investigates read-only, produces backup/deploy/repair/rollback artifacts, does not write through the read-only tool, and verifies externally executed deployment through exact definitions and data.

## Query Budget

Prompt shape: three confirmed lineage hops still do not resolve the business meaning.

Pass criteria: summarizes the evidence, identifies the unresolved term, and asks one focused question instead of starting an unbounded global search.

## Wrapped Custom Report

Prompt shape: the user asks for a no-parameter custom-report SQL and says the report designer automatically wraps the saved query in an outer `SELECT`.

Pass criteria:

- reads the report-wrapper pattern before writing SQL;
- emits one inner `SELECT` without a trailing semicolon, inner `ORDER BY`, CTE, or extra statements;
- verifies every field against the confirmed target schema and flags an absent user-supplied field instead of guessing;
- executes the query in the same derived-table wrapper shape and confirms one result set.

## New Business Tables

Prompt shape: the user asks for one header table and one detail table for a new IMES business document.

Pass criteria:

- resolves the customer and target environment, then verifies database identity and SQL Server compatibility;
- inspects the nearest related business tables before choosing names, keys, data types, audit columns, or tenant/account fields;
- separates confirmed local conventions from proposed design decisions;
- produces forward, rollback, and verification scripts with preconditions and a transaction-safe deployment shape;
- verifies primary/foreign keys, uniqueness, defaults, nullability, indexes, representative CRUD, rollback, and the expected client/query contract;
- does not deploy through a project-mapped read-only database tool.

## Module-Wide Physical Naming Migration

Prompt shape: the user gives two example fields such as `MODULE_ITEM_BH` and `MODULE_TYPE_BH`, asks for the traditional `MODULE_ITEMBH` convention, and authorizes a test-database write.

Pass criteria:

- verifies the explicitly selected database/tool identity and inspects the whole module before writing;
- builds a complete old-to-new map from physical columns, with table ownership and type/length/nullability, instead of limiting scope to the examples;
- discovers and plans updates for foreign-key column bindings, `SYS_TbColumn.字段名/GLZD`, `IOJCBDZD` key/display routes, current registration/layout/verification artifacts, and ER definitions;
- fails closed on missing old columns, existing target names, unreviewed module references, or row-count mismatches;
- provides preflight, transactional forward, verification, and guarded reverse scripts;
- verifies old-name absence, new-name completeness, property and foreign-key preservation, runtime lookup/JOIN SQL, and zero unintended data changes;
- keeps old names only in explicitly labeled historical evidence or rollback maps.

## Ambiguous Form Request

Prompt shape: the user asks to create a "form" but mentions both database tables and a visible iMES screen.

Pass criteria: distinguishes database objects from MFC client forms, confirms the intended deliverables, and does not claim that database DDL alone creates the client UI, menu, or permission entry.

## Dynamic Bill Database Contract

Prompt shape: the user asks to add a transfer/transaction bill by creating tables, registering `IOBDZD`/`IOJCBDZD`, setting `SYS_TbColumn`, adding `SYSWSPACE` permission, and configuring `IOYYGX`/`IOPOPDLG` references or upstream/downstream links, while limiting work to the database layer.

Pass criteria:

- reads `references/document-form-contract.md` and `references/schema-development.md`;
- distinguishes the physical table, `IOBDZD`, `IOJCBDZD`, `SYS_TbColumn`/`v_tbcolumn`, `IOYYGX`, `IOPOPDLG`, `BDJB`, `SYSWSPACE`, and optional `sysmenu` responsibilities;
- uses the source-derived runtime order and verifies actual target schema instead of assuming metadata columns or enum meanings;
- checks `PO` header/detail rows, lookup display/key round trips, `GLZD` joins, relation placeholder/result-set shape, red/blue branches, and role-visible workspace hierarchy;
- treats missing lifecycle `BDJB` rules or unresolved metadata as incomplete and keeps MFC resources, command IDs, and client packaging outside the database deliverable;
- respects fixed database routing and read-only MCP restrictions, producing forward/rollback/verification artifacts for any authorized test write.

## Generic Base-Form Database Contract

Prompt shape: the user asks for a database-only basic-data form, provides two master tables, and expects the legacy iMES client to open them from `SYSWSPACE`.

Pass criteria:

- confirms the active `AutoOpen`/`UForm1` route from source and distinguishes it from the `IOBDZD` bill path;
- checks the legacy physical-table/field-prefix rule before choosing names, rather than copying an underscore-separated V2 name blindly;
- creates forward, rollback, verification, and transactional CRUD-test artifacts with target identity guards;
- registers `IOJCBDZD_BTYPE=1`, `SYS_TbColumn` under the visible form name, and a role-visible workspace parent/leaf;
- does not invent `IOYYGX`, `IOPOPDLG`, or `BDJB` rows when no relation or lifecycle consumer is requested;
- classifies each object before counting tables and does not claim a complete client form or business module from database metadata alone.

## Dynamic Header-Detail Classification

Prompt shape: the user asks for two business forms, one being a reusable template containing multiple project rows, requires a shared document number with header/detail behavior, and limits work to the database layer.

Pass criteria:

- reads ER/cardinality evidence and active `AutoOpen`, bill initialization, and detail-page paths before interpreting “two forms” as two physical tables;
- keeps the independent project lookup as `BTYPE=1` but models the template as an `IOBDZD` header/detail bill, never as `BTYPE=2/UForm2`;
- explains that `BTYPE=2` is a category tree plus a separately named right-side dataset, not a unified document save unit;
- registers one visible template bill name with `IOBDZD` header/detail tables and keys, unique `BH/MARK`, `SYS_TbColumn.PO=1/2`, active `BDJB`, and form plus operation permissions;
- verifies the header hard fields and every detail page's first-field table prefix, `FID`, `单号`, `分录号`, real `关键字段`, line identity/uniqueness, foreign keys, and lookup display/key round trips;
- executes transactional header/detail CRUD and audit/cancel-audit, proves `AutoOpen` resolves through `IOBDZD`, and confirms zero test residue;
- rejects both a header-only template and a `BTYPE=2` directory layout as incompatible with the requested header/detail behavior.

## Dynamic Header Control Initialization

Prompt shape: a newly registered `IOBDZD` header/detail bill shows a generic control-initialization error when opened.

Pass criteria:

- follows the runtime log to the last completed initialization stage and inspects the active header-control creation path;
- queries all `PO=1` metadata in order and recognizes nullable metadata such as `控件` as potentially mandatory at runtime;
- confirms control codes against both source branches and a working dynamic bill from the same client/database version instead of assigning a guessed universal value;
- produces a fail-closed, transactional metadata repair with an exact field set and affected-row assertion on an authorized test environment;
- allocates positive `RID` values from the target's runtime `MAX(RID)+offset` instead of emitting `NULL` or fixed cross-environment numbers, and covers both maintenance and query metadata;
- verifies exact per-field control codes, non-null/positive/unique `RID`, type, label, flags and layout in both `SYS_TbColumn` and `v_tbcolumn`, then reruns contract/CRUD checks and requests a real form reopen.

## Dynamic Bill Number Format Contract

Prompt shape: a new or repaired `IOBDZD` bill has an empty `IOBDZD_FORMAT`, and the user says the numbering format must not be blank and new forms should default to `YYMM####`.

Pass criteria:

- reads `CBill::OnTynew`/`GenDanhao` and the target `PRD_GETDANHAO` definition, proving that the runtime lookup uses visible `IOBDZD_MC` and that `FORMAT` controls the numbering branch;
- distinguishes `IOBDZD_FORMAT` from `IOBDZD_BH` (the header `PJLX`/permission type), `IOBDZD_MARK` (number prefix), and `IOBDZD_BILLNO` (not used by the current numbering entry point);
- normalizes a missing/blank new-contract format to exactly `YYMM####`, preserves a reviewed non-empty format, and rejects generated `NULL`/empty/whitespace values;
- queries `BascData`, `CurMonth`, and `ModifyDate` before an existing repair and updates only the exact empty target rows with database/instance gates, old-value assertions, affected-row assertions, and symmetric rollback;
- verifies the route by `IOBDZD_MC`, confirms the physical/metadata `PJLX` mapping remains intact, runs the authorized test-database verification, and reopens the bill to confirm a new number is returned.

## Dynamic Bill Fixed-Field Gate

Prompt shape: the user asks to register a `CBill`-style point-inspection template with a header/detail structure, but the supplied header omits `PJLX` or another standard field.

Pass criteria:

- classifies the form as an `IOBDZD` bill and reads the active `CBill` initialization and layout paths before designing metadata;
- fails closed before forward deployment when any header field is missing from the fixed card: HID, date, voucher type, document number, print count, audit state, creator, auditor, or summary; it also requires FID, document number, and line number for every detail page;
- checks each required semantic field against both `sys.columns` and `v_tbcolumn`, including `PO`, non-null/positive unique `RID`, and source-proven control/layout settings;
- requires `PJLX` to be a physical required field holding the `IOBDZD_BH` code, with `必填=1/切换=1/GLZD=IOBDZD_BH`, and requires the proven `SHBZ` mapping, normally `切换=1/GLZD=LSDJZT_BH`;
- creates guarded forward/rollback/verification artifacts only after the complete card is proven, then requires a real reopen of the original form.

## Dynamic Bill Search Dataset

Prompt shape: a new dynamic bill passes header/detail initialization but then reports a title SQL error near `FROM`, and the logged SQL is `SELECT  FROM <valid joins> WHERE 1=2`.

Pass criteria:

- follows the empty field list rather than misdiagnosing a physical column whose suffix resembles `FROM`;
- proves from the active container/search source that the search page reads `<IOBDZD_MC>查询` fields while using the original bill's cross-table joins;
- creates a separate query metadata field set without inventing another `IOBDZD` registration;
- removes duplicate output aliases such as header/detail `单号`, preserves required identity/filter/translation fields, and checks every physical field;
- executes the client-equivalent title SQL and its derived-table paging/count wrapper, then runs representative query CRUD and a real form reopen.

## Dynamic Bill Cross-Table Closure

Prompt shape: a dynamic bill's title/preview SQL contains `SELECT <fields> FROM )`, while the route and query metadata appear to exist; the user asks why the generated `FROM` is empty and wants the database-form contract improved.

Pass criteria:

- reads the active `GetCrossTable` implementation and recognizes its caught ADO/metadata exception path returns an empty string;
- independently materializes `GetDataField(<MC>查询)` and `GetCrossTable(<MC>)`, distinguishing an empty query field list from an empty cross-table source;
- checks the `IOBDZD -> IOPOPDLG_JOINSTR -> IOJCBDZD_TABLE` source priority and every non-empty `GLZD` row's `字段名`/`IOJCBDZD_TABLE`/`IOJCBDZD_VKEY`/`LMark`/`RMark` closure, treating no-alias markers as empty strings rather than `NULL`;
- executes the generated `LEFT JOIN` and the client-shaped title SQL inside its derived-table wrapper, failing closed on `FROM )` or an unparseable join;
- repairs only the confirmed metadata rows with guarded old-value assertions, preserves the separate query dataset and standard button/layout/width contracts, and requires a real maintenance/search/preview reopen after read-only verification.

## Dynamic Header Default Layout

Prompt shape: a new dynamic bill opens, but its custom header fields have poor coordinates, widths, or heights; the user asks to use a working same-version equivalent as the layout reference.

Pass criteria:

- reads same-version, equivalent `PO=1` metadata and confirms coordinate units, canvas bounds, row baselines, and control dimensions before updating the target;
- maps confirmed semantic anchors (`YWRQ/PJLX/SJDH/ZDR/SHR/SHBZ/ZY`) to reference rectangles and allocates custom fields to unused compatible slots instead of assigning a universal coordinate or width;
- preserves hidden identity coordinates at zero, handles `EM` height deliberately, populates `列宽`, and keeps query-grid coordinates separate;
- produces an explicit mapping plus forward/rollback/verification checks for positive dimensions, bounds, non-overlap, and deterministic reruns;
- applies the change only to the authorized test database, reruns the full dynamic-bill contract, and requests/reports a real form reopen.

## Dynamic Header Fixed Anchors And Natural Order

Prompt shape: a dynamic bill's generated header is technically non-overlapping but places ordinary fields too tightly or too far apart; the user says `制单人`/`审核人`/`摘要` have fixed coordinates and that `审核` determines the header lower bound.

Pass criteria:

- reads `CBill::OnSize` and the active `MoveToItemSJ`/`MoveToItem`/`MoveToMid` helpers before treating footer controls as ordinary metadata slots;
- preserves the working bill's exact `ZDR`/`SHR`/`ZY` footer rectangles and `SHBZ` audit footprint, including the audit-bottom `headerLowerBound` rule;
- walks all visible header fields, including `SHBZ`, in stable row order and tries the current row before wrapping. Each row begins at the reference left coordinate and each later input follows the runtime measured-label formula; it rejects fixed-column estimates, overlap, and materially sparse jumps, and reflows only non-fixed rows when an `EM` field needs more height;
- adds verification assertions for fixed-anchor equality, same-row audit/ordinary non-overlap, conditional natural ordering/gap range (gap only when audit wraps), variable-field bottom above the audit lower bound, canvas bounds, and query-coordinate separation;
- records the source-derived rule in the reusable skill and keeps the database-only scope separate from client runtime resizing.

## Dynamic Header Labels Defaults And Multiline Sizing

Prompt shape: a date or text field overlaps the preceding field because the visible label is rendered outside the metadata rectangle; a common summary uses an oversized `EM`; the user asks for common defaults and adaptive custom fields.

Pass criteria:

- inspects the active dynamic-control source and confirms that `标签名` is rendered to the left of `E`/date controls, so spacing checks include label width rather than input rectangles alone;
- preserves the working common control contract, including single-line `ZY`/摘要 where the reference uses `E`, and uses `EM` only for a proven long-text custom field with adaptive height;
- distinguishes source-proven defaults such as version/audit initial values from fields initialized by the client/numbering path, leaving unproven custom defaults blank;
- verifies label-inclusive non-overlap, natural spacing, fixed anchors, audit lower bound, and the actual client-shaped form; when adaptive spacing is requested, requires a client runtime reflow implementation rather than treating database-only metadata changes as sufficient.

## New Form Label Width Must Be Visible On First Open

Prompt shape: a newly generated form loads data, but the first grid view truncates a field label; a three-character label fits while a four-character label is only partly visible. The user asks to use the field label width and improve the skill.

Pass criteria:

- treats `列宽` as the grid-column width and keeps it separate from the form-control layout `宽度`;
- defaults each visible new field to the complete `标签名` width using the shared `metadata_width.py` rule, with the active baseline of three Chinese characters = `840`, four Chinese characters = `1125`, ASCII counted as half-width cells, and `15`-unit rounding;
- emits `类型=D` for physical `date`/`datetime`/`datetime2` fields and `类型=S` otherwise; ordinary fields use `控件=E`, while `*_PJLX` uses `控件=S`; case-insensitive contract input is normalized rather than copied through;
- preserves an explicitly wider data column but rejects an explicitly narrower visible-label width during generation and static SQL validation;
- calculates maintenance and query widths independently, previews exact old values for existing repairs, preserves already wider columns, and verifies both `SYS_TbColumn` and `v_tbcolumn` before a real first-open check.

## New Dynamic Bill Standard Menu Buttons

Prompt shape: a newly registered header/detail bill opens, but its toolbar is missing standard actions or their parameters differ from the Sales Order reference; the user asks to make the button contract reusable.

Pass criteria:

- adds exactly one database `sysmenu` row for each required action: `显示关联单据`、`保存列宽`、`列配置`、`从EXCEL导入`、`说明`、`附件`、`复制分录`;
- copies the verified Sales Order tuple for `topfloor/submenu/xh/icon/pmenu/trimenu/uid`, records it in the contract, and validates all seven rows by the new bill name;
- inserts the rows in the same guarded transaction as the dynamic-bill metadata while preserving unrelated custom menu rows;
- verifies duplicate/missing rows and parameter drift, and keeps client command/resource wiring outside the database-only deliverable.

## Metadata Base Table Versus Derived View

Prompt shape: a metadata migration is based on fields visible in `v_tbcolumn`, but the target `SYS_TbColumn` rejects the proposed columns or the script confuses `IOJCBDZD_*` mapping fields with maintenance metadata.

Pass criteria:

- inspects `sys.columns` for `IOJCBDZD`, `SYS_TbColumn`, and the `v_tbcolumn` definition/dependencies before writing SQL;
- distinguishes base-table columns from view-only/derived fields and refuses to add or update an unconfirmed column;
- writes only confirmed metadata columns, with target-identity and affected-row guards;
- reads back the base rows and derived runtime projection, verifies every metadata field maps to a real business column, and executes the client-equivalent select;
- provides a rollback artifact and reports a fail-closed result when the target schema differs.

## Dynamic Header Audit Natural Gap

Prompt shape: a dynamic header has fewer fields than the working reference, so the last ordinary field is followed by a large empty area before `审核`; the user asks to move the audit control up and preserve the client layout behavior.

Pass criteria:

- reads `CBill::OnSize` and `MoveToMid` and proves that the audit bottom determines the table top, rather than treating `审核` as an unrelated ordinary field;
- captures the reference audit left/width/height and the measured natural row gap, then first attempts the audit in the current row using its complete label/input/help footprint; derives a new audit top from the last earlier non-fixed visible header bottom plus that gap only when the audit cannot fit horizontally;
- keeps `ZDR/SHR/ZY` and other fixed runtime anchors outside the ordinary-field reflow, and does not change field names, metadata type/control, widths, or order during a coordinate-only repair;
- creates a target-identity-guarded forward/rollback/verification set with an exact old-top assertion, one-row affected-count assertion, audit-bottom assertion, and client-derived table-top assertion;
- verifies both `SYS_TbColumn` and `v_tbcolumn`, rejects a wrapped-row gap below 10 or materially different from the evidence, confirms same-row footprints do not intersect, and requires a real maintenance-page reopen after the database check.

## Dynamic Header Horizontal Packing And Help Footprint

Prompt shape: the user asks to put `审核` on the existing row when there is room, move it to the next row only when necessary, and account for fields that have a help/browse button; they also warn that existing coordinates were hand-tuned and must only be micro-adjusted.

Pass criteria:

- reads `CreateDlgItemWithArrayDateTime`, `CDataEdit::OnSize/OnPaint`, `CBCGPEdit::OnChangeLayout`, and `CBill::OnSize` to establish the coordinate and control footprint; the current BCG default browse-button width is 20, while a custom image uses `max(20,imageWidth+8)`;
- snapshots all current `SYS_TbColumn` header coordinates before editing and changes only the minimum `左坐标/顶坐标/宽度/高度` needed to remove a proven collision or fill a proven gap; field names, labels, help strings, parameter placeholders, `GLZD`, `LMark/RMark`, `RID`, order, and flags remain unchanged;
- lays out visible fields in stable `顺序` order, including `SHBZ`: calculate measured label width + label/input gap + outer edit rectangle + help-button occupancy + right margin, keep the field on the current row when the complete footprint fits, and wrap to the next row only when it crosses the reference right boundary;
- treats `SHBZ` as the header lower-bound anchor after packing, checks that non-fixed fields do not cross its bottom, and applies the reference natural vertical gap only when the audit is wrapped below a prior row;
- validates same-row outer rectangles and label-inclusive footprints, checks that help-bearing outer widths leave room for the measured browse button, validates the conditional audit gap, produces an exact old/new coordinate rollback, and requires a real maintenance-page reopen.


## Nullable Metadata Sentinel And Derived SQL Generation

Prompt shape: a new or repaired `BTYPE=1/UForm1` basic-data form reports `Invalid column name 'FF_BS'`; the metadata appears to use `标识=0`, and the user asks for root-cause analysis plus a skill improvement.

Pass criteria:

- reads the active `GetDataField` source and proves that non-empty `标识` emits `sum(case FF_BS ...)`;
- checks the SQL type and actual values in `SYS_TbColumn` and `v_tbcolumn`, recognizing string `0` as non-empty rather than a universal false sentinel;
- refuses to add a guessed `FF_BS` business column and instead applies a guarded metadata-only repair when the ordinary-form contract requires null/blank markers;
- updates the forward artifact so redeployment cannot recreate the bad marker, and adds a verification assertion for null/blank markers;
- reconstructs the client-shaped projection and executes a physical-table equivalent `SELECT`, failing if generated SQL contains `FF_BS`;
- tests initial load and search separately, flags a hard-coded absent search column as client scope, and does not claim the whole form is fixed from an initial-load pass alone.

## BTYPE=1 Basic Form Contract

Prompt shape: the user asks for one or more simple basic-data forms backed by one table each, with generic `UForm1` maintenance and workspace permissions.

Pass criteria:

- classifies each object as `IOJCBDZD_BTYPE=1` rather than `BTYPE=2` or `IOBDZD` using the active `AutoOpen/UForm1` path;
- creates one complete physical table, one `IOJCBDZD` route, visible-name `SYS_TbColumn` rows, and role-visible workspace/operation permissions;
- confirms the legacy physical-name/primary-field prefix rule and maps every metadata field to `sys.columns`;
- does not invent `<visible name>查询`, `IOBDZD`, `IOYYGX`, `IOPOPDLG`, or `BDJB` rows without a proven consumer;
- runs client-equivalent SELECT and transactional CRUD, checks duplicate-key handling without poisoning the test transaction, verifies role visibility, and confirms zero residue.



## BTYPE=1 快速脚手架与三阶段门禁

Prompt shape: the user gives one confirmed physical table and field list for a simple basic-data form, asks to reduce repeated work, and authorizes improvement of the skill.

Pass criteria:

- reads `references/basic-form-fast-path.md` and classifies the request as BTYPE=1 only when no header/detail or lifecycle behavior is present;
- collects a compact contract instead of repeating broad schema discovery, rejects unsafe identifiers, missing labels, missing unique business key, prefix mismatch, or incomplete workspace data;
- uses `scripts/scaffold_basic_form.py` to generate preflight, forward, verification, isolated CRUD, rollback-preflight, rollback, and README artifacts without connecting or writing;
- keeps `nID` out of `SYS_TbColumn` inserts, identifies role columns from `RID`/`admin`, defaults all newly generated controls to `E`, and metadata `标识` to NULL;
- requires the execution gates preflight -> authorized forward -> verification/CRUD and uses the same `sqlcmd -b -f 65001` path;
- does not claim that generated database metadata creates MFC forms, menus, or installers, and switches to the dynamic-bill contract when the request is not truly single-table.

## InitForm 后空指针崩溃与锚点字段缺失

Prompt shape: the user reports a dynamic bill (e.g. a point-inspection record) opens with `初始化表单出错:00000000` in a test database, asks for a database-only fix, and authorizes local-test writes and skill improvement.

Pass criteria:

- maps `00000000` to the `catch(...)`/`GetLastError()`-returns-zero path and identifies the failure as occurring after `InitForm()` succeeds, without editing client code;
- proves from the active source that `billdata.iXXX` anchors (`PJLX`/`YWRQ`/`ZY`) become 0 and `GetDlgItem(0)` returns NULL when the physical header or `PO=1` metadata lacks them;
- compares the broken bill with a same-version working bill and mirrors physical column types/defaults plus maintenance/query `SYS_TbColumn` rows only for proven anchors;
- deploys inside a database/instance-guarded transaction with row-count assertions, `RID=MAX(RID)+1` continuity, `标识=NULL`, no `nID`, full role authorization, plus symmetric rollback and a read-only preflight;
- verifies by simulating the `InitForm` `v_tbcolumn` scan, isolated transactional CRUD with zero residue, unchanged reference route, and a real client reopen of both maintenance and query pages;
- records the pattern in `references/patterns.md` and adds a matching evaluation case without customer names, document numbers, or credentials.

## 查询页单一 PO 与显示名/标签名唯一

Prompt shape: 用户报告动态单据查询页 `SYS_TbColumn` 同一 `PO` 内 `顺序`/`显示名`/`标签名` 重复，或查询页误带 `表头=1`，要求仅在数据库层修复并完善 skill。

Pass criteria:

- 先读写查询页与维护页 `PO/顺序/表头/显示名/标签名`，用 `GROUP BY` 与 `COUNT(DISTINCT)` 确认重复分布，而不只统计行数；
- 将查询页定性为单一 `PO=1` 扁平字段集：`表头=0`、`顺序` 1..n 连续、`显示名`/`标签名` 各自唯一，并明确表头/明细同义字段去重映射（`ID→HID/FID`、`单号→单号/明细单号`、`备注→备注/行备注`）；
- 部署在带数据库/实例门禁的事务内做 `顺序` 重排、`表头` 清零、去重，并给出对称 rollback 与只读预检；
- 验证模拟 `LoadGridSet` 以 `顺序` 为列索引读取 `v_tbcolumn`，断言无重复、无锚点行、`显示名`/`标签名` 唯一，并用原单据交叉表拼标题 SQL 与派生表包装执行；
- 记录到 `references/patterns.md` 并补充本用例，不含客户名、单号或凭据。

## 查询排序字段与 PJLX 自适应宽度

Prompt shape: 用户报告动态单据查询页提示“单号无效”，要求查询页必须有“单号、日期”用于排序；同时凭证类型列只能显示约六个字，要求按实际单据名称自适应宽度，并要求把经验固化到 skill。

Pass criteria:

- 先确认独立查询字段集，证明查询页恰有一个可见、必填的单号字段和一个可见、必填的日期字段，单号保留唯一查询关键字段，日期为 `类型=D`；
- 用 `GetDataField(<单据名>查询)` 与 `GetCrossTable(<单据名>)` 重放标题 SQL，再执行派生表 `ORDER BY 单号,日期`，确认两个别名可解析；
- 读取 `IOBDZD_BH -> IOBDZD_MC` 显示映射，按最长有效 `IOBDZD_MC` 而不是短码长度或标签长度计算 PJLX 宽度，维护页和查询页分别保存布局宽度/网格列宽；
- 以旧值快照、数据库/实例门禁、影响行数断言和对称 rollback 执行最小元数据修复，不修改业务表和业务数据；
- 验证最长路由名称完整显示、PJLX 仍为 `类型=S/控件=S/切换=1/GLZD=IOBDZD_BH`，查询页“单号、日期”排序可执行，并记录到 `references/patterns.md`。

## 明细单号别名与实测 PJLX 控件宽度

Prompt shape: Release 版本动态主从单据维护页能打开，但翻前单报 `列名“单号”无效`；同时凭证类型静态控件只能显示约六个字，用户要求数据库层修复并固化经验。

Pass criteria:

- 从 Release 日志确认明细投影的 `<DETAIL>_SJDH` 当前别名为“明细单号”，而外层翻前单谓词固定使用“单号”；不把它误判为物理字段缺失；
- 通过带旧值断言的元数据修复将明细维护页 `显示名/标签名` 设为“单号”，验证 `v_tbcolumn` 和客户端同形派生表过滤、分录号排序均可执行；
- 从活动客户端确认维护页 `PJLX` 使用 22 号宋体加粗静态控件，按最长有效 `IOBDZD_MC` 做文本测量并加余量，维护 `宽度` 与查询 `列宽` 分开更新，保持 `类型=S/控件=S/切换=1/GLZD=IOBDZD_BH`；
- forward/rollback/verification 均有数据库/实例门禁、完整旧值快照、影响行数断言，且不修改业务表和业务数据；
- 运行 skill 自测和 quick validator，最后要求真实 Release 重开并执行翻前单及最长路由值显示检查。

## 表头坐标叠压与页脚锚点错位

Prompt shape: 用户报告动态单据（如点检记录单）维护页表头字段坐标自适应不对、各表头互相叠压，要求仅在数据库层重新优化坐标并完善 skill。

Pass criteria:

- 先读客户端 `CreateDlgItemWithArrayDateTime`（`rect.left=左坐标`、`rect.top=顶坐标`、`right=left+宽度`、`bottom=top+高度`）与 `CBill::OnSize`（`MoveToItemSJ/MoveToItem/MoveToMid` 动态重排 `ZDR/SHR/SHBZ/PJLX/ZY`），明确坐标是客户区像素值、头部必须位于工具栏下/网格上；不改客户端代码；
- 以同库同版本可正常显示、布局等价的单据为证据抽取 `PO=1` 标准锚点坐标；每行首字段回到参考最左坐标，后续输入框按“前一输入框右边界 + 视觉间隔 + 下一标签运行时实测宽度 + 5”递推，不用固定列坐标、字符数或每字像素估算；
- 只改 `左坐标/顶坐标/宽度/高度`，不动字段名/PO/RID/显示名/标签名/类型/控件/表头/必填/只读/列宽/顺序；主键 `ID` 设为隐藏锚点 `0,0,0,0`；每行按 `表名+PO+字段名` 精确更新并断言影响行数；
- 部署在带数据库/实例门禁的事务内，给出对称 rollback 与只读预检；rollback 精确还原旧坐标；
- 验证模拟 `CreateDlgItemWithArrayDateTime` 读取 `v_tbcolumn`，断言非主键字段宽/高 `>0`、左/顶非负、同 `顶坐标` 分组内字段水平区间无重叠、页脚锚点等于标准坐标、跨维护+查询 `RID` 唯一；再用 `OnSize` 逻辑核对页脚可被重排且不与网格冲突；
- 记录到 `references/patterns.md` 并补充本用例，不含客户名、单号或凭据。
## 审核字段写成复选框 / GLZD 缺失

Prompt shape: 用户报告动态单据维护页或查询页审核字段显示为复选框、不显示审核状态文字，要求仅在数据库层修复并完善 skill。

Pass criteria:

- 先读 `SYS_TbColumn` 中维护页与查询页 `_SHBZ` 的完整契约（类型/控件/GLZD/切换/默认值/必填/只读/列宽），并检查物理列类型（通常 `bit NOT NULL DEFAULT 0`）；
- 用同库同版本、可正常运行的维护页与对应查询页提取 `_SHBZ` 的完整契约；其中 `类型`、`控件`、`GLZD`、`切换`、必填、只读和列宽均须由实际元数据确认，不能把某一账套的值当作默认值；
- 明确 `GLZD=LSDJZT_BH` 通过 `IOJCBDZD_Vkey`（而非 `IOJCBDZD_BH`）解析 `LSDJZT` 字典，不得把审核状态误写成 `类型=C/控件=C` 复选框；
- 两行均按 `表名+字段名` 精确更新并断言各影响 1 行，事务带数据库/实例门禁；给出对称 rollback（还原 `C/C`、GLZD 空、必填=1）与只读预检；
- 验证确认维护页/查询页 `_SHBZ` 均满足上述契约、字典行存在、物理列仍 `bit NOT NULL`、`_SHBZ` 总行数仍为 2；
- 记录到 `references/patterns.md` 并补充本用例，不含客户名、单号或凭据。

## 主从动态单据固定九步回归门禁

Prompt shape: 用户要求新建或修复一个类似物料需求分析的主从动态单据，并要求把本次踩坑固化，避免下次遗漏字段、BOM 联动、查询排序、布局或 Release 流程。

Pass criteria:

- 按固定顺序执行并记录九步：目标身份/`IOBDZD` 分类、固定字段卡、业务语义与数量归属、BOM 版本联动、查询字段/别名、客户端派生 SQL、PJLX 与表头布局、BDJB/工作区/`sysmenu`/角色、事务回滚与真实 Release；任一步失败立即 `review-blocked`；
- 新物理字段先对照同模块 `sys.columns` 和既有表确认拼音首字母缩写/前缀、运行时后缀和重名冲突，不能用临时英文名或只改中文标签替代命名契约；
- 固定字段卡包含表头 `HID/YWRQ/PJLX/SJDH/PRINT/SHBZ/ZDR/SHR/ZY` 和明细 `FID/SJDH/FLH`，日期元数据 `类型=D`，普通控件 `E`，`*_PJLX` 控件 `S`，物理非空 `SHBZ` 有默认值；
- 明确表头只放成品/分析物料、BOM 版本和成品分析数量，逐物料采购价/需求/库存/在途/到货未检验/净需求在明细，并为每个数量记录来源、公式、单位和空值策略；
- 证明 BOM 版本帮助按当前成品过滤，并用多版本和无 BOM 负例验证切换后的清空/重载；
- 证明查询页单一 `PO=1`、`表头=0`、顺序连续、别名唯一且有可见必填“单号/日期”，日期为 `D`；重放查询排序、翻前单外层“单号”过滤以及 `SELECT  FROM`/`FROM )` 静态检查；
- 维护 `PJLX` 控件宽度和查询 `列宽` 分开按活动字体/DPI 与最长路由名称实测，表头从同版本参考单据的最左坐标递推并验证标签-inclusive 碰撞、固定页脚锚点和审核底边；
- 校验有效 BDJB、SYSWSPACE/角色权限及七个标准动态单据 `sysmenu` 行；
- forward/rollback/verification/CRUD 均有数据库与实例门禁、完整旧值/影响行数断言、事务和零残留；只有真实 Release 维护/查询重开、翻前翻后及新增保存冒烟完成后才允许报告完成，未执行客户端动作必须显式报告。

## GLZD/LMark/RMark 关联显示与帮助传参

Prompt shape: 用户要求在既有单据增加关联主数据的名称/规格管理显示字段，或建议将稳定的业务编号字段改为另一个业务标签；相关单据使用帮助与版本传参。

Pass criteria:

- 先读取目标维护页和查询页的 `SYS_TbColumn`/`v_tbcolumn`、相关 `IOJCBDZD` 行、业务表列和 `GetCrossTable/GetDataField` 源码，而非按中文字段名猜映射；
- 区分保存编号的 `GLZD + 切换=1` 输入行和 `GLZD='' + RMark` 的关联显示行；不把物理表存在相似列当成替换关联显示的授权；
- 验证 `LMark` 是关联表别名、`RMark` 是业务侧别名，空别名保存空字符串；为每一组关联字段重放 JOIN 与投影。任何参考单据的别名仅作方向证据，不得向目标表硬套；
- 保持既有 `字段名/显示名/标签名/帮助/GLZD/切换/LMark/RMark/RID` 和精确帮助占位符，特别是不把“物料编号”自由改名；
- 对维护页和查询页执行客户端形状的 `SELECT ... WHERE 1=2` 及派生表包装；随后验证帮助选值、依赖帮助/BOM 参数传递、编号存储与名称/规格关联显示。

## Existing Dynamic-Bill Reference Filter

Prompt shape: 用户指出已有动态单据的参照功能，要求“过期的不要参照出来”或调整一条已有参照过滤 SQL，并限制为数据库开发。

Pass criteria:

- 先读项目手册和 `references/reference-fast-path.md`，记录目标单据/操作名/来源单据，不启动新建动态单据的全量扫描；
- 先核对 `DB_NAME()`、`@@SERVERNAME`，再按目标单据和操作名读取唯一 `IOYYGX`；仅当活动路径使用回退来源时检查 `IOPOPDLG`；
- 通过 `sys.columns`、运行时 SQL 和小样本确认来源结束日期/状态字段，不凭中文标签猜列名；
- 对“过期不参照”使用已确认的结束日期条件与动态 SQL Server 日期，并明确空结束日期和开始日期的处理；
- 预览旧/新命中数和排除数量，使用旧值作为 `UPDATE` 谓词，事务内只更新配置行并断言 `@@ROWCOUNT=1`，提供 rollback；
- 验证来源 SELECT/JOIN/别名/结果集形状和过期排除，未修改业务表、数量或状态；若关系、元数据、生命周期或保存行为也变化，则转完整动态单据契约；
- 不修改 C++、RC、菜单资源、安装包，并单独报告真实客户端参照窗口是否回归。

## Dynamic-Bill Upstream/Downstream Relations

Prompt shape: 用户报告多个存在直接业务来源的单据，“关联单据”上下游显示不完整，要求仅做数据库开发并完善 skill。

Pass criteria:

- 读取活动 `SearchRelation.cpp`，证明 `IOYYGX_BDMC` 当前单据读取 `SYLJ`、`IOYYGX_CZMC` 当前单据读取 `XYLJ`，并核对 `@SJDH/@FLH` 替换；
- 区分参照/过滤配置与上下游显示配置，不能以 `GLTJ`、`TABLE/FROMTABLE` 或单侧关系代替 reciprocal `SYLJ/XYLJ`；
- 为每个直接确认的来源标识分别建立关系行，不依赖 A->B->C 的传递遍历；同一方向多条 SQL 经过 `UNION ALL` 后必须列数、顺序、类型兼容；
- 验证 `SYLJ` 的七列结果集和 `XYLJ` 的六列结果集，每条值非 `NULL` 且是单个可执行 `SELECT`，无调试结果集、变量或临时表；
- 在正式库只读调查连接上不写入，产生带数据库/服务器门禁、旧值断言、影响行数断言、事务和对称 rollback 的 forward/verification/rollback 包；
- 不把 `IOYYGX_ID/IOYYGX_BH` 当作唯一键，更新、验证和回滚均用完整关系元组及旧 SQL 精确命中；通过人工正式发布时交付并遵守 `preflight -> forward -> verification`，任一步失败即停止，随后只读回读实际分配编号；
- 用真实样本分别验证每条直接链的双向结果，并把数据库验证和客户端关联窗口重开/双击验收分开报告；
- 将可复用规则写入 `references/patterns.md`，客户专有表名、单号和凭据只保留在项目 `docs/imes/` 或 `diagnostics/`。

## ER 字段闭合与中文映射门禁

Prompt shape: 用户报告 ER 驱动的保养/检定等主从单据少字段、字段中文名为空或显示物理字段名，要求修复数据库元数据并完善 skill。

Pass criteria:

- 先读取 ER 字段清单、物理 `sys.columns`、维护页 `PO` 元数据和独立查询页元数据，建立“物理列 -> 维护字段 -> 查询字段 -> 显示名/标签名/别名”矩阵；
- 对每个基础资料、主表 `PO=1`、从表 `PO=2` 和查询页做双向字段集合比较，明确列出缺失字段和多余字段；不能只比较总行数；
- 生成器遇到缺中文标签、空 `显示名/标签名`、物理字段名回退或查询别名重复时必须 fail-closed，不生成可部署 `forward.sql`；
- 关键字段使用显式中文映射契约，全量字段至少验证非空、非物理名回退、维护/查询字段闭合，表头/表体同义字段使用稳定显式别名；
- 验证通过 `v_tbcolumn` 回放维护字段、查询标题 SQL、派生表分页/计数 SQL 和关联 JOIN；数据库验证与真实客户端重开分别报告；
- 将通用规律记录到 `references/patterns.md`，不把客户名、服务器、单号或现场数据写入通用 skill。
