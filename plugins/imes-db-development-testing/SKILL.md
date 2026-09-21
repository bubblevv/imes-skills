---
name: imes-db-development-testing
description: Develop, test, or diagnose IMES SQL Server databases across customer environments, including 业务表设计、表结构迁移、索引与约束、存储过程、自定义报表、BDJB、PDA、报工、审核/撤审、回填、同步和生产报错. Use when the user asks to create or change database objects, validate database behavior, or investigate an exact IMES SQL entry point. This skill does not create MFC client forms or dialog resources.
---

# IMES数据库开发与测试

## Capability Routing

- When the active repository contains `docs/imes/README.md`, read it first as the human-readable project handbook index. For a broad iMES database task, also read `docs/imes/开发与排障手册.md`; keep project-specific facts in that repository rather than promoting them into this personal skill.
- For a new or changed business table, schema migration, index, constraint, view, function, trigger, or supporting procedure, read `references/schema-development.md` before designing or editing SQL.
- For a new metadata-backed iMES form, read `references/document-form-contract.md` as well. It distinguishes `IOJCBDZD_BTYPE=1` single-table lookups, `BTYPE=2` category-tree/detail-dataset maintenance, and true `IOBDZD` header/detail bills. It defines the database-only contract across the business tables, `IOBDZD`, `IOJCBDZD`, `SYS_TbColumn`/`v_tbcolumn`, `IOYYGX`, `IOPOPDLG`, `BDJB`, `SYSWSPACE`, and required `sysmenu` metadata for the standard dynamic-bill buttons.
- For an existing dynamic-bill reference/filter-only request, read `references/reference-fast-path.md` first. Use its narrow `IOYYGX`/source-date/preview/update/verification path; do not repeat the full dynamic-bill creation contract unless the route, metadata, lifecycle, or save behavior also changes.
- For an existing `IOJCBDZD_BTYPE=2/UForm2` form incident, read the mandatory BTYPE=2 first-pass below and `references/document-form-contract.md` before broad metadata comparison or DDL. The left tree has source-level hard-coded column names; a non-empty route and non-empty `v_tbcolumn` rows do not prove that the physical master table is runnable.
- For a live database investigation or existing business-logic change, follow the evidence-first debugging workflow below.
- Before designing or repairing any table, form, layout, or metadata row, read `references/client-source-contract.md`. It records the compiled-in table names, column names, aliases, control codes, suffix anchors and SQL shapes of the legacy client. The hard-rule list in `## 客户端源码硬规则` below is a subset and is not optional.
- A database table is not an iMES client form. This skill may define the database contract needed by a form. Database-resident `SYSWSPACE` rows and role-column grants may be included when the user explicitly scopes database metadata; MFC dialogs/resources, client menu or command mappings, and C++ form classes still require the client project's workflow and are never implied by the database change.

## 客户端源码硬规则（不可协商）

这个老客户端把大量契约编译进了 EXE。数据库可以完全合法、约束齐全、CRUD 全通过，客户端仍然报错、空白或打不开，而且错误信息往往没有堆栈。因此下面每条都是**门禁**：缺少由当前版本源码、同库工作单据或目标库只读证据支持的结论时，**停止并报告**，不得猜测、不得用“先部署再试”代替验证。完整证据、确切 SQL 形状、控件分派表和症状对照见 `references/client-source-contract.md`。

1. **键不能混用。** `GLZD` 关联路由查 `IOJCBDZD.IOJCBDZD_MC`；字段 `帮助` 值查 `IOJCBDZD.IOJCBDZD_BZBH`；单据路由查 `IOBDZD.IOBDZD_MC`（审批路径查 `IOBDZD_BH`）。三条路由各自独立，键写错不报错、只返回空串。
2. **`显示名` 和 `字段名` 不得为空。** `GetDataField` 命中空值时会弹窗并返回空字段串，最终生成 `SELECT  FROM …`。`标识` 必须保持 `NULL`，非空（含字符串 `'0'`）会输出 `sum(case FF_BS …)`，要求业务表存在物理列 `FF_BS`。
3. **`GLZD` 非空行的 `字段名`、`IOJCBDZD_Table`、`IOJCBDZD_VKEY`、`LMark`、`RMark` 必须全部有值并生成可执行 JOIN。** 空别名写 `''`，不写 `NULL`。
4. **可见名五处一致且唯一：** `IOJCBDZD_MC`、`IOBDZD_MC`、`SYS_TbColumn.表名`、`SYSWSPACE_MC`、`sysmenu_bdmc`。
5. **`PO=1` 每行的 `控件`、`类型`、`RID`、`显示`、`必填`、`只读`、坐标必须非空。** 这些列被直接转字符串、`bool`、`(int)(double)`；`NULL` 会抛异常并被吞掉，只显示“控件初始化时出错!”，单据打不开。
6. **控件码只能来自当前版本源码 + 同库工作单据，不能按物理列类型推断。** 表头 `控件='S'` 是静态文本、`'C'` 是复选框；`类型='D'` 是**只读日期格式框（右键日历）**、`'DT'` 才是日期时间选择器、`'EM'` 才是多行框。
7. **表头锚点后缀 `_ID/_SJDH/_YWRQ/_PJLX/_SHBZ/_ZDR/_SHR/_ZY` 各恰好一条，且不得有其它字段名子串冲突**（源码用 `Find` 子串匹配，靠后的同后缀行会覆盖前者）。
8. **明细组 `顺序=1` 那条字段的 `字段名` 前缀就是明细物理表名。** 明细 `顺序` 同时是 Grid 列下标，必须是 `1..n` 连续无重复。
9. **明细字段集必须投影出 `单号` 和 `分录号`，且 `分录号` 能 `cast(... as int)`。** 翻前单 SQL 写死这两个别名和排序。
10. **动态单据必须有独立的 `<表单名>查询` 字段集**（`GetDataField(<表单名>查询)` 配 `GetCrossTable(<表单名>)`），并含可见必填的 `单号`、`日期` 锚点。
11. **`CBill` 固定字段卡在物理列和元数据里都必须齐全**，其中 `<表头>_PJLX` 是硬运行字段：所有表头读写都带 `and <表头>_PJLX='<IOBDZD_BH>'`。
12. **`IOBDZD_BH` 必须能唯一反查 `IOBDZD_HTABLE`/`IOBDZD_MC`；`IOBDZD_FORMAT`、`IOBDZD_MARK`、`HTABLE`/`FTable`/`Vkey` 必须齐全。** 单号由 `PRD_GETDANHAO` 按可见表单名生成，过程缺失或 `FORMAT` 为空只会得到空单号，不报错。
13. **`BDJB_PJLX` 用可见表单名，不是 `IOBDZD_BH`。** 审核状态 `<表头>_SHBZ` 的取值含义必须来自同版本字典，源码多处直接比较 `="1"`。
14. **`BTYPE=1/UForm1` 的 `顺序` 是真实 0 基列下标**（`0..n-1`）；`BTYPE=1` 搜索按钮写死 `charindex(…,码表编号)`，字段集必须能投影出别名 `码表编号`，否则搜索恒定报“列名 '码表编号' 无效”——这是客户端范围问题，**不得**用新增物理列掩盖。
15. **目标库排序规则必须是大小写不敏感。** 同一源码里 `v_tbcolumn`、`V_TbColumn`、`V_TBCOLUMN` 并存。
16. **空来源必须回放验证。** 部署前执行 `SELECT <GetDataField> FROM <GetCrossTable> WHERE 1=2`，以及维护页、查询页、翻前单三种包装形状；`SELECT  FROM …` 与 `FROM )` 分别指向字段集为空和跨表来源为空，两者根因不同。
17. **`BTYPE=1`、`BTYPE=2`、`IOBDZD` 三套规则不能互换**（`顺序` 基址、查询字段集、审核布局、按钮集各不相同）。

## GLZD/LMark/RMark 关联显示契约

在分析或修改任何使用 `v_tbcolumn` 的表（包括基础资料、表头/明细单据、查询页和其他业务单据）时，先把“存储字段”和“显示字段”分开建模。系统通常只在业务表保存编号；名称、规格、描述、状态等管理字段由关联表投影显示。字段名、标签名和帮助文字不是可自由发挥的同义词，必须沿用已确认的元数据契约。

- `GLZD` 是关联/连接契约，不是界面文案。`GLZD` 非空的 `v_tbcolumn` 行必须闭合到 `IOJCBDZD_TABLE`、`IOJCBDZD_VKEY` 与 `LMark/RMark`；该行以 `切换=1` 走显示值转换时还必须闭合 `IOJCBDZD_BYZD`。
- 编号输入行通常是 `GLZD=<关联路由>`、`切换=1`：物理 `字段名` 保存业务编号，`GetDataField` 投影 `IOJCBDZD_BYZD` 作为显示值。不要把编号字段改名为“分析物料”等新标签来替代已有字段契约。
- 关联显示行通常是 `GLZD=''`、`RMark=<右侧关联别名>`：`字段名` 必须是关联表真实的显示列，投影为 `RMark.字段名`。显示行常为只读，但是否只读仍以同版本源码和目标元数据为准。
- `LMark` 是关联表的左侧别名，`RMark` 是当前业务表/右侧来源的别名。源码生成的形状是 `LEFT JOIN <IOJCBDZD_TABLE> AS <LMark> ON <RMark>.<字段名>=<LMark>.<IOJCBDZD_VKEY>`；`LMark` 为空时使用无别名关联表，并按 `RMark`（若有）给当前字段加前缀。别名为空时写空字符串，不写 `NULL`。
- `GetCrossTable` 对当前源码路径查询到的 `GLZD` 非空行（现版本条件含 `PO<=2`）建立连接；其他 `PO` 或其他运行入口必须单独确认是否参与交叉表。`切换=1` 还决定 `GetDataField` 是否输出 `IOJCBDZD_BYZD`。因此不能只检查帮助能否打开，必须同时回放 JOIN 和 SELECT 投影。
- 物理表中即使存在看似相同的名称/规格列，也不能据此删除关联显示行、改 `GLZD` 或改 `LMark/RMark`。先核对 `sys.columns`、`v_tbcolumn`、`IOJCBDZD` 和客户端生成 SQL；界面已采用关联显示契约时必须保持该契约。

修改一个关联字段前，必须同时核对并保持 `字段名`、`显示名`、`标签名`、`帮助`、`GLZD`、`切换`、`LMark`、`RMark`、`RID` 及帮助/传参占位符。任何一项未由源码、同版本工作表单或目标库只读证据确认，都不得写库；详情和症状-根因-验证矩阵见 `references/patterns.md` 的 **GLZD/LMark/RMark 关联显示契约**。

## Fast Path: BTYPE=1 单表基础资料

当请求是“一张表一个基础资料表单”，且没有表头/明细、审核/撤审、上下游、库存回写或分类树时，先读 `references/basic-form-fast-path.md`，再使用 `scripts/scaffold_basic_form.py`。模型只需先形成一张单表契约卡（目标库/实例、物理表、可见名、路由、工作区、字段、授权），不要重复做全库扫描或重复询问已证实字段。

脚手架读取经过确认的 JSON 契约，一次生成 `preflight/forward/verification/crud/rollback` 全套脚本；它只生成文件，不连接、不写库。`schema-draft.sql` 仅供审阅且必须是注释式、不可执行的 DDL 草图；部署只允许执行 `forward.sql`，不能把目录内所有 `.sql` 批量喂给 `sqlcmd`。必须先执行 preflight，再在明确授权的测试库执行 forward，随后执行 verification 和隔离 CRUD。任何命名空间、父节点、元数据列、字段前缀或表单类型冲突都 fail-closed。`BTYPE=1/UForm1` 的每个 `(表名,PO)` 元数据组必须按客户端实际列下标从 `0..n-1` 连续编号，隐藏 identity 字段通常占 `顺序=0`；不要套用动态单据的 `1..n` 规则。

## Fast Path: 复杂表单四阶段

当请求涉及点检模板、点检记录单、审核单、表头/表体单据、独立单据查询页、`IOBDZD`、审核/撤审 `BDJB` 或表头表体联动时，先读 `references/complex-form-fast-path.md`，再使用 `scripts/scaffold_complex_form.py`。其中“主从动态单据固定九步回归门禁”是强制顺序：目标/分类 → 固定字段卡 → 业务数量归属 → BOM 版本联动 → 查询字段/别名 → 客户端派生 SQL 回放 → PJLX 实测宽度与表头布局 → BDJB/工作区/sysmenu/角色 → 事务、回滚与真实 Release 冒烟。不得只因建表、元数据插入或普通 SQL 可执行就跳到部署或宣布完成。

固定为四阶段：字段契约确认 → 前期只读准备 → 中期事务部署 → 后期验证与隔离 CRUD。可从 ER SVG 快速生成审阅阻断包；只有物理字段、主外键、IOBDZD 路由、维护页/查询页 `SYS_TbColumn`、审核布局证据、BDJB 规则和 SYSWSPACE 契约闭合后，才允许生成可执行 `forward.sql`。新生成元数据中，物理日期字段（`date`、`datetime`、`datetime2`）的 `类型` 固定为 `D`，其他字段固定为 `S`；普通字段的 `控件` 固定为 `E`，`PJLX/凭证类型` 字段（字段名后缀 `*_PJLX`）固定为 `S`。`SYS_TbColumn.标识` 保持 `NULL`，不插入 `nID`；动态角色权限和 `admin` 后权限默认全部授权。审核的左坐标、宽度、高度和参考自然间距必须来自同版本有效单据；`SHBZ` 是表头下限锚点但不是必须独占的列，按横向装箱规则能与当前行字段同排时应同行，只有完整占用区越过右边界才换行；换行时才用最后一个较早行的非固定字段底边加自然间距推导审核顶坐标。审核底边仍决定表头下限，禁止机械复制参考坐标造成大空洞。生成元数据前必须形成逐字段闭合矩阵：物理列 → 维护页 `(表名,PO,字段名)` → 独立查询页 `(查询名,PO,字段名)` → `显示名/标签名`。每个必需物理字段必须在对应字段集恰好出现一次；每个元数据字段必须回到真实物理列或已证实的关联投影；空文案、物理字段名回退或缺失 ER 中文标签均为硬阻断。复杂表单不走 `BTYPE=1/UForm1` 快速通道；本技能仍不创建 MFC/C++/RC 资源。

## Existing Single-Table (`BTYPE=1`) Incident: Mandatory First Pass

When an existing `BTYPE=1/UForm1` single-table form reports an open failure, blank tab, generated SQL error, or incomplete setup, complete this short read-only checklist in order before comparing other forms, scanning broad schema, or inspecting client code. Report every failed required row from these five narrow checks. If any item fails, do not enter source-code or feature-specific analysis; only expand the earliest failed item far enough to prove its immediate cause. Enter later analysis only after all five items pass.

1. Verify target identity, then read the one visible-name `IOJCBDZD` route: it is unique, `BTYPE=1`, and its table/key/display/help mappings are non-blank where the active route consumes them.
2. Verify the physical table, primary/business key, and the route's table/key/display mappings. Every runtime-mapped field must resolve to a physical field; confirm the active `UForm1` prefix/key convention rather than inferring it from a Chinese label.
3. Read maintenance `v_tbcolumn` only for that visible form: it is one runtime field set, every metadata field resolves to the physical table or a proven lookup projection, ordinary `标识` is `NULL`/blank, and its `顺序` is exactly `0..n-1` with the hidden identity/key row at `0`. Do not apply the dynamic-bill `1..n` rule.
4. Materialize the active `GetDataField(<form>, true)` and `GetCrossTable(<form>)` projection, then execute the client-shaped initial-load SQL. Separately replay the source-proven search predicate/path; a passing initial load does not prove a fixed search field exists.
5. Read only this form's `SYSWSPACE` parent, leaf, and configured operation rows. Verify the leaf and each operation have explicit role visibility. Missing `IOBDZD`, `BDJB`, `<form>查询`, or dynamic-bill `sysmenu` rows is not a single-table defect unless a proven consumer requires them.

Only after all five items pass, inspect client source, optional help/relation behavior, or a same-version reference form. If the source-proven search path is the only failed check and has no database configuration counterpart, report it as client scope instead of inventing a business column.

## Existing `BTYPE=2/UForm2` Incident: Mandatory First Pass

When an existing category-tree form opens with blank field names, missing tabs/surface, an empty right grid, or a generic open error, complete this read-only checklist before comparing broad metadata, proposing compatibility columns, or changing the route. A non-empty `IOJCBDZD` row and non-empty `v_tbcolumn` rows are not sufficient: `UForm2` directly constructs tree SQL and reads fixed physical column names.

1. Verify target identity, then read the unique `IOJCBDZD` route by visible name. Confirm `BTYPE=2`, right-side `TABLE/MC`, tree `LBTABLE/LBNAME`, and the detail filter contract.
2. Read the active `UForm2` source path and record the exact master/detail hard-field contract. In this client family the tree master must expose `<MASTER>_BH`, `<MASTER>_MC`, and `<MASTER>_PBH`; the right-side table must expose `<DETAIL>_ID`, `<DETAIL>_BH`, and `<DETAIL>_LBBH`. Confirm each with `sys.columns`/`COL_LENGTH`, not with labels or route aliases.
3. Treat `IOJCBDZD_VKEY/BYZD` as lookup and projection metadata, not as permission to rename the tree columns used by hard-coded `UForm2` code. If the route says one naming convention but the table exposes another, stop and report a runtime naming-contract failure; do not mask it by adding unrelated metadata rows.
4. Replay both client-shaped SQL paths: the tree query `SELECT * FROM <LBTABLE> WHERE ISNULL(<LBTABLE>_PBH,'')=<parent>` and the selected-detail query filtered by `<DETAIL>_LBBH=<MASTER>_BH`. Fail on invalid columns, empty `GetDataField`, empty `GetCrossTable`, or an invalid filter source.
5. Read the two metadata sets separately: `LBNAME` fields for the tree and `MC` fields for the right dataset. Verify tree/detail fields resolve to their own physical tables, `顺序` follows the active `UForm2` path, and workspace/role rows are not used to hide a physical contract failure.

If any item fails, the result is `review-blocked` until the first failed runtime predicate is repaired or explicitly accepted as client-scope work. Do not continue to layout, help, workspace, or CRUD analysis as though the form were structurally valid.

## Existing Dynamic-Bill (`IOBDZD`) Incident: Mandatory First Pass

When an existing `IOBDZD` form reports an open failure, generated SQL error, absent buttons, missing page, or incomplete setup, complete this short read-only checklist in order before comparing unrelated forms, scanning broad schema, or investigating optional features. Report every failed required row from these six narrow checks. If any item fails, do not enter source-code or feature-specific analysis; only expand the earliest failed item far enough to prove its immediate cause. Enter later analysis only after all six items pass.

1. Verify target identity, then read the one `IOBDZD` route by visible form name: unique `MC/BH/MARK` (with `MARK` exactly two ASCII letters and globally unique), tables, header/detail keys, tabs, and non-blank `FORMAT`.
2. Read maintenance `v_tbcolumn` only for that form: each `PO` has fields, `顺序` is continuous for the route, the full `CBill` fixed-field card (header HID/date/PJLX/document number/print/audit/creator/auditor/summary and each detail FID/document number/line number) has physical and metadata rows, required header controls/RIDs exist, and every metadata field resolves to a physical field or a proven lookup projection.
3. Read `<form name>查询` as a separate required dataset. Confirm one query group, unique aliases, exactly one visible required header document-number field (`<HEADER>_SJDH`, alias `单号`), and exactly one visible required header-date field (`<HEADER>_YWRQ`, alias `日期`); both are stable default-sort anchors and cannot be replaced by detail fields or removed during deduplication. Then execute the exact client-shaped title SQL: `SELECT <GetDataField(查询)> FROM <GetCrossTable(原表单)> WHERE 1=2`. A blank field list, blank `FROM`, duplicate alias, missing document-number/date anchor, dangling lookup, or SQL parse error is the first root cause.
4. Read active `BDJB` for the visible form name. Zero active rows is an initialization failure; do not inspect disabled scripts or referenced procedures until this check passes.
5. Read only this form's `SYSWSPACE` leaf and operation rows. Check the main leaf is role-visible and each configured operation name has an explicit role value. Treat missing role grants as a permission defect even if `admin` can open it.
6. Read `sysmenu` for this form. Every database-only dynamic header/detail bill requires the seven standard rows: `显示关联单据`、`保存列宽`、`列配置`、`从EXCEL导入`、`说明`、`附件`、`复制分录`. Zero rows, or a missing named standard row, is a confirmed configuration defect; use the Sales Order values only when preparing an authorized repair.

Only after all six items pass, inspect feature-specific objects: `IOYYGX`/`IOPOPDLG` for reference or relation symptoms, `report` for printing, disabled `BDJB` dependencies, or legacy forms with a different visible name. Do not report an optional object as missing unless the affected workflow proves it is consumed. In this client, page metadata `PO=2/3/4` maps to tabs 1/2/3, so `PO=3` is the second tab and does not by itself require `IOBDZD_TAB3`.

## Fast Path: Existing Dynamic-Bill Reference

When an existing `IOBDZD` bill already has a working `IOYYGX` reference and the user only asks to change its filter, use `references/reference-fast-path.md`:

1. Verify identity and read the exact target `IOYYGX` row by bill and operation name.
2. Confirm only the source columns/aliases used by `IOYYGX_GLTJ`; inspect `IOPOPDLG` only when the active path uses its fallback.
3. Resolve date/status meaning from `sys.columns`, runtime SQL, and a small data sample. For “exclude expired,” add the confirmed end-date predicate with `CONVERT(date,GETDATE())`; do not add a start-date rule unless the user asks for the full current interval.
4. Preview old/new match counts, update only the exact old configuration value inside a guarded transaction, and assert `@@ROWCOUNT=1`.
5. Verify the client-shaped source query and that expired rows are excluded. Report client reopen separately.

If the relation is missing or non-unique, the source route is unresolved, or the request changes metadata, saving, quantities, audit, or upstream/downstream behavior, stop this fast path and use the full dynamic-bill contract.

### Existing Dynamic-Bill Upstream/Downstream Relation

When the request is about the dynamic-bill "关联单据" window rather than reference filtering, read the active `SearchRelation.cpp` path and use the full relation contract:

1. Treat `IOYYGX_BDMC` as the current/downstream bill and `IOYYGX_CZMC` as the source/upstream bill. The current bill consumes enabled `IOYYGX_SYLJ`; the source bill consumes enabled `IOYYGX_XYLJ`.
2. An enabled row with a `NULL` relation SQL is not a configured direction: `CSearchRelation::LoadData` skips that value before it builds `UNION ALL`. Assert every required `SYLJ` and `XYLJ` is non-null as well as executable.
3. Replace `@SJDH` and `@FLH` with a confirmed document value, then execute each relation SQL independently before reasoning about `UNION ALL`. `SYLJ` queries must return the seven-column window shape (document number, date, document type, creator, total, achieved, audit); `XYLJ` queries must return the six-column shape (document number, date, document type, creator, achieved, audit).
4. If the current document stores multiple confirmed source identifiers, create a separate reciprocal `IOYYGX` row for each direct source. Do not rely on transitive traversal from source A through source B to source C; the client only unions the rows for the current bill/source name pair.
5. Require one executable `SELECT` per relation value, no debug result sets, declarations, temp tables, or incompatible aliases. `IOYYGX_ID` and `IOYYGX_BH` may not be unique, so target an existing row with the full relation tuple (`ID/BH`, `BDMC`, `CZMC`, direction flags, enabled state, and old SQL). Allocate new non-identity metadata IDs under a transaction lock and provide a guarded rollback.
6. When the approved production path is manual, hand off `preflight -> forward -> verification` in that order. Stop on any failure, never retry a guarded forward blindly, then use the read-only investigation connection to record actual allocated IDs and re-run the runtime-shaped checks.
7. Verify both directions with a representative document and separately report database verification versus a real client reopen/double-click acceptance.

Do not use the existing reference/filter fast path when the request adds or repairs `SYLJ/XYLJ`, changes document lineage, or changes the relation result-set contract.

## Core Posture

New metadata must render `类型='D'` for physical `date`/`datetime`/`datetime2` fields and `类型='S'` for all other fields. Ordinary fields must render `控件='E'`, while a voucher-type field whose name ends in `'_PJLX'` must render `控件='S'`; case-insensitive contract input is normalized before SQL generation. Do not infer any other type or control value from bit-ness, numeric precision, label text, or layout.

For a module-wide physical naming migration, treat the user's named columns as examples until the target-module inventory proves the full set. Build an explicit old-to-new map from `sys.columns`, including type/length/nullability and table ownership; migrate every confirmed physical column and update all dependent metadata strings (`SYS_TbColumn.字段名/GLZD`, `IOJCBDZD` key/display mappings, and proven route/help values) together. Search `sys.sql_modules`, foreign-key column bindings, indexes/constraints, form registration/layout/verification artifacts, and ER definitions before writing. Fail closed on any target-name collision or unreviewed old-name reference. The forward script must use database/instance gates, a clean transactional `sp_rename` sequence, exact row-count assertions per dependency category, and a symmetric rollback; verification must prove the old set is absent, the new set is complete, field properties and foreign-key relationships are unchanged, and runtime lookup/JOIN SQL still parses. Historical evidence and rollback maps may retain old names only when explicitly labeled as migration history.

Treat every customer database as an independent environment. When production/test classification is unknown, apply production-grade safety controls without claiming the target is a production database. Discover the target from current evidence, find the root cause before editing, preserve result columns and field names, make the smallest compatible SQL change, and verify with rollback-safe execution.

Treat user-provided entry points as primary evidence. If the user gives an exact table, query, document type, procedure, script category, or document number, start there after the database identity check. Do not replace a narrow entry point with broad schema discovery, global module searches, or an unrelated subsystem scan.

Keep one evidence-supported hypothesis active at a time. Before following a new direction, state what observed fact supports it and what query can falsify it. Do not present an inferred field meaning, route role, status mapping, or source chain as fact.

Ask one focused question instead of guessing when multiple plausible interpretations would change the investigation or fix. Examples include ambiguous environment, UI label-to-column mapping, whether a marker means final process or key process, and whether quantities should overwrite or accumulate. If a read-only query can resolve the ambiguity directly, query first; otherwise stop and ask.

Never infer a database or connection from this skill. Resolve the target in this order:

1. Database, customer account, or environment explicitly named by the user.
2. Current SQL `USE` statement or qualified object name.
3. Repository rules and project configuration.
4. Existing configured database-tool environments.

File paths and diagnostic folders are supporting evidence only. If evidence conflicts or multiple environments match, stop before connecting or changing data and ask which target is intended.

## Load References

Read `references/workflow.md` before any live database investigation or database edit.

Read `references/project-knowledge-layer.md` before connecting when the active repository has `AGENTS.md`, fixed customer routing, or project-local IMES knowledge. Project instructions control environment routing and permissions; this personal skill supplies the reusable workflow.

When the active repository provides `docs/imes/README.md` and `docs/imes/开发与排障手册.md`, use them as the human-readable project entry point and current project workflow. Do not copy their customer-specific facts into this skill; use the repository's `AGENTS.md`, handbook, and diagnostics as the project knowledge layer.

Read `references/reference-fast-path.md` first for an existing dynamic-bill reference/filter-only request; it is the default route for `IOYYGX_GLTJ` changes that do not alter the bill contract.

Read `references/client-source-contract.md` before any work that creates, repairs, or verifies a business table, form route, `SYS_TbColumn` field set, header control, detail grid, or query dataset. It is the source-code evidence layer behind the hard rules above: the exact SQL the client builds, the three independent lookup keys, the header control dispatch table, the suffix anchors, the detail-page and 翻前单 shapes, and a symptom→root-cause table for errors that surface without any database error. Read it together with the route-specific reference, not instead of it.

Read `references/patterns.md` when the issue involves `GLZD/LMark/RMark` 关联显示、字段帮助/传参、BDJB, PDA save/get procedures, 报工、领料、批号、同步、自定义报表、报表设计器包装、transaction handling, or result-set errors. Object and table names in that reference are examples from common IMES deployments; confirm them against the target schema.

Read `references/bdjb-audit-fast-path.md` when the request mentions BDJB, 审核、撤审、报工、回填、完成标志、状态未更新, or provides a `BDJB_PJLX`/BDJB query. Follow its mandatory first round before broader discovery.

Read `references/bdjb-procedure-consolidation.md` when several BDJB scripts should be consolidated into one stored procedure, or when a cancel-audit precheck must block a confirmed downstream document. It records the source entry points, placeholder replacement contract, execution ordering, guarded one-file integration, and verification checklist.

Read `references/audit-state-matrix.md` whenever audit or cancel-audit writes quantities, completion flags, generation states, or work-order states. Complete the applicable transitions before proposing a formula change or historical repair.

Read `references/evaluation-cases.md` only when modifying or validating this skill.

Read `references/basic-form-fast-path.md` for a BTYPE=1/UForm1 single-table form; do not load the dynamic-bill contract unless the request has header/detail or lifecycle behavior.

When the request says “建表单” but limits the work to the database layer, treat “form complete” as a verified metadata contract, not merely a physical table plus one permission row. The dynamic bill reference must be closed before any metadata write; client resources, command IDs, and MFC form classes remain outside this skill.

Before interpreting a requested number of “tables/forms,” classify every business object from the ER model, lifecycle, and active client route as a single-table lookup, `BTYPE=2` category-tree/detail dataset, or `IOBDZD` business bill. Business-object count is not physical-table count. A request for one document number with header and line rows, `PO=1/2/3`, or an audit/cancel-audit lifecycle is an `IOBDZD` bill, never a `BTYPE=2` form. Never flatten confirmed header-line cardinality merely to meet a stated count; report the required physical tables and build the smallest complete business unit.

## Database-Only Form Creation Workflow

Every new `IOBDZD` header/detail bill must include the seven standard `sysmenu` actions from Sales Order. Copy their exact `topfloor/submenu/xh/icon/pmenu/trimenu/uid` values; where the Sales Order stores `pmenu` or `uid` as a literal single space, preserve that space instead of converting it to an empty string. Existing bills missing these rows require a guarded, exact-row repair before claiming the form is complete.

When the user says “建表单” and limits the work to the database layer, execute this workflow in order. The output is a database contract that the existing client can resolve; it is not an MFC dialog, resource, menu command, or package change.

### Gate 0: classify before writing

Create a short classification record before DDL:

- `BTYPE=1`: one physical table is one complete basic-data row; use `IOJCBDZD` + one visible `SYS_TbColumn.表名`.
- `BTYPE=2`: a real category/tree master (`LBTABLE/LBNAME`) filters an independent right-side dataset (`TABLE/MC`); use the two metadata names required by `UForm2`.
- `IOBDZD`: one document number owns a header and one or more detail pages, with `PO=1/2/3...`, unified save/delete, audit/cancel-audit, references, or upstream/downstream relations. Use one visible bill name and one `IOBDZD` route.

`BTYPE=1/UForm1` 的 `顺序` 是 FlexGrid 和字段访问使用的真实 0 基列下标：每个单表组必须是 `0,1,...,n-1`，首个隐藏主键字段也必须占用 `0`。`IOBDZD/PageRows` 的动态单据组仍按其独立运行时契约使用 `1..n`；两类规则不能互换。

If the request describes a shared-document-number header with `1:N` detail rows, or the ER model proves that structure, reject a single-table or `BTYPE=2` design even if the requested count is “two tables”. Record physical-table count separately from form count.

### Gate 1: collect source and schema evidence

Read `references/workflow.md`, `references/schema-development.md`, and (for metadata-backed forms) `references/document-form-contract.md`. Inspect the active source path (`AutoOpen`, `UForm1/UForm2`, `CBill::InitForm`, `CBillForm`, `PageRowsTab`, search-page initialization, `GetCrossTable`, relation loading, and workspace authorization) and one working form of the same route/version. In the target database, verify `DB_NAME()`, `@@SERVERNAME`, compatibility level, metadata view definitions, actual columns, and existing keys/enums before choosing names or values. Keep confirmed facts separate from proposed design.

Before writing metadata, inspect `sys.columns` for every metadata object named by the contract. Treat `SYS_TbColumn` as the base table's actual columns and `v_tbcolumn` as a derived runtime projection: fields with names such as `IOJCBDZD_TABLE`, `IOJCBDZD_VKEY`, `IOJCBDZD_BYZD`, or `IOJCBDZD_FILTER` belong to `IOJCBDZD` (or the confirmed view), not automatically to `SYS_TbColumn`. Never design an `INSERT` or `UPDATE` from a view-only column or from a remembered schema; fail closed when the inspected base columns do not match the proposed statement.

For a new `BTYPE=2/UForm2` object, DDL has an additional runtime preflight: the proposed tree master must expose `<MASTER>_BH`, `<MASTER>_MC`, and `<MASTER>_PBH`; the right-side detail table must expose `<DETAIL>_ID`, `<DETAIL>_BH`, and `<DETAIL>_LBBH`. `*_CODE`/`*_NAME`, route aliases, labels, and help metadata are not compatible substitutes for these source-level names. A mismatch among the source contract, route, physical columns, metadata, or generated SQL is a naming-contract conflict and must stop `forward.sql` before any table or metadata is created.

### Gate 2: write the form contract

For each business object record the visible name, stable code, route (`BTYPE` or `IOBDZD`), physical tables, primary/business keys, header-detail foreign key, `PO`/tab mapping, lookup display/key mapping, lifecycle operations, relation consumers, workspace parent/leaf, role columns, and required query fields. Mark each dependency as `required`, `optional (only with a proven consumer)`, or `out of database scope`. An unresolved key, enum, control code, relation placeholder, or lifecycle meaning stops metadata writes.

### Gate 3: build physical schema

Using the nearest confirmed local convention, produce `forward.sql`, `rollback.sql`, `verification.sql`, and (for writable test databases) `crud-test.sql`. Create tables, real columns, primary/foreign keys, unique constraints, defaults, nullability, precision, and indexes first. For a bill, include the runtime hard fields confirmed from source (normally header ID/document number/type/date/creator/auditor/summary/audit flag and detail ID/document number/line number); do not register virtual fields that do not exist physically. Guard every script with the target identity and expected preconditions.

Before `CREATE TABLE` for `BTYPE=2`, run a column-level conflict preflight against the source-confirmed hard-field map. Assert that the planned master/detail columns use the exact runtime names, that existing objects do not expose an incompatible same-purpose naming set, and that the route's `LBTABLE/LBNAME`, `TABLE/MC`, `VKEY/BYZD`, metadata fields, keys, and generated tree/detail SQL all agree. If the only proposed fix is to add `*_BH`/`*_MC`/`*_PBH` or `*_ID`/`*_LBBH` after an incompatible table was already created, classify it as a compatibility change requiring explicit review; never silently create the conflicting table or add guessed aliases.

### 3.1 `CBill` fixed-field gate

For a `CBill`-style `IOBDZD` bill, fail closed before generating or executing `forward.sql` unless the active source and a same-version working bill prove every required semantic field is present in both the physical schema and its maintenance metadata. The standard field card is:

| Page | Semantic field | Expected physical convention |
|---|---|---|
| Header `PO=1` | HID | `<HEADER>_ID` |
| Header `PO=1` | date | `<HEADER>_YWRQ` |
| Header `PO=1` | voucher type | `<HEADER>_PJLX` |
| Header `PO=1` | document number | `<HEADER>_SJDH` |
| Header `PO=1` | print count | `<HEADER>_PRINT` |
| Header `PO=1` | audit state | `<HEADER>_SHBZ` |
| Header `PO=1` | creator | `<HEADER>_ZDR` |
| Header `PO=1` | auditor | `<HEADER>_SHR` |
| Header `PO=1` | summary | `<HEADER>_ZY` |
| Detail `PO>1` | FID | `<DETAIL>_ID` |
| Detail `PO>1` | document number | `<DETAIL>_SJDH` |
| Detail `PO>1` | line number | `<DETAIL>_FLH` |

`PJLX` is a hard runtime field, not optional display metadata: its physical column must be required, contain the route's `IOBDZD_BH` value, and its `PO=1` row must be required with `切换=1` and `GLZD=IOBDZD_BH`; its maintenance and query metadata must use `类型='S'` and `控件='S'`. `SHBZ` must use the active version's verified audit-state mapping; in the standard `CBill` route this is `切换=1` and `GLZD=LSDJZT_BH`, with `类型='S'` and `控件='E'`. Do not infer a control from SQL type, label, or layout. `ZDR`/`SHR`/`ZY` remain fixed layout anchors.

The `IOBDZD_FORMAT` column is the bill-number format consumed by `PRD_GETDANHAO`; it is a required route value, never `NULL`, empty, or whitespace. If a new contract does not provide it, normalize it to the literal `YYMM####`; preserve an explicitly confirmed non-empty format. The active procedure reads the route by visible `IOBDZD_MC`, prefixes `IOBDZD_MARK`, and maintains `IOBDZD_BascData`, `IOBDZD_CurMonth`, and `IOBDZD_ModifyDate`. For a new `YYMM####` route, initialize `IOBDZD_BascData=0`, `IOBDZD_CurMonth=CONVERT(varchar(7),GETDATE(),111)`, and `IOBDZD_ModifyDate=CONVERT(date,GETDATE())`; leaving the month/date NULL makes the procedure skip its serial branch or return an unusable number. `IOBDZD_Type` and `IOBDZD_IoFlag` must also be explicitly set from the confirmed bill family (the EAM contract uses `EAM` and `0`). `IOBDZD_BH` is the voucher-type/data-permission value written to `<HEADER>_PJLX`, not the numbering lookup key, and `IOBDZD_BILLNO` is not used by the current `GenDanhao` entry point. Confirm supported format branches from the procedure definition (`YYMM`, `YYYYMM`, `YYMMDD`, or `#` serial mode) before accepting a custom value. A repair must preview the exact old format and update only the intended empty rows with an affected-row assertion; do not reset numbering state or overwrite existing formats.

`IOBDZD_BH` and `IOBDZD_MARK` are allocated by reconnaissance, never invented form by form. Before choosing either value, run a read-only inventory of the target's existing `IOBDZD` rows, group them by business class, and derive both values from that inventory.

- `IOBDZD_BH` is the stable class code. Forms of the same business class stay grouped together and are assigned downward as class prefix plus serial number, taking the smallest unused serial in that class. Preserve a confirmed existing class prefix; do not invent a new prefix for a form that belongs to an established class, renumber unrelated routes, or allocate an isolated code from the new form alone. Because the prefix-plus-serial form has no fixed width, size dependent columns from the current longest route value rather than assuming a six-character code.
- `IOBDZD_MARK` is the document-number prefix and must be exactly two ASCII English letters, globally unique across the entire `IOBDZD` table. Reject `NULL`, empty or whitespace-only values, digits, Chinese characters, three or more letters, mixed non-ASCII, and any duplicate of an existing mark. Choose the two letters as the pinyin-initial mnemonic of the form's distinguishing name whenever one exists (`点检模板` -> `MB`, `维修工单` -> `WX`, `资产入库单` -> `RK`); when no readable mnemonic is available, any unused two-letter combination is acceptable. Uniqueness is the hard constraint and mnemonic quality is only a preference, so never reuse a taken mark to keep a nicer abbreviation. A scaffold or generator must fail closed when the mark is missing or malformed instead of substituting a default such as `1`.

Both values are fixed route identity. A repair must not change an existing confirmed `BH` or `MARK` to accommodate a new form, and the preflight must assert the chosen `MARK` is two ASCII letters and unused, and that the chosen `BH` does not collide with an existing route.

The preflight and verification scripts must assert the full fixed field card against `sys.columns` and `v_tbcolumn`, their `PO` groups, positive unique `RID` values, and the two mappings above. A different suffix, control, or omitted semantic field requires explicit active-source evidence in the contract; do not infer an exemption from another route or customer.

### Gate 4: register route and metadata in dependency order

For `*_PJLX` width, remember that `GLZD=IOBDZD_BH` stores the short route code but displays `IOBDZD_MC` through `IOJCBDZD_BYZD=IOBDZD_MC`. Size maintenance `宽度` and query `列宽` from the longest active `IOBDZD_MC` value with same-version font/DPI margins; never size from `LEN(IOBDZD_BH)`, SQL storage length, or the four-character label alone.

When the client replays a detail page through `PageRowsTab`/翻前单, its outer predicate may be fixed to the alias `单号`. If the detail physical field is `<DETAIL>_SJDH`, its maintenance metadata `显示名` and `标签名` must therefore be `单号` unless active source evidence proves a different predicate; verify the generated derived-table SQL with the exact outer filter before claiming the repair complete. For the standard 22-point bold 宋体 `PJLX` static control, use a source-backed text measurement plus margin for maintenance `宽度` separately from query-grid `列宽`; a label-only or route-character estimate is insufficient.

Use one reviewed transaction for related metadata writes, with row-count assertions and a rollback artifact. Do not copy rows blindly from another customer.

#### Runtime cross-table closure gate

`GetCrossTable(<IOBDZD_MC>)` is a fail-soft runtime boundary in the legacy client: an ADO/metadata exception is caught and the function returns an empty string. A valid `IOBDZD` route therefore does not prove that the `FROM` source is usable. Before accepting a dynamic bill, materialize and validate `GetDataField(<MC>查询)` and `GetCrossTable(<MC>)` independently. For every `v_tbcolumn` row with non-empty `GLZD`, require non-empty `字段名`, `IOJCBDZD_TABLE`, `IOJCBDZD_VKEY`, and `LMark/RMark` values (use `''` rather than `NULL` when no alias is intended), then validate the generated `LEFT JOIN` against real tables and columns. Fail closed on either an empty cross-table result or an unparseable join; do not let the client turn the exception into `FROM )`.

1. Register `IOJCBDZD` lookup/table mappings needed by `切换=1`, `帮助`, `GLZD`, `GetCrossTable`, and display/key conversion. For `BTYPE=1/2`, register the correct route and (for `BTYPE=2`) both master-tree and right-side dataset metadata. For `IOBDZD` bills, keep lookup registrations separate from the bill route.
2. Register one unique `IOBDZD` row for a dynamic bill: `MC`, a class-grouped `BH` allocated from the inventory, a `MARK` of exactly two ASCII letters unique across the whole `IOBDZD` table, non-empty `FORMAT` (default `YYMM####` when a new contract omits it), header/detail tables and keys, and only the tabs/options read by the active version. Prove `AutoOpen` resolves this row before any `BTYPE=2` fallback. Do not create an `IOBDZD` row for a basic-data or category-tree form.
3. Populate maintenance `SYS_TbColumn` rows and validate through `v_tbcolumn`, not only the base table. For dynamic bills use the visible bill name with `PO=1` header and `PO>1` detail rows; for `BTYPE=2` keep the `LBNAME` and `MC` metadata sets distinct. Every runtime field must have a real physical column and complete `RID`, `类型`, `标签名`, flags, layout, and (for every dynamic `PO=1` row) a non-null `控件`. For newly generated metadata, use `类型='D'` for physical `date`/`datetime`/`datetime2` fields and `类型='S'` otherwise; ordinary fields use `控件='E'`, while `*_PJLX` uses `控件='S'`. `顺序` is a runtime ordering input: after compiling/inserting metadata, renumber it separately for every `(表名,PO)` group as the contiguous sequence `1..n` (never start at `0`, reuse a stale number, or let duplicates remain). `RID` is a runtime control identifier, not optional display metadata: it must be a positive integer, unique across the new maintenance and query metadata set, and generated by the target's current `MAX(RID)+offset` strategy rather than hard-coded customer-specific numbers. The client-equivalent verification must read the same `RID`, `顺序`, and other fields from `v_tbcolumn` that `CreateDlgItemWithArrayDateTime` consumes; database deployment success alone does not prove a form can be reopened. In a repair of existing metadata, do not normalize old rows by guesswork; first capture the exact old values and use a separately authorized repair contract. For `列宽`, use the shared `scripts/metadata_width.py` rule on the field's visible `标签名` as the first-view minimum: three Chinese characters map to `840`, one full-width character to `280`, ASCII characters count as half-width cells, and the result is rounded up to the control's `15`-unit step (`4` Chinese characters -> `1125`). New metadata defaults to this label width; a deliberately wider explicit width is allowed, but a visible field width below the label minimum must fail closed. Maintenance and query metadata calculate this independently from their own labels; never copy a content-driven reference width, use the `100` fallback, or mix maintenance and query widths. For `*_PJLX`, the label minimum is not enough: compute a source-backed width from the longest current `IOBDZD_BH` display value plus measured font/DPI margins, independently for form `宽度` and grid `列宽`; fail closed if the current longest route value cannot fit. The static artifact validator must apply the same rule. For an existing repair, preview visible rows below the label minimum, update only those rows with exact old-value and affected-row assertions, and preserve already wider columns. Unmatched custom fields remain unchanged until a source-backed width is confirmed. In the standard detail Grid, `控件` is retained as metadata but is not the cell-editor switch; detail behavior comes from the Grid fields such as `类型`, `帮助`, `管道字符`, `只读`, `列宽`, and lookup mappings. `IOJCBDZD_*` mapping fields are not `SYS_TbColumn` fields unless `sys.columns` proves that this deployment actually has such columns. Generate default header layout from a working same-version bill with a proven equivalent fixed-field and footer layout, as required below; do not invent an unrelated coordinate system for each new form. For every `(表名,PO)` metadata group, exactly one row may have `主键=1`; do not model a composite or duplicate metadata primary key. `关键字段` must be explicit, must not be copied from an identity primary key by default, and the query field set must contain exactly one `关键字段=1`.
4. For every dynamic bill, add a separate non-empty `<IOBDZD_MC>查询` `SYS_TbColumn` field set. It is not a second `IOBDZD`. Build it from the original bill's cross-table joins, keep one query row per output alias, remove duplicate aliases such as header/detail `ID`/`单号`/`备注`, keep exactly one query `主键` and one query `关键字段`, and verify the client-shaped title SQL plus derived-table paging/count SQL. The query set must retain exactly one visible, required header document-number field (`<HEADER>_SJDH`, alias `单号`) and one visible, required header-date field (`<HEADER>_YWRQ`, alias `日期`) as stable default-sort keys; deduplication must use explicit aliases rather than deleting either anchor. Distinguish the two empty-source failures: `SELECT  FROM <valid joins>` means the query field list is empty; `SELECT <fields> FROM )` means `GetCrossTable` returned empty and its route/`GLZD` join contract failed. Never copy both header and detail identity rows under the same display name.
5. Add `IOYYGX` only for proven extra operations, references, or upstream/downstream consumers. Add `IOPOPDLG` only when the active source uses its fallback relation. Validate operation uniqueness, enabled flags, `CZ/CZD/CX`, `GLTJ` placeholders, red/blue branches, `SYLJ/XYLJ` replacement, and one-result-set/column-shape contracts.
6. For dynamic bills, register real active `BDJB` rules using the value the active client actually queries (normally visible `IOBDZD_MC`), including audit and cancel-audit symmetry where applicable. Do not add no-op rules merely to pass initialization.
7. Create `SYSWSPACE` parent, leaf, and operation-permission rows in the target hierarchy; set the actual role columns and verify the leaf is returned for the intended role. `SYSWSPACE_MC` is a runtime business name used by `AutoOpen` and permission lookup, so it must match the new `IOJCBDZD_MC`/`IOBDZD_MC` and `SYS_TbColumn.表名`, and must be globally unique in the target database. If a generic name such as `物料` already exists, choose a business-qualified visible name and propagate it through every route, metadata, workspace, help, and verification row; never rename only the workspace text or overwrite an existing node. Preflight must check both generated-name duplicates and existing `SYSWSPACE_MC`/form-name collisions before DDL or metadata writes. For newly inserted form/metadata rows, default every role-permission column that actually exists in the target schema to `1` (authorized), unless the request explicitly requires restriction; discover role columns from `sys.columns` and never invent role names. Do not overwrite existing permissions or bulk-authorize unrelated existing rows. Every new `IOBDZD` header/detail bill must also carry the fixed `sysmenu` set from the Sales Order reference: `显示关联单据`、`保存列宽`、`列配置`、`从EXCEL导入`、`说明`、`附件`、`复制分录`, with exact `topfloor/submenu/xh/icon/pmenu/trimenu/uid` values recorded in the contract. A leaf without parents, role grants, operation rows, or this required menu set is incomplete.

#### 3.1 字段闭合与中文映射

For new or ER-derived forms, compare field sets in both directions before deployment: every physical header/detail column must appear exactly once in its maintenance `PO` group and in the independent query set, and every metadata field must resolve back to that physical table or a proven lookup projection. Every visible row must have explicit non-empty `显示名` and `标签名`; a physical field name used as either value is a generation error. Query display aliases and labels must be unique. A row-count match without field-name and label-map comparison is insufficient.

### 4.1 主表默认布局生成

For every visible dynamic header (`PO=1`) with custom fields, derive coordinates from a working same-version header with the nearest proven equivalent layout before inserting metadata. Read `Bill.cpp::CBill::OnSize` and the active `MoveToItemSJ`/`MoveToItem`/`MoveToMid` helpers first: the client repositions the footer controls at runtime, so those controls are anchors, not ordinary custom-field slots. Layout generation is a contract, not a collection of convenient constants.

#### 4.1.1 先锁定可用区域

- The reference evidence must record the coordinate unit, the first ordinary input left edge, the ordinary input right boundary, the first row top, the row step, ordinary control height, horizontal visual gap, audit rectangle, audit natural gap, and the client gap from the audit bottom to the detail grid. If any of these cannot be proved from the same-version reference/source, stop with `review-blocked`; do not invent a global canvas.
- Define the usable header rectangle before placing any field:
  - `ordinary_left_min` is the reference first ordinary input left edge.
  - `ordinary_right_max` is the reference right edge of the usable input area.
  - `ordinary_top_min` is the reference first row top.
  - `header_lower_bound = SHBZ.顶坐标 + SHBZ.高度`.
  - `detail_top = header_lower_bound + MoveToMid gap` from the active client source.
- Every ordinary visible input must satisfy `ordinary_left_min <= 左坐标`, `左坐标 + 宽度 <= ordinary_right_max`, `顶坐标 >= ordinary_top_min`, and `顶坐标 + 高度 <= header_lower_bound`. Label-inclusive rectangles must also remain inside the client area; a label may not be allowed to start below zero merely because the input rectangle fits.
- Hidden identity/runtime rows remain `左坐标=顶坐标=宽度=高度=0` and do not consume a layout slot. Query-page metadata is a separate grid contract and normally keeps zero coordinates; never use query coordinates as maintenance-page evidence.

#### 4.1.2 固定锚点与统一页脚

- Treat `ZDR` (制单人), `SHR` (审核人), and `ZY` (摘要) as fixed footer anchors. Copy the exact `左坐标/顶坐标/宽度/高度/列宽`, control code, and single-line/multiline contract from the reference. A module-wide fixed-footer policy must use one anchor card for every main/detail bill in that module; do not derive per-form variants from field count.
- Treat `SHBZ` (审核) as the header lower-bound anchor, but do not assume it must occupy an isolated column. Copy its reference left coordinate, width, height, and complete label-plus-input footprint. Try the current row first; wrap only when that complete footprint would cross `ordinary_right_max` or intersect a field already on that row.
- The audit rectangle's bottom, not the last ordinary field's bottom, defines the header lower bound. No ordinary field may cross it. When `SHBZ` wraps, its top is `last earlier non-fixed visible header bottom + natural_gap`; when it shares a row, do not insert a vertical gap that is absent from the reference.
- Fixed footer rectangles are reserved space. Never allocate a custom field into, between, or beyond those rectangles, and never move them as a side effect of ordinary-field reflow. Only a source-proven multiline business field may use `EM`; changing a custom field to multiline must trigger a fresh collision and lower-bound check.

#### 4.1.3 按标签完整占用区间装箱

- Bind semantic anchors (`YWRQ`, `PJLX`, `SJDH`, and `SHBZ`) by field meaning, then walk remaining visible header fields in stable `顺序`. Place each field in the current row first. A row is accepted only when the full footprint fits: measured label width, label/input spacing, outer input rectangle, browse-button reservation, and right margin.
- The first input on a row uses the reference left baseline. For later fields, use `previous input right + reference visual gap + next measured label width + label creation margin`; the active `CDataEdit` path uses the measured `GetTextExtentExPoint` width plus the label control's `6`-unit creation margin, followed by the input's `5`-unit left offset. Do not substitute character counts, fixed columns, grid widths, help-string length, or per-character pixel estimates.
- A non-empty `帮助` reserves `max(20, imageWidth + 8)` client units for the browse button in the active BCG build. The measured button width is part of the outer input footprint, not an afterthought. A field that fits by text width but not after the browse button is included must wrap or be rejected.
- Use the reference row baseline and row step for every wrapped row. Do not place fields using `top += height` unless the reference proves that is the active rule. Preserve the reference visual gap; do not create a large empty row merely to avoid doing the packing calculation.
- Widths are independent contracts: maintenance `宽度` is the input rectangle, query `列宽` is the grid column, and neither may be copied blindly from the other. Use the nearest same-semantic reference width or a measured business requirement; preserve a deliberately wider existing width, but fail closed when the label/help footprint cannot fit.

#### 4.1.4 生成、修复和验证门禁

- Before a repair, capture the exact old values for every touched row. A coordinate repair may change only `左坐标/顶坐标/宽度/高度` and, when explicitly contracted, `列宽`; it must not silently change field name, `PO`, `RID`, label, help, relation alias, type, control, required/read-only flags, or order.
- After generation, assert: fixed footer anchors equal the reference; every visible rectangle has positive dimensions; all ordinary inputs stay inside the locked rectangle; label-inclusive footprints have no negative left edge; fields on one row do not intersect; row tops follow the reference baseline/step; `SHBZ` is on the current row whenever its complete footprint fits; wrapped `SHBZ` uses the evidence-backed `natural_gap` and at least the validator minimum of 10 units; ordinary fields end above the audit bottom; and the derived detail top follows the client gap.
- Persist the target-to-reference field mapping, canvas bounds, row step, visual gap, measured labels, browse-button width, audit geometry, `natural_gap`, and old/new coordinates in the forward/rollback artifact. A rerun must produce the same plan or stop on an old-value mismatch.
- When font, DPI, window size, or runtime resize changes the required geometry, metadata coordinates are only the initial rectangle. The contract must include client-side reflow at creation and resize; without both same-version measurements and the client implementation, do not claim that the form is adaptive or collision-free.

### Gate 5: execute the runtime-shaped verification

Run parse-only checks, then read-only contract checks in every environment and transactional CRUD/audit tests only in an explicitly authorized test database. The verification must prove:

- route classification and unique `MC/BH/MARK` resolution;
- physical columns, keys, constraints, and header-detail joins;
- for a `CBill` route, the complete fixed-field card in Gate 3.1, including physical/header-detail fields, the `PJLX` required/mapping/`控件=S` contract, and the verified `SHBZ` mapping;
- `v_tbcolumn` field sets, `PO` grouping, exactly one metadata primary key per `(表名,PO)`, one explicit business `关键字段` per detail page where the runtime requires it, exactly one query `关键字段`, unique query aliases, positive/non-null unique `RID` values across maintenance and query rows, and source-confirmed controls; verification must reproduce the client control-initialization field reads and then require a real client reopen for final acceptance;
- before lookup tests, assert exact bidirectional field closure for every physical table and metadata group, no missing/extra fields, no empty `显示名/标签名`, no physical-name fallback, and reviewed field-map values for critical labels;
- lookup display-to-key and key-to-display round trips;
- non-empty query metadata, unique aliases, separately non-empty `GetDataField` and `GetCrossTable` results, executable title SQL, and paging/count wrapper; fail on either `SELECT  FROM ...` or `FROM )`;
- for `BTYPE=1`, visible-name-to-table routing, physical-column mapping, and no invented dynamic-bill query/`IOBDZD`/`BDJB` contract;
- for `BTYPE=1`, reproduce the `UForm1` zero-based field/grid access and assert every `(表名,PO)` order is exactly `0..COUNT(*)-1`; an extra `IOJCBDZD_BYZD` projection column may hide an off-by-one error but does not change this contract;
- for `BTYPE=2`, assert one unique route, source-confirmed master/detail hard columns, and executable tree-root and selected-node detail SQL using those exact columns; `LBNAME` metadata must close to the tree and `MC` metadata must close to the right dataset, with no `*_CODE`/`*_NAME` substitution accepted;
- for `UForm1` metadata, reproduce `GetDataField(..., true)`/`GetCrossTable` field generation and assert that ordinary fields have empty `SYS_TbColumn.标识`; a non-empty marker (including the string `0` in an `nvarchar` column) is a runtime switch that emits `sum(case FF_BS ...)`, not a generic false value;
- test the initial-load path and the search-button path separately: a successful `Refresh()` does not prove that a fixed search predicate such as `码表编号` exists on the target table; an absent search column is a client-source defect and must not be masked by adding an invented business column;
- each enabled `IOYYGX`/`IOPOPDLG` relation and `SYLJ/XYLJ` result shape;
- applicable `BDJB` save/audit/cancel-audit behavior and rollback;
- workspace hierarchy, role visibility, and operation authorization;
- zero test-data residue after rollback.

If a runtime-shaped SQL check fails (including `SELECT  FROM ...`), a control initialization error, a dangling metadata field, an unresolved lookup/relation, a missing lifecycle rule, or an unauthorized workspace leaf is found, report the evidence and stop. Do not declare the form complete or continue adding unrelated metadata.

### Gate 6: deliver and separate scope

Deliver the forward/rollback/verification/CRUD artifacts, a dependency matrix, target identity and write authorization record, verification results, and a list of remaining client work. Explicitly separate database rows from MFC resources, command IDs, client menu wiring, executable changes, and packaging; never imply that database metadata alone creates those client features.

### Fast Path: ER-driven dynamic bills

For repetitive “改 ER 图/建一个表单” work, use `scripts/scaffold_dynamic_bill.py` before hand-writing SQL:

1. Parse the SVG into `contract.json`; preserve the source path and the header/detail field list. Pass `--reference-bill-name` when a same-version working bill is known so the scaffold also emits `reference-evidence.sql`.
2. If a previous contract exists, pass `--baseline-contract` and review `contract-diff.json`. Any added, removed, or same-label renamed field invalidates reuse of the old forward/rollback/verification/CRUD package. Reconcile the physical schema, both maintenance/query metadata sets, lookup mappings, and tests together.
3. Run the generated read-only `preflight.sql` and, when a reference bill is supplied, `reference-evidence.sql`; only after the target identity, base-table columns, `IOBDZD`, lookup route, and working same-version reference are confirmed should a human produce deployment SQL.
4. Run `scripts/validate_dynamic_bill_artifacts.py` on the final `forward.sql` and `crud-test.sql`. It resolves each `SYS_TbColumn` tuple against the statement's actual column list, checks arity, `标识=NULL`, physical date fields using `类型=D` and other new fields using `类型=S`, ordinary `控件=E`/`*_PJLX` `控件=S`, visible-label minimum `列宽`, fixed or `@RIDBase+offset` RID uniqueness/range, the required `MAX(RID)+1` declaration and positive-value guard, CRUD column/value parity, explicitly supplied audit coordinates, same-row outer-rectangle collisions, and help-bearing widths against the measured browse-button footprint. `--expected-audit-gap` applies only when `SHBZ` is wrapped below a prior row; a same-row audit is valid without that vertical gap. It accepts both `INSERT dbo...` and `INSERT INTO dbo...`, normalizes quoted SQL literals, and excludes the separate `<MC>查询` layout from maintenance-page audit-coordinate assertions before SQL Server is involved.

The fast path reduces repeated parsing and counting; it does not bypass route, control-code, audit-coordinate, `FF_BS`, lookup, relation, or authorization gates. A generated scaffold is review-only and never deploys by itself.

## Dynamic-bill hard-stop rules

- An ER `FK` marker is evidence of a relationship, not permission to invent a foreign-key target. Keep it unresolved and report it until the target table/key is confirmed.
- `RECORD_BH`/similar newly added fields must appear consistently in physical tables, maintenance metadata, the separate `<MC>查询` metadata, CRUD tests, verification, and rollback review. A label-only edit is incomplete.
- A renamed `ZY`/`BZ`-like field must explicitly distinguish the visible business field from any runtime compatibility anchor. Hidden compatibility rows must be excluded from visible layout assertions and documented for client testing.
- For audit controls, copy a working same-version anchor: validate the complete label-plus-input footprint, not only the input rectangle. The audit lower edge is the header layout boundary; do not guess a new minimum width or let ordinary fields overlap the tab. The static validator must recognize `N'..._SHBZ'` SQL literals and compare the maintenance page only; query-page audit rows normally stay hidden/zero-coordinate.
- For asset-type/basic-data help, prove the physical code column and the full `IOJCBDZD` route (`BTYPE`, table, key, display column, help key) plus `SYS_TbColumn.GLZD/帮助`. A Chinese label alone is not a working lookup.
- Ordinary metadata rows keep `标识` `NULL` unless a confirmed client source and working route prove a real `FF_BS` producer. The string `'0'` is not a universal false value.
- New dynamic-form metadata uses `类型='D'` for physical `date`/`datetime`/`datetime2` fields and `类型='S'` otherwise; ordinary fields use `控件='E'`, and `*_PJLX`/凭证类型 fields use `控件='S'` in both maintenance and query metadata. No other type or control may be inferred from bit-ness, numeric precision, label, or layout.
- For an existing metadata repair, the preflight must assert the exact current (old) value and the forward statement must update only that old value to the proven target value; never put the desired value in the update predicate, because that makes a no-op look like a successful repair. Rollback must assert the repaired value before restoring the captured old value.
- Each `(表名,PO)` metadata group has exactly one `主键=1`, and its `顺序` values must be exactly `1..COUNT(*)` with no gaps or duplicates. Query metadata has exactly one `关键字段=1` across its output set, and duplicate `显示名` aliases are a hard stop because the client wraps the SELECT in a derived table.
- Every required physical field must close to exactly one maintenance metadata row and one independent query metadata row (or the proven route-specific equivalent); every metadata field must close back to a physical field or a proven lookup projection. Empty `显示名/标签名`, physical-name fallback, missing ER label, missing query projection, or extra metadata field blocks generation and deployment.
- Dynamic-bill physical fields must follow the target database's established 拼音首字母缩写/prefix convention. Before DDL, inspect `sys.columns` and same-module tables for collisions, homophones, reserved runtime suffixes, and existing semantic anchors; a new English name or label-only rename is not accepted as a naming decision.
- A module-wide suffix migration such as `..._BH -> ...BH` is never a two-field patch: inventory the entire module, carry the mapping through physical columns, foreign-key/index/constraint definitions, `SYS_TbColumn.字段名/GLZD`, `IOJCBDZD` routes, current scripts and ER artifacts, and keep old names only in labeled migration history. Require old/new field counts, metadata impact counts, property preservation, foreign-key closure, runtime JOIN/help replay, exact row-count assertions, and a guarded reverse map before deployment.

## Form completion matrix

| Route | Physical model | Required database objects | Completion gate |
|---|---|---|---|
| `BTYPE=1` basic data | one complete table | `IOJCBDZD`, visible `SYS_TbColumn`, workspace parent/leaf and role grant | `UForm1` field-prefix rule, physical-field mapping, CRUD and role visibility |
| `BTYPE=2` category/tree | tree master + independent right-side dataset | `IOJCBDZD` with `LBTABLE/LBNAME` and `TABLE/MC`, two metadata sets, workspace/roles | tree selection filters the right dataset; it is not a shared document-number save unit |
| `IOBDZD` dynamic bill | header + one or more detail tables | `IOBDZD`, lookup `IOJCBDZD`, maintenance and `<MC>查询` metadata, applicable `IOYYGX/IOPOPDLG`, active `BDJB`, workspace operation permissions, required standard `sysmenu` button set | `PO`/keys/controls/query SQL/relations/lifecycle/roles/buttons all pass; otherwise incomplete |

## Bundled Tools

Use `scripts/generate_first_pass_sql.py` when the user provides a `BDJB_PJLX` and optional document number but no ready first-round script. If the user already supplied an exact safe query, execute that query directly instead of delaying it with generation.
Use `scripts/scaffold_dynamic_bill.py` for ER-driven dynamic-bill contract drafts and `scripts/validate_dynamic_bill_artifacts.py` for SQL tuple/CRUD static checks. These tools are parse-only and do not connect to SQL Server.

Use `scripts/extract_bdjb_rules.py` on a JSON, CSV, or TSV export of the relevant BDJB rows when several scripts update related targets. It produces a static review matrix for update targets, assignment modes, and predicate fields. Treat every result as a candidate and prove it with live read-only data.

Run `scripts/self_test.py` after changing either bundled script.

## Standard Workflow

1. Record the exact target, user-provided entry point, example document, requested action, and any unresolved business term.
2. Ask immediately if environment or business meaning is ambiguous and cannot be resolved read-only without choosing a direction.
3. Connect only to the resolved environment and verify `DB_NAME()` plus `@@SERVERNAME`.
4. Execute the narrowest confirmed entry query first. For BDJB/audit issues, use the mandatory fast path; do not start with broad object searches.
5. Build an evidence table: rule/object, target field, predicates, actual values, matched row count, and observed outcome.
6. Follow the first failed predicate or broken join upstream one confirmed hop at a time. Expand scope only after the current hop is proven.
7. Before editing, confirm the complete symmetric path when relevant: audit, cancel-audit, cumulative recalculation, repeat audit, partial cancel, status trigger, and historical data impact.
8. Save the smallest deployable change and its backup/rollback artifact under the repository's diagnostic convention.
9. Parse first, deploy only when authorized, then verify the exact definition, original document, aggregate cases, and rollback path.
10. Report facts separately from assumptions: root cause, affected scope, target database, changed artifact, verification, writes performed, and remaining uncertainty.

## Script Generation And Phase Gates

For a new basic-data form, prefer deterministic generation over hand-writing repeated metadata tuples. Keep the user-facing work to three gates: read-only preflight, authorized transactional forward deployment, and read-only/runtime-shaped verification plus isolated CRUD. Use the same UTF-8 `sqlcmd -b -f 65001` execution shape for every generated script; capture the exit code and stop on the first failure. Do not claim a visible MFC form, menu resource, or package from database metadata alone.

## Database Object Development

For new business tables and other database objects, use the schema-development reference rather than treating the request as a debugging incident. Start from the nearest confirmed IMES object conventions, produce reviewable forward/rollback/verification artifacts, and test against the resolved test environment when write access is explicitly authorized. Never deploy through a project-mapped read-only MCP.

For a dynamic bill/form, also follow the database contract in `references/document-form-contract.md`. Include metadata and lifecycle dependencies in the same review: a form that can open but lacks effective maintenance `v_tbcolumn` rows, the separate `<visible bill name>查询` dataset used by the standard bill-search tab, lookup translations, relation SQL, active `BDJB`, or a role-visible `SYSWSPACE` leaf is incomplete. Validate the runtime read path before proposing DDL or configuration writes.

Treat every dynamic bill `PO=1` header row's control type, `RID`, field type, label, flags, and layout as runtime inputs rather than optional decoration. In clients that directly convert these values, a `NULL` control type can abort initialization before the form opens; derive valid control codes from the active source and a working bill in the same database, then fail verification on missing or unexpected values.

## Custom Report SQL

1. Inspect the report runner or project source to determine whether it wraps the saved SQL in a derived-table query such as `SELECT * FROM (<saved SQL>) a WHERE 1=1`.
2. When the runner wraps the SQL, output only one inner `SELECT` statement. Do not add the wrapper yourself, a trailing semicolon, `ORDER BY`, CTE, `DECLARE`, `SET`, temporary tables, or multiple result sets. Put joins, filters, aggregation, and aliases inside that statement.
3. Assume the outer layer may append filters against returned aliases. Keep aliases stable and valid as derived-table column names; do not reference the outer alias from the inner query.
4. For no-parameter reports, do not add `@` placeholders or UI parameter markers. Validate the final SQL by executing it inside the same wrapper shape before handing it off.
5. If the runner's wrapping behavior cannot be proven from source or a confirmed report execution path, ask one focused question before choosing a SQL shape.

## Safety Rules

- Keep initial investigation read-only and use least-privilege access.
- Never ignore or postpone an exact SQL entry point supplied by the user unless it is unsafe or targets the wrong confirmed database.
- Do not run broad `sys.sql_modules`/schema scans before the narrow entry path is exhausted. Broaden only to answer a specific unresolved question.
- Do not guess columns, UI label mappings, marker semantics, or cumulative-versus-overwrite behavior. Prove them from definitions/data or ask.
- Never infer that an environment is production or test; record the classification as unknown until evidence confirms it.
- Treat database names, object names, document numbers, and generated paths as untrusted input. Parameterize values, safely quote validated identifiers, and keep output paths inside the repository.
- Before destructive or repair SQL, preview affected rows, assert the expected row count, prepare rollback/restore steps, and obtain explicit authorization immediately before execution.
- For negative unique-key tests, do not continue a transaction after a constraint error under `XACT_ABORT ON`. Use an isolated test transaction with `XACT_ABORT OFF`, a savepoint, explicit handling of 2601/2627, rollback to the savepoint, and a final rollback; assert `XACT_STATE()`/`@@TRANCOUNT` and zero test residue.
- Never place credentials, tokens, server secrets, or connection strings in scripts or replies.
- Never test an unknown write procedure in production merely by wrapping it in an outer transaction; the procedure may commit or roll back that transaction. Prefer a disposable clone or confirmed test environment.
- Preserve outer transactions: use savepoints where valid and never issue an unconditional rollback that can destroy caller work.
- Do not leave debug result sets in BDJB scripts or procedures consumed by PDA interfaces.
- When `INSERT ... EXEC` captures output, ensure the called chain returns the expected result-set shape only.
- Preserve business errors; do not convert failure into a silent success result.

## Self-Improvement

Only update this personal skill when the user explicitly requests or authorizes it. First record project-specific evidence in the active repository's `docs/imes/` or `diagnostics/` layer. Then add only a concise reusable entry to `references/patterns.md`: symptom, likely cause, safe fix pattern, and verification. If the new rule changes task routing or a first-action gate, update this `SKILL.md` and the applicable `references/evaluation-cases.md` as well. Exclude customer names, proprietary customer rules, document numbers, credentials, dated incidents, and unverified schema assumptions.

Then run the bundled script self-test and the skill validator in Python UTF-8 mode against this directory. Review the applicable cases in `references/evaluation-cases.md`; use independent forward-testing only when current agent and production-safety instructions allow it.
