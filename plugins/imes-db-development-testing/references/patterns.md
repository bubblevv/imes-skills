# Common IMES Patterns

## Schema Variability

IMES deployments share business concepts but can differ by customer version, customization, and naming. Confirm every object, column, status value, and relationship in the target database before using it; no object name from another diagnostic package is a default prerequisite.

## Dynamic Bill Number Format Is Missing

Symptom: a dynamic bill opens its route but new-document numbering is empty or fails to produce a usable number; `IOBDZD_FORMAT` is `NULL`, empty, or whitespace.

Likely cause: `CBill::OnTynew` calls `GenDanhao` with the visible bill name, and `GenDanhao` calls `PRD_GETDANHAO`; the procedure reads `IOBDZD_FORMAT` by `IOBDZD_MC` and only emits a number inside its supported format branches. `IOBDZD_BH` is used as the header `PJLX`/data-permission type, while `IOBDZD_BILLNO` is not read by this current numbering entry point.

Safe fix pattern: for a new dynamic-bill contract normalize a missing format to the literal `YYMM####`, and retain explicitly confirmed non-empty formats such as `YYMM####`. For an existing repair, first query `MC/BH/MARK/FORMAT/BascData/CurMonth/ModifyDate`, assert the exact empty old value and one intended row, then update only `IOBDZD_FORMAT` in a database/instance-guarded transaction. Do not reset `BascData`, `CurMonth`, or `ModifyDate`, and do not overwrite a non-empty format. Confirm the procedure definition before accepting a custom format; the current branches are `YYMM`, `YYYYMM`, `YYMMDD`, and `#` serial mode.

Verification: assert `IOBDZD_FORMAT` is non-empty and equals the reviewed contract value, prove the route is uniquely found by `IOBDZD_MC`, verify the physical `<HEADER>_PJLX` still carries `IOBDZD_BH`, and keep the old/new format in a symmetric rollback artifact. A read-only MCP may provide the evidence but must not execute the repair; after an authorized test execution, reopen the bill and create a new document to confirm the client receives a number.

## Dynamic Bill Route Codes Are Allocated By Class Inventory

Symptom: a new dynamic bill is registered, but its `IOBDZD_BH` is an isolated code invented for that one form, or its `IOBDZD_MARK` is a long bill code, a digit, or a duplicate of another route. Numbering then either collides with an existing route or produces a prefix nobody can trace back to a business class.

Likely cause: `BH` and `MARK` were chosen form by form instead of from the target database's existing allocation. `AutoOpen` needs a non-empty unique `MARK` to enter the dynamic-bill path, and `PRD_GETDANHAO` reads `MARK` by `IOBDZD_MC` to build the document number, so both values are route identity rather than free-text labels. Nothing in the runtime rejects a badly shaped mark; it fails later, as a wrong or colliding document number.

Safe fix pattern: before assigning either value, run a read-only inventory of the target's `IOBDZD` rows and group them by business class.

- `IOBDZD_BH`: keep forms of the same business class grouped together and assign downward as class prefix plus serial number, taking the smallest unused serial in that class. Preserve a confirmed existing class prefix; do not invent a new prefix for a form that belongs to an established class, renumber unrelated routes, or allocate an isolated code from the new form alone. Because the prefix-plus-serial form has no fixed width, size dependent columns from the current longest route value instead of assuming a six-character code.
- `IOBDZD_MARK`: require exactly two ASCII English letters, globally unique across the entire `IOBDZD` table. Reject `NULL`, empty or whitespace-only values, digits, Chinese characters, three or more letters, mixed non-ASCII, and any duplicate of an existing mark. A generator must fail closed on a missing or malformed mark rather than substituting a default such as `1`.

Both values are fixed route identity, so a repair must not change an existing confirmed `BH` or `MARK` to accommodate a new form.

Verification: assert the mark is exactly two ASCII letters, unused before the write and still unique after it; assert the chosen `BH` does not collide with an existing route and sits in its class's serial range; keep the inventory that justified both choices in the evidence package. Do not accept a route registration whose `BH`/`MARK` provenance is only "it was free".

## Dynamic Bill Metadata Is Incomplete

Symptom: a new transfer/transaction table exists, but the dynamic bill cannot open, fields are missing or read-only incorrectly, lookup values save as display text, references return no rows, upstream/downstream search fails, or the authorized user cannot see the form.

Likely cause: only the physical tables and one registration row were added. The runtime contract also requires an `IOBDZD` mapping, effective `v_tbcolumn`/`SYS_TbColumn` rows, `IOJCBDZD` lookup and join mappings, `IOYYGX`/`IOPOPDLG` relation metadata, applicable `BDJB` lifecycle rules, and a role-visible `SYSWSPACE` leaf (and sometimes `sysmenu`).

Safe fix pattern: read `references/document-form-contract.md`; trace the active source query path; build a dependency matrix from `MC/BH` to header/detail keys, `PO` field metadata, lookup translations, relation placeholders and permission hierarchy; preview every affected metadata row; then deploy the smallest forward/rollback/verification set only to an authorized test environment. Do not guess enum values or copy another customer's metadata.

Verification: prove the physical join, `IOBDZD` lookup, `v_tbcolumn` header/detail result, display-to-key and key-to-display lookup, every enabled `IOYYGX` relation including `CZ/CZD` and red/blue branches, `SYLJ/XYLJ` result shape, applicable audit/undo rules, and `SYSWSPACE` role visibility. Record client-form work that remains outside the database scope.

## Dynamic Header Control Initialization Error

Symptom: an `IOBDZD` dynamic bill resolves its registration and begins loading header metadata, then shows a generic control-initialization error before the header is usable.

Likely cause pattern: one or more `SYS_TbColumn`/`v_tbcolumn` `PO=1` rows has a `NULL` or invalid `控件`, `RID`, `类型`, `标签名`, flag, or layout input. Some legacy clients directly convert these values while constructing controls, so a nullable metadata column can still be a mandatory runtime value. Detail-grid metadata may follow a different creation path; do not assume a header requirement applies identically to every `PO`.

Safe fix pattern: identify the last successful initialization stage from the runtime log, inspect the exact active control-creation source, query every header row in `PO,顺序` order, and compare the metadata contract with a working dynamic bill in the same client/database version. For newly generated dynamic metadata, use `类型=D` only for physical `date`/`datetime`/`datetime2` fields and `类型=S` otherwise; ordinary `控件` is `E`, while `*_PJLX` voucher-type `控件` is `S`. For an existing repair, preserve old values until a separately authorized repair contract captures them. Build an explicit field map, assert the expected field set and current bad-value distribution, then update only those rows in one transaction on an authorized test database.

Verification: fail on any missing control or any generated ordinary control other than `E` / `*_PJLX` control other than `S`; require `D` for physical `date`/`datetime`/`datetime2` fields and `S` for all other new fields, plus non-null/unique `RID`, non-empty label, complete flags and layout, and positive dimensions for visible controls. Re-run the full database contract and CRUD tests, reopen the original form, and confirm the runtime log advances through header creation, detail-page initialization, and total bill opening.

## Missing `CBill` Fixed Fields

Symptom: a newly registered `IOBDZD` bill exits or raises `0xC0000005` while the client is preparing the page, even though the route, `BDJB`, and ordinary control metadata appear valid.

Likely cause: the physical header or `PO=1` metadata omits one of the `CBill` fixed semantic fields. The common contract is HID, date, voucher type, document number, print count, audit state, creator, auditor, and summary; every detail page also needs FID, document number, and line number. In particular, missing `PJLX` leaves the client without the control it uses for the route/type display and fixed filtering; missing footer anchors such as `ZY` can leave layout IDs unresolved.

Safe fix pattern: before deployment, compare the exact same-version source and working bill with the target's `sys.columns` and `v_tbcolumn`. Require actual fields and maintenance metadata for the whole card. Set `PJLX` as required and mapped through `切换=1/GLZD=IOBDZD_BH`; use the proven audit mapping, normally `切换=1/GLZD=LSDJZT_BH`. Generate one guarded physical-and-metadata migration with a rollback artifact; do not conceal a missing field by adding a null check in the client.

Verification: fail preflight on any missing fixed field or mapping; after deployment confirm physical nullability/defaults, `PO`, `RID`, control contract, and `v_tbcolumn` mappings. Reopen the original bill before declaring the repair complete. A different suffix or control is valid only with active-source evidence.

## Runtime RID Allocation Must Be Guarded

Symptom: a newly registered dynamic bill has complete-looking `SYS_TbColumn` rows but the client immediately shows `控件初始化时出错!` while opening either the maintenance page or its query page.

Likely cause pattern: the active control factory directly converts `RID` to an integer. A `NULL`, non-positive, or duplicate value is therefore a runtime contract failure even though SQL accepts the nullable metadata column. The same defect can be generated again when a scaffold emits `RID=NULL` or assigns fixed numbers without considering the target database's existing metadata.

Safe fix pattern: confirm the source read path and the exact maintenance/query field set, preview the target rows and their current null distribution, then use a guarded transaction that asserts the exact row count and all target rows are in the expected bad state. Allocate `MAX(RID)+1` at execution time, assign deterministic offsets ordered by `(表名,PO,顺序,字段名)`, and assert positive, unique values plus the exact affected-row count. Keep an exact rollback artifact; do not overwrite pre-existing non-null values or repair through a read-only production MCP.

Verification: check both `SYS_TbColumn` and `v_tbcolumn`; fail on any null/non-positive/duplicate `RID`, missing physical field, or mismatch in `类型/控件/标签名/显示/必填/只读/布局`. Re-run contract and isolated CRUD tests, then require a real reopen of both the dynamic bill and its query page. A SQL pass without that client action must be reported as incomplete runtime verification.

## Dynamic Bill Title SQL Has An Empty Field List Or Cross Table

Symptom: a dynamic bill initializes far enough to build a title/search/print query, then reports a SQL error near `FROM`; the logged SQL is either `SELECT  FROM <header/detail joins> WHERE 1=2` or `SELECT <fields> FROM )`.

Likely cause pattern: these are two separate runtime failures. The first means the standard bill container called `GetDataField(<IOBDZD_MC>查询)` but the dedicated query metadata set is empty. The second means `GetCrossTable(<IOBDZD_MC>)` returned an empty string after its ADO/metadata exception path. Typical upstream causes are an incomplete `IOBDZD`/fallback route or a `GLZD` row whose `字段名`, `IOJCBDZD_TABLE`, `IOJCBDZD_VKEY`, `LMark`, or `RMark` is missing/invalid. A non-empty maintenance field list and a valid-looking `IOBDZD` row do not prove that the final `FROM` source is usable.

Safe fix pattern: materialize `GetDataField(<MC>查询)` and `GetCrossTable(<MC>)` independently. For an empty field list, create the separate `<visible bill name>查询` set, preserve required identity/filter/translation fields, and remove duplicate aliases such as header/detail `单号`; do not create a second `IOBDZD`. For an empty cross table, validate the source priority `IOBDZD -> IOPOPDLG_JOINSTR -> IOJCBDZD_TABLE`, then close every `GLZD` mapping and execute each generated `LEFT JOIN` against confirmed tables/columns. Store no-alias markers as empty strings rather than `NULL`. Do not mask either defect in client code.

Verification: assert both runtime strings are non-empty, execute `SELECT <query fields> FROM <cross table> WHERE 1=2`, and execute the actual derived-table/paging/count wrapper. Also assert unique aliases, physical and translated fields, and the exact `FROM` source; then reopen maintenance, search, preview, and print-design paths. A check that only tests query metadata cannot certify the `FROM` path.


### 审核槽位最小宽度不能猜写

审核栏目的“孤零零”、标签截断或与输入框脱节，通常不是业务字段问题，而是 `SYS_TbColumn` 的审核矩形被当成普通字段重新排版。审核矩形必须从目标库同版本、同路线有效单据读取，包含标签占位、输入框、控件、顶坐标、高度和列宽；审核不是必须独占一栏，应和其他表头字段一起参加横向装箱，能在当前行放下就同行，只有完整占用区越过右边界才换行。

同库同版本的参考单据应保存审核字段的完整矩形快照，作为本次契约的目标值；部署到其他客户或版本前必须重新查询，静态校验应把目标审核锚点和参照值作为显式参数，而不是写成全球常量。用户已经手动调整的坐标要先保存旧快照，坐标修复只允许最小必要移动，不得顺带修改字段名、帮助、传参或关联别名。

The ER-driven scaffold accepts `--reference-bill-name` and emits a read-only `reference-evidence.sql` pack. Run it before generating metadata so IOBDZD routing and same-version audit/footer anchors are evidence, not global defaults.


验证至少包括：审核字段唯一、显示开启、正尺寸、审核与同排字段的完整标签+输入框占用区不相交、审核底边加客户端 tab 间隙不超过 `IDC_TAB3` 起点，并且 ordinary header fields 不越过该边界。审核换行时才检查上一行到审核顶边的自然间距；同行不应因“固定审核 gap”被误报。

### 帮助按钮占用未计入表头装箱

症状：字段输入框看似没有重叠，但带“帮助”的编号输入被后一个字段挤压，浏览按钮覆盖边框或文本区过窄；把审核放入当前行后尤其容易暴露这一问题。

可能原因：布局只使用了 `宽度` 的文本区估算，没有按实际 `CBCGPEdit` 非客户区扣除浏览按钮。当前 BCG 源码中 `EnableBrowseButton(true)` 的默认 `m_nBrowseButtonWidth` 为 `20`；若设置自定义图标，`OnChangeLayout` 使用 `max(20, imageWidth + 8)`。按钮在编辑框右侧非客户区内，不是帮助字符串长度，也不是可忽略的装饰。

安全修复模式：先用同版本客户端取得带帮助字段的实际窗口矩形和按钮宽度。若契约给出的是可输入文本宽度，先加按钮宽度得到外框 `宽度`；若契约给出的是外框宽度，则在文本可用宽度检查中扣除按钮宽度。横向装箱的完整占用区必须包含标签实测宽度、标签/输入框间距、外框、按钮占用和右侧余量；按钮宽度缺少证据时保持审阅阻断，不按帮助字符串字符数猜写。

验证：对每个非空 `帮助` 字段确认外框宽度大于按钮实测宽度，重放同排字段的外框碰撞检查，并在客户端确认按钮可点击、文本可输入、下一字段标签不覆盖按钮。数据库静态检查只能验证已提供的按钮宽度证据，不能替代真实重开。
## Dynamic Header Custom Layout Is Misaligned

Symptom: a dynamic bill opens, but custom header fields overlap, appear in an unrelated area, have unusable widths/heights, or differ visibly from a working same-version equivalent bill.

Likely cause: coordinates were copied from an unrelated form or assigned as arbitrary constants. `SYS_TbColumn` layout values are client coordinate units, and the same-version bill header already defines the usable canvas, row baselines, gaps, and control sizes.

Safe fix pattern: read the working equivalent header and `Bill.cpp::CBill::OnSize` from the target version; reserve only the fixed `ZDR/SHR/ZY` footer anchors. Put `SHBZ` into the same stable-order packing pass as the other visible header fields: try the current row first, and wrap only when the complete label/input/help footprint crosses the right boundary. Preserve the working common control contract (normally `ZY=E` at the single-line reference height); use `EM` only for a proven long-text field. Set `headerLowerBound` to the audit rectangle's bottom, then bind `YWRQ/PJLX/SJDH` and allocate remaining fields. Since `CDataEdit` creates the label on the left using its runtime `GetTextExtentExPoint` result plus `6`, the next input's left edge is `previousInputRight + visualGap + nextMeasuredLabelWidth + 5`; include the active browse-button width for non-empty `帮助` (current default 20) when deriving the outer edit width. Never estimate this from character count, grid width, help-string length, or a fixed per-character pixel value. Every wrapped row's first field uses the working reference left edge. Runtime resize must recalculate this flow from the active font/DPI; metadata coordinates alone cannot provide adaptive spacing. If the client change or an exact same-version measurement set is unavailable, keep the layout review-blocked instead of claiming it cannot overlap. Keep every variable field above the audit lower bound, never move fixed anchors, and write an explicit target-to-reference/slot mapping with rollback.

Verification: assert fixed anchor coordinates/control codes/heights equal the working bill, positive dimensions for every visible field, label-inclusive rectangles and variable-field natural ordering/gap range, variable bottoms above `headerLowerBound`, canvas bounds, no rectangle intersections within each `PO`, populated `列宽`, source-proven common defaults, deterministic reruns, and separate zero-coordinate query metadata. Reopen the form and inspect both header and search pages after the database contract checks pass.

## 新建表单列宽必须先保证字段名可见

症状：新建动态单据或基础资料后，网格字段值可以加载，但首次打开只能看到字段名的一部分；例如三字标签“分录号”刚好，四字标签“点检记录”却只显示两字。维护页和查询页还可能出现同一字段宽度不一致。

可能原因：生成器把列宽当成数据内容宽度、复制了参考单据的旧内容列宽，或用 `100` 作为默认值；也可能把控件布局 `宽度` 误当成网格 `列宽`，没有按实际 `标签名` 计算首屏最小宽度。

安全修复模式：新生成的可见元数据统一调用 `scripts/metadata_width.py`，以 `标签名` 的完整显示宽度作为最小值；当前客户端以每个全宽显示单元 `280`、三字 `840` 为基准，ASCII 按半宽单元计算，最终按 `15` 单位向上取整，所以四字标签为 `1125`。未显式指定时使用该最小值，显式更宽时保留，显式更窄时在生成和静态 SQL 验证阶段 fail-closed。`宽度` 只保存表单控件布局，`column_width` 只保存表格列宽；维护页和查询页必须各自按自己的标签计算。存量修复先预览精确旧值，只更新低于标签最小值的目标行，已更宽的列不缩窄。

验证：对 `SYS_TbColumn` 和 `v_tbcolumn` 分别检查可见字段的 `标签名`、`列宽`、`显示` 和字段集；确认三字为 `840`、四字为 `1125`，中英文混合标签使用统一算法，维护页/查询页均无首屏截断，且更宽的业务列保持不变。再运行生成器 self-test、SQL 静态验证器和目标库只读验证，最后真实重开维护页和查询页确认首次显示完整列名。

## Lookup And Parameter-Substitution Field Contract

Symptom: changing a metadata field from a stable business label such as `物料编号` to a newly coined label makes lookup selection fail or leaves a dependent lookup without its required filter value.

Likely cause pattern: legacy client paths use a coupled runtime contract across `SYS_TbColumn.字段名`, `显示名`, `标签名`, `帮助`, `GLZD`, `LMark/RMark`, control `RID`, and helper SQL placeholders such as `@<physical-field-name>`. A value may be resolved by physical field name and RID in one step, while a lookup or result mapping consumes display/label metadata in another. The placeholder's exact delimiter can also be syntax for a legacy parser, including a trailing space that marks the end of the physical field name. Treating any of these names or delimiters as independent presentation text breaks that cross-path contract.

Safe fix pattern: do not rename any linked field or label merely to improve wording. First trace the active source path from helper launch through placeholder replacement and selected-value mapping. Snapshot every participating maintenance and query metadata row plus the helper SQL. For an authorized repair, update only the proven presentation values in a database/instance-guarded transaction with exact old-value and affected-row assertions; preserve physical `字段名`, `帮助`, `GLZD`, `LMark/RMark`, `RID`, and every `@<physical-field-name>` token including its parser-required terminator unless source evidence requires a coordinated migration. Keep a symmetric rollback artifact.

Verification: read back both base `SYS_TbColumn` rows and the derived `v_tbcolumn` rows; assert the physical field, mapping values, RID, and helper placeholder are unchanged; then reopen the form, select a value through the first lookup, and prove the dependent filtered lookup receives that selected value. A metadata readback alone does not prove the client-side selection chain.

## GLZD/LMark/RMark 关联显示契约

症状：帮助可打开但选择后名称/规格为空，生成 SQL 出现无效列、重复或悬空别名；或者为了优化文案而把“物料编号”改成“分析物料”，导致帮助选中、BOM 版本传参或表头/明细显示一并失效。

可能原因：iMES 业务表常只保存编号。当前 `GetCrossTable` 路径按源码条件扫描参与交叉表的 `GLZD` 非空行（现版本查询含 `PO<=2`），按 `LMark/RMark` 拼出关联 `LEFT JOIN`；`GetDataField` 在 `GLZD` 非空且 `切换=1` 时，用 `IOJCBDZD_BYZD` 代替业务编号投影显示值。另一组 `GLZD=''`、`RMark=<关联别名>` 的行则投影关联表的真实名称、规格或描述列。将这些行当成独立的展示字段，改了 `字段名/显示名/标签名/帮助`，混淆了 `LMark` 与 `RMark` 的方向，或因为业务物理表有相似列而直接替换关联字段，都会破坏同一份运行时 SQL 契约。

安全修复模式：先对目标可见名的维护页和查询页分别导出 `SYS_TbColumn` 与 `v_tbcolumn`，并对每一组关联画出“业务编号行 → `GLZD` 路由 → 关联表键/显示列 → 显示行”的映射。编号输入行保持真实业务 `字段名`、既有 `帮助` 和精确传参占位符；关联显示行保持关联表真实列名。`LMark` 只给被 JOIN 的关联表命名，`RMark` 只限定编号字段所在的业务侧来源；有别名时依照源码重放 `LEFT JOIN <关联表> AS LMark ON RMark.业务字段=LMark.关联键`，无别名时显式保存空字符串，不能写 `NULL`。物理表有相似的名称/规格列时，先以同版本有效单据、目标 `v_tbcolumn` 和生成 SQL 决定显示来源；已使用关联显示的页面不得仅为“看起来更直接”改读物理列。只改有明确证据的展示属性，并保留字段名、帮助、`GLZD/切换/LMark/RMark/RID` 及占位符；任何结构性变更均需同一事务的 preflight、精确旧值断言和对称 rollback。

可复用的别名证据形状是：编号输入字段以非空 `GLZD` 和 `LMark` 建立关联；关联表的名称、规格等显示字段以同一个 `RMark` 投影。表头和明细可并存多组关联，每组必须使用自身已验证的别名。这只是别名方向的参照，不是向任何其他表硬套字段名、别名或关联路由的理由。

验证：逐组断言 `GLZD` 行的 `IOJCBDZD_TABLE/VKEY/BYZD`、业务编号字段和别名组合有效；重放 `GetCrossTable` 的每条 JOIN，重放维护页及 `<单据名>查询` 的 `GetDataField` 投影并执行 `SELECT ... WHERE 1=2` 与其派生表包装。确认编号保存的是编号，显示列来自预期关联别名且没有重复别名；逐个执行帮助选值、被筛选的后续帮助/BOM 参数传递和新增/重开显示。若任一字段名、标签名、帮助、占位符或别名的消费者未能证明，停止修改而非猜测改名。

## Quick Reference

| Area | Typical symptom | First evidence to inspect |
|---|---|---|
| BDJB | Audit failure or unexpected output | Active rows, execution order, command text, result sets |
| PDA save/get | `INSERT EXEC` mismatch or transaction error | Full call chain and every emitted result set |
| 报工 | Available quantity or route calculation is wrong | Current and previous process rows, coefficients, approved quantities |
| 领料 | False missing-material error | Material source, production order, process, net issued quantity |
| 批号 | Missing batch or incorrect allocation | Batch-management flag, source chain, available and used quantity |
| MES-to-ERP sync | Drafts sync or routes duplicate/change | Effective status, stable row identifiers, protected downstream usage |

## BDJB And Result-Set Hygiene

BDJB-style audit engines commonly execute active rules by priority and order. Confirm the actual dispatcher and columns in the target schema.

If a caller uses `INSERT ... EXEC`, every reachable audit script must respect the captured result contract. Debug `SELECT *`, intermediate multi-column queries, or inconsistent success shapes can cause column-count errors even when the business rule itself is correct.

Safe pattern:

- remove unintended debug result sets;
- capture audit output internally when the public procedure promises one final response;
- return the documented success shape exactly once;
- raise or throw the original business failure instead of returning a false success;
- verify the complete nested call chain, not only the top-level procedure.

## Detail Complete But Header Not Backfilled

Symptom: approved reporting detail or process rows show completed quantities, while batch/work-order headers or completion flags remain null, zero, or stale.

Likely cause pattern: one BDJB rule updates detail without the restrictive predicate used by later header rules. The pipeline partially succeeds, creating contradictory states. Common restrictive predicates involve final/key-process markers, next-process fields, approval status, or a join that assumes one report per process.

Safe diagnosis:

1. Query the exact BDJB document type and order active audit rules by execution order.
2. Identify the first successful detail update and the first missing header update.
3. Evaluate every predicate of the missing rule against the exact document.
4. Trace only the first failed predicate upstream.
5. Check whether final-process reporting can be split across multiple approved documents; if so, require cumulative aggregation rather than current-document overwrite.
6. Check the cancel-audit rule for symmetric recalculation instead of unconditional zeroing.

Safe fix pattern: replace the unpopulated/incorrect discriminator with a confirmed business predicate, recalculate from all effective documents, update audit and cancel-audit together, and prepare a set-based historical repair with exact preview counts and rollback snapshots.

Verification: prove single-report, split-report, partial cancel-audit, final cancel-audit, batch-header aggregate, work-order aggregate, and derived status behavior.

## PDA Save And Get Interfaces

PDA save/get procedures often combine validation, audit execution, transaction handling, and a small result contract. Preserve that external contract while correcting internal logic.

For save procedures:

- distinguish transaction ownership from participation in a caller transaction;
- use a savepoint when recovery inside an existing transaction is valid;
- never unconditionally roll back a transaction owned by the caller;
- do not treat an outer transaction as a sandbox until the procedure's commit/rollback behavior is proven;
- prefer a disposable clone or confirmed test environment for write-path verification;
- confirm success emits only the expected column set and business failure remains visible.

For get procedures, verify returned field names and types because PDA clients can bind them positionally or by fixed names.

## Reportable Quantity

A common non-first-process model is:

```text
reportable quantity = previous-process available sets * current coefficient
                      - current qualified quantity
                      - current rejected quantity
```

When multiple previous processes feed the current process, the limiting source may be the minimum available set count. This is a reasoning pattern, not a universal formula: confirm route representation, unit conversion, coefficient meaning, approved-status filters, rework, outsourcing, inventory differences, and whether the UI applies a display cap that save/audit logic does not.

Do not copy a display-only cap into save or audit validation without proving the business contract requires the same semantics.

## Material-Issue Validation

For rules such as “issue material before reporting,” first classify the material source:

- produced by a confirmed previous process;
- issued externally against the production order and process;
- returned, supplemented, substituted, or manually managed by a customer-specific flow.

Previous-process output may not require a material-issue document. Externally issued material normally requires a confirmed match on production order, process, material/specification, and positive net available quantity. Verify whether the customer's rule checks document existence or quantity sufficiency.

## Batch Allocation And Update Chains

Enter batch allocation only for rows confirmed to require batch management. Trace the source before updating:

- external material issue commonly allocates from issued quantity minus already-used quantity;
- previous-process consumption commonly allocates from approved upstream output batches;
- customer-managed exclusions or manual materials must come from confirmed configuration, not hardcoded prefixes;
- synchronized output must preserve required batch identifiers for the downstream ERP contract.

Verify quantity conservation, deterministic allocation order, concurrency behavior, used-quantity backfill, and rollback safety.

## Transaction And Error Contracts

- Preserve the caller's transaction ownership.
- Use `XACT_STATE()` and `@@TRANCOUNT` to distinguish committable, doomed, and clean states.
- Use savepoints only when SQL Server permits rollback to them.
- Assume an unknown procedure can commit or roll back the caller transaction; inspect the full call chain before runtime testing.
- A rollback wrapper detects some violations but cannot recover data already committed by the procedure.
- Do not swallow a business error and return `OK`.
- Do not introduce extra result sets while adding diagnostics.
- Test the original failure and inspect transaction count before and after rollback.

## Legacy Generic Base-Form Naming

Symptom: a new basic-data table exists and has workspace permission, but the generic iMES form opens with no fields or saves/deletes against the wrong object.

Likely cause pattern: the old `AutoOpen` route uses `IOJCBDZD_BTYPE=1` and `UForm1`. `UForm1` derives the physical table name by taking the part before the first underscore in the primary metadata field (`字段名`), while `SYS_TbColumn.表名` and `IOJCBDZD_MC` use the visible business name. A V2 name such as `INSP_ITEM` therefore conflicts with the legacy prefix inference when its key is `INSP_ITEM_ID`.

Safe fix pattern: for a database-only generic base form, confirm the active client route, use a legacy-compatible physical table name without underscores (for example `INSPITEM`) and prefix every field with that exact table name (`INSPITEM_ID`, `INSPITEM_BH`, ...). Register `IOJCBDZD` with `BTYPE=1`, point `IOJCBDZD_TABLE`/`Vkey`/`BYZD` at real columns, register `SYS_TbColumn.表名` under the visible form name, and expose a role-visible `SYSWSPACE` leaf. Do not add `IOBDZD`, `IOYYGX`, `IOPOPDLG`, or `BDJB` rows unless this is a bill or has a proven relation/lifecycle consumer.

Verification: read back `IOJCBDZD`, `v_tbcolumn`, and the workspace hierarchy; assert that the primary field exists, its prefix equals the physical table name, every metadata field exists in `sys.columns`, `GetDataField`-equivalent SELECTs execute, and `AutoOpen` would choose the `BTYPE=1` branch. Test a minimal insert/update/delete in a transaction and roll it back.

## Metadata Base Table Versus Derived View

Symptom: a metadata migration fails with an invalid-column error, or a script tries to persist fields that appear in `v_tbcolumn` but not in `SYS_TbColumn`.

Likely cause pattern: the derived runtime view was treated as the physical metadata schema. Deployments commonly expose `IOJCBDZD_TABLE`, `IOJCBDZD_VKEY`, `IOJCBDZD_BYZD`, and `IOJCBDZD_FILTER` from `IOJCBDZD` while `v_tbcolumn` joins or derives them; they are not evidence that the same-named columns exist in `SYS_TbColumn`.

Safe fix pattern: before designing metadata SQL, query `sys.columns` for `IOJCBDZD`, `SYS_TbColumn`, and the definition/dependencies of `v_tbcolumn`. Write only columns confirmed on the target base table, and read derived fields only through the view or its proven source. If a proposed column is absent, stop instead of adding a compatibility column or silently changing the statement.

Verification: assert the insert/update column list against `sys.columns`, read back both base rows and `v_tbcolumn`, confirm every runtime field maps to a real business column, and execute the client-equivalent select. Keep the metadata migration fail-closed and rollbackable.

## BTYPE=1 Basic Form Contract

Symptom: a simple lookup form has a physical table and permissions but the generic form has no fields, targets the wrong table, or was given unnecessary dynamic-bill metadata.

Likely cause pattern: `IOJCBDZD_BTYPE=1` was mistaken for an `IOBDZD` bill. `UForm1` is a single-table route: it resolves the visible form name, reads one `SYS_TbColumn` field set, and derives the physical table from the confirmed primary-field naming convention. It does not require a `<visible name>查询` field set, `IOBDZD`, `IOYYGX`, `IOPOPDLG`, or `BDJB` unless a separate source-proven consumer proves one is needed.

Safe fix pattern: classify the object as one complete basic-data row, choose a legacy-compatible physical name/prefix only after reading the active `UForm1` source, register one `IOJCBDZD` row with real `TABLE/VKEY/BYZD`, register visible-name `SYS_TbColumn` rows, and add the role-visible workspace hierarchy and operation leaves. Do not manufacture a bill lifecycle or query metadata to satisfy a dynamic-bill checklist.

Verification: prove the `AutoOpen` `BTYPE=1` branch, assert `TABLE/VKEY/BYZD` and the primary field exist, map every metadata field to `sys.columns`, run client-equivalent select plus transactional insert/update/delete, verify role visibility, and confirm no test residue.

## Audit Anchor Layout And Negative Constraint Tests

Symptom: a form is technically non-overlapping but the audit control appears isolated, or a duplicate-code test poisons the surrounding transaction and produces a misleading failure.

Likely cause pattern: `SHBZ` was treated as an ordinary field and only its input rectangle was checked; separately, a unique-constraint error was raised under `XACT_ABORT ON` and the test then attempted to continue or roll back to an invalid savepoint.

Safe fix pattern: derive `headerLowerBound` from the reference `SHBZ` bottom, preserve fixed `ZDR/SHR/ZY/SHBZ` rectangles, size `SHBZ` from the same-version reference/runtime minimum including its label footprint, and lay out only non-fixed fields within the measured canvas and natural gaps. For duplicate-key tests use an isolated transaction with `XACT_ABORT OFF`, `SAVE TRANSACTION`, explicit 2601/2627 handling, rollback to the savepoint, and final rollback.

Verification: assert fixed-anchor equality, audit right edge/canvas bounds, label-inclusive spacing, natural field order, all variable-field bottoms above the audit lower bound, `XACT_STATE()`/`@@TRANCOUNT` after the expected error, and zero test rows after rollback. Keep query-page coordinates separate and request a real client reopen for visual confirmation.

## UForm2 Mistaken For A Dynamic Bill

Symptom: a requested header/detail form opens as a left directory plus one right-side grid, or the header is maintained under a second visible metadata name; it lacks one document number/save unit or cannot participate correctly in audit and document relations.

Likely cause pattern: `IOJCBDZD_BTYPE=2/UForm2` was called a generic master-detail bill merely because it touches two physical tables. Its real contract is a category tree (`LBTABLE/LBNAME`) filtering a separate right-side dataset (`TABLE/MC`) through `<DETAIL>_LBBH`. It uses two metadata names and is not the `IOBDZD` bill engine.

Safe fix pattern: classify by runtime semantics before DDL. Keep `BTYPE=2` only when the intended UI is genuinely a category/directory tree with a filtered dataset. When the request needs one header with line rows, a shared `_SJDH`, unified save/delete, audit/cancel-audit, references, or upstream/downstream links, create an `IOBDZD` bill. Register one visible `IOBDZD_MC`, its header/detail tables and keys, a unique nonempty `MARK`, `SYS_TbColumn.PO=1/2/3`, active `BDJB`, and form plus operation permissions. Keep independent lookup objects as their own `BTYPE=1` forms.

Verification: prove `AutoOpen` resolves the visible name through `IOBDZD` before `IOJCBDZD`; `PO=1` fields map to the header and each `PO>1` first field prefix maps to the intended detail table; every detail page exposes `FID`, `单号`, `分录号` where expected, and a real `关键字段`; run transactional header/detail CRUD plus audit/cancel-audit and confirm rollback leaves no test rows.

## Existing BTYPE=2/UForm2 Must Validate Hard-Coded Tree Columns

症状：分类树表单能查到 `IOJCBDZD` 路由和 `v_tbcolumn` 行，但打开后字段名、页签表面为空，或右侧网格没有数据。

可能原因：`UForm2` 在动态元数据加载前直接拼接树查询和明细筛选，实际读取 `<MASTER>_PBH/<MASTER>_BH/<MASTER>_MC` 以及 `<DETAIL>_ID/<DETAIL>_BH/<DETAIL>_LBBH`。物理表使用 `*_CODE/*_NAME`，或把 `VKEY/BYZD` 当成硬字段别名时，路由看似完整但初始化已经在左树阶段失败。

安全修复模式：先从活动源码记录硬字段和两条真实 SQL，再核对 `sys.columns`、`IOJCBDZD`、`LBNAME`/`MC` 两套元数据。发现命名契约冲突时停止建表或元数据写入；只有在明确审查兼容范围后，才能做成套物理列/索引/元数据/回滚变更，不能用标签、帮助或额外元数据掩盖缺列。

验证：执行树根查询和选中节点明细查询，分别断言字段存在、筛选值来源正确、`GetDataField`/`GetCrossTable` 非空；树字段只能闭合到 `LBNAME`，右侧字段只能闭合到 `MC`。最后再检查工作区和角色，不能把权限结果当成运行时硬字段验证。

## New Table Naming Must Fail Closed Against Client Runtime Contracts

症状：建表脚本执行成功，但同版本客户端仍报列不存在、空页签或空字段；或者新表与已存在的客户端命名契约冲突。

可能原因：DDL 只检查了“表名不存在”，没有把源码硬编码列名、路由、元数据和生成 SQL 纳入对象冲突判断；于是 `*_CODE/*_NAME` 被错误地当成 `<MASTER>_BH/<MASTER>_MC` 等价物，或在冲突状态下直接创建了物理表。

安全修复模式：把运行时硬字段清单作为建表前 preflight 的必需输入，逐列比对源码、同模块现有表、路由和约束。任何缺列、同义替代、表名/字段名冲突或 SQL 不可执行都返回 `review-blocked`，不生成或执行 `forward.sql`；修复必须同时说明兼容列、数据迁移、元数据和回滚范围。

验证：在 DDL 前输出冲突清单和停止原因；在允许的测试环境中再验证 exact `sys.columns`、树根 SQL、选中节点 SQL、两套元数据闭合和工作区权限。没有这些结果，不能以“表已创建”或“元数据有记录”宣布完成。

## MES-To-ERP Synchronization

Common invariants to confirm across customers:

- synchronize only records whose status means formally effective in that deployment;
- distinguish not-required, pending, successful, and failed synchronization states from actual schema values;
- match existing route rows through stable identifiers when available instead of regenerating sequence numbers;
- protect rows already referenced by reporting, station entry, dispatch, material issue, or downstream ERP records;
- make deletion and route replacement conditional on confirmed absence of dependent business data.

## Custom Report SQL Wrapped By Designer

Symptom: a custom-report query works when run directly but fails after saving, often with a syntax error near `ORDER BY`, a CTE, or a trailing statement.

Likely cause: the report designer executes the saved text as a derived table, for example `SELECT * FROM (<saved SQL>) a WHERE 1=1`, and may append outer filters. A complete top-level query or statement batch is therefore not a valid inner query.

Safe fix pattern: inspect the runner and emit exactly one inner `SELECT`. Keep joins, predicates, aggregation, and stable column aliases inside it. Remove the inner `ORDER BY`, trailing semicolon, CTE, variable declarations, temp-table statements, and extra result sets. Use confirmed target columns; do not silently normalize a user-supplied field name that is absent from the target schema.

Verification: execute the exact saved text both directly and inside the runner's wrapper shape. Confirm the wrapped query returns one result set with stable column names and that any outer `WHERE 1=1` or generated filter can be appended without syntax errors.


## BTYPE=1 Metadata Marker Accidentally Emits `FF_BS`

Symptom: a simple `IOJCBDZD_BTYPE=1`/`UForm1` form fails during data loading with `Invalid column name 'FF_BS'`, even though the business table has no `FF_BS` column.

Likely cause pattern: the active `GetDataField` source reads `SYS_TbColumn.标识` from `v_tbcolumn` and tests only whether the returned string is non-empty. A value such as the string `0` in an `nvarchar` metadata column is therefore true, and the client emits `sum(case FF_BS when '<标识>' then <字段> else 0 end)`. This is a metadata-to-SQL generation defect, not evidence that the business table needs an `FF_BS` column.

Safe diagnosis and fix pattern:

1. Read the exact `GetDataField` branch and one working same-route form. Confirm whether `标识` is the switch for the `FF_BS` aggregate and confirm its SQL type.
2. Inspect the target `SYS_TbColumn` rows and the derived `v_tbcolumn` rows for the affected visible form. Keep `标识` `NULL`/empty for ordinary `BTYPE=1` fields unless the active source and a working instance prove a real `FF_BS` producer/consumer.
3. Treat `0` as a value, not as a universal “off” sentinel, when the client checks string length. Do not add a fake `FF_BS` business column to hide the generated SQL error.
4. If an existing authorized test database contains the bad marker, make a guarded, transactional, row-count-asserted metadata repair and preserve a rollback/forward artifact. Update the original deployment script so a rerun cannot recreate the defect.

Verification: assert the target identity; assert all ordinary-form markers are null/blank; reconstruct the runtime field list using the same `v_tbcolumn`/`字段名1` shape as `GetDataField(..., true)` and fail if the generated text contains `FF_BS`; execute the resulting client-equivalent `SELECT` against the physical table. Test initial load and search separately because `UForm1` may use a different, hard-coded search predicate. If search references an absent column such as a legacy `码表编号`, report the client-source defect separately and do not change the database schema without proof that the column is part of the business contract.

## UForm1 Initial Load Versus Search Predicate

Symptom: the basic-data grid opens after a metadata repair, but pressing search fails with an invalid column name.

Likely cause pattern: `Refresh()` builds its projection from `GetDataField` and the route table, while the search handler builds a separate predicate. Legacy `UForm1` code may hard-code `码表编号` even when the route's physical key is a different confirmed field such as `<prefix>_CODE`.

Safe fix pattern: prove both SQL paths from source. Keep the database repair limited to confirmed metadata and physical schema; do not add a compatibility column merely to satisfy an unproven client literal. Either correct the client to use the route's confirmed key/search field or explicitly record search as remaining client scope.

Verification: run the initial-load projection and the actual search-shaped SQL independently, check every referenced identifier against `sys.columns`, and report separate pass/fail results.

## BTYPE=1/UForm1 顺序必须从 0 开始

症状：单表基础资料的字段显示顺序错乱，或编译后维护页出现空白、错位、不能正常关闭。

可能原因：`UForm1` 的 `LoadData()` 按查询结果从 `0` 创建 FlexGrid 列，`LoadGridSet()` 和新增/修改路径又直接把 `SYS_TbColumn.顺序` 当作列下标。单表若使用 `1..n`，最后一个序号会访问不存在的第 `n` 列；旧客户端可能捕获该异常后只留下半初始化页面。某些 `IOJCBDZD_BYZD` 展开出的额外查询列可能暂时掩盖越界，但不改变单表契约。

安全修复模式：只对已确认的 `IOJCBDZD_BTYPE=1/UForm1` 表单，按稳定字段顺序在每个 `(表名, PO)` 组重排为 `0..n-1`，隐藏 identity 字段通常占 `0`；预检保存 `RID+字段名+旧顺序`，前向 SQL 只更新精确旧值并断言影响行数，附带对称回滚。不要把该规则套用到 `IOBDZD/PageRows` 动态单据，后者按其独立契约通常使用 `1..n`。

验证：单表每组必须满足 `MIN(顺序)=0`、`MAX(顺序)=COUNT(*)-1`、`COUNT(DISTINCT 顺序)=COUNT(*)`，且不存在 NULL、负数或跳号；同时用 `SYS_TbColumn`/`v_tbcolumn` 重建客户端字段列表和首屏 SELECT，最后重新打开表单并验证新增、编辑、删除。

## Common Mistakes

- Treating example IMES object names as guaranteed schema.
- Reusing another customer's database environment because the product is the same.
- Fixing the top-level procedure without inspecting nested BDJB output.
- Confusing UI display limits with save/audit business formulas.
- Requiring issue documents for material produced by a previous process.
- Allocating batches without proving the source and remaining quantity.
- Testing a save procedure without rollback or without checking transaction ownership.


## ER Contract Drift Invalidation

Symptom: an updated ER diagram adds a field, removes one, or changes a field name while an older dynamic-bill deployment script is reused; the form opens partially, query metadata is stale, or SQL artifacts fail only at runtime.

Likely cause: the old contract was treated as a cosmetic layout change. Dynamic bills duplicate the field set across physical schema, maintenance metadata, the separate `<MC>查询` dataset, lookup mappings, CRUD tests, and verification.

Safe fix pattern: generate a new `contract.json`, compare it with the previous contract, and review added/removed/same-label renamed fields as one change. Rebuild the affected physical column, `SYS_TbColumn` rows, query dataset, rollback, and tests. Run the parse-only artifact validator before database execution; never silently reuse the old forward script.

Verification: assert the expected field set per table/PO, no dangling metadata fields, complete RID range/uniqueness, CRUD column/value parity, and a non-empty executable query field set.

## Audit Anchor Is A Layout Boundary

Symptom: the audit control looks isolated, overlaps the detail tab, or ordinary fields render below it even though their input rectangles appear non-overlapping.

Likely cause: the audit control is a fixed label-plus-input anchor, while the layout check considered only the input rectangle or copied coordinates without its label footprint.

Safe fix pattern: copy the audit anchor from a working same-version bill, validate its label and input width/height together, and treat the anchor's bottom edge plus the client tab gap as the header lower bound. Place ordinary fields above that boundary and exclude only documented hidden runtime anchors from visible-layout checks.

Verification: check the exact audit field coordinates/control code, positive dimensions, label-inclusive non-overlap, and every visible header field's bottom edge against the computed boundary.

## Lookup Contract Needs Code/Display/Help Closure

Symptom: an asset type field shows a label but cannot open help, saves display text instead of a code, or returns no translated value.

Likely cause: only `SYS_TbColumn` text was configured; the `IOJCBDZD` BTYPE/table/key/display route or help key is absent, duplicated, or points at a different physical column.

Safe fix pattern: prove the real code column and data type, then verify the complete `IOJCBDZD` route and the matching `GLZD`/`帮助` values in both maintenance and query metadata. Do not infer the route from the Chinese caption.

Verification: test key-to-display and display-to-key round trips and execute the generated lookup SQL against the confirmed table.
### Metadata defaults: ordinary controls and role visibility

Symptom: a newly generated form contains nullable or inconsistent `控件`/role flags, so the header can fail to initialize or the new form is invisible to the current role.

Likely cause pattern: the generator copied only a few reference values and treated detail Grid metadata as if it used the header control factory.

Safe fix pattern: for newly inserted dynamic `SYS_TbColumn` rows, use `类型='D'` for physical `date`/`datetime`/`datetime2` fields and `类型='S'` for all others; ordinary fields use `控件='E'`, while `*_PJLX`/voucher-type fields use `控件='S'`. Do not derive `N`, `C`, `EM`, or radio values from SQL type or labels. For every role column that actually exists in the target schema, initialize newly inserted form/metadata rows to `1` by default, while preserving existing permissions and never inventing role columns.

Verification: read `sys.columns` to enumerate role columns; assert date metadata rows have `类型='D'`, other rows have `类型='S'`, ordinary controls are `E`, and `*_PJLX` controls are `S`; all actual role columns are `1`, and standard `PO>1` detail behavior is verified from Grid metadata (`帮助`/`管道字符`/`只读`/`列宽`) rather than from `控件` or inferred type.

### New Header/Detail Bills Require the Standard Button Set

Symptom: a new header/detail bill opens, but users cannot show related bills, preserve column widths, configure columns, import Excel rows, view notes/attachments, or copy detail rows.

Likely cause: the bill was registered in `IOBDZD`/`SYSWSPACE` without the standard `sysmenu` rows, or the rows were added with guessed menu parameters. These buttons are resolved from `sysmenu_bdmc` and the active `Bill.cpp` menu map; `SYSWSPACE_BTN` is not a substitute.

Safe fix pattern: every new `IOBDZD` header/detail bill must add exactly one row for each of `显示关联单据`、`保存列宽`、`列配置`、`从EXCEL导入`、`说明`、`附件`、`复制分录`, using the Sales Order reference: `显示关联单据=(topfloor=0,submenu=0,xh=3,icon=40,pmenu=' ',trimenu=0,uid=' ')`; `保存列宽=(0,1,3,0,'其他',1,' ')`; `列配置=(0,1,4,0,'其他',0,' ')`; `从EXCEL导入=(0,1,5,0,'其他',0,' ')`; `说明=(1,0,3,24,' ',0,' ')`; `附件=(0,0,3,24,' ',0,' ')`; `复制分录=(1,0,3,40,' ',0,' ')`. The tuple order is `topfloor,submenu,xh,icon,pmenu,trimenu,uid`; `sysmenu_bdmc` is the new bill name. The `' '` values are the literal single spaces stored by the Sales Order rows. Add the rows in the same transaction as the bill contract and preserve any unrelated custom menu rows.

Verification: read the target `sysmenu` schema and assert one row per required button, no duplicate required names, exact `topfloor/submenu/xh/icon/pmenu/trimenu/uid` values, and correct attachment to the new `sysmenu_bdmc`. Reopen the bill and verify both header and detail toolbars expose the expected commands; database rows alone do not prove the toolbar rendered.

## Metadata Role Columns Must Be Distinguished From Form Flags

Symptom: a newly deployed form appears with incorrect `显示/必填/只读/切换` behavior, or verification reports role authorization while the generated `SYS_TbColumn` rows still have unexpected standard flags.

Likely cause: `SYS_TbColumn` contains ordinary metadata `bit` columns before `RID` (`主键`, `显示`, `新增`, `更新`, `关键字段`, and similar) and role permission columns after `RID`; selecting every `bit` column after `nID` or from a remembered ordinal updates form flags as if they were roles. Some deployments also have dropped-column gaps, so a contiguous ordinal range is unsafe.

Safe fix pattern: inspect `sys.columns` for the target `SYS_TbColumn`; use the confirmed `RID` column as the boundary and treat only `bit` columns with `column_id > RID.column_id` as role columns. Handle `admin` explicitly according to its actual type and do not invent missing role columns. For `SYSWSPACE`, inspect the actual `admin` column and treat only `bit` columns after that role boundary as role columns; keep `MX/JDBZ/QCYWBZ/BTN` as workspace flags. Update only newly inserted rows inside the deployment transaction.

Verification: print the resolved role-column names and ordinals before writing, assert standard metadata flags remain equal to their inserted values, assert every actual role column on new rows is `1`, and verify `admin` separately with type-aware conversion. Reject the deployment if `RID` or the workspace role boundary is absent.

## Static INSERT Arity Is A Deployment Gate

Symptom: the SQL script executes but `控件`, `RID`, `admin`, or a trailing permission value lands in the wrong column, or SQL Server reports a column/value count error only after a large generated statement is run.

Likely cause: wide legacy metadata tables have many nullable columns and an identity `nID`; a hand-generated tuple can contain one extra value or accidentally include the identity column. A one-position shift is especially damaging because the statement may remain type-compatible.

Safe fix pattern: exclude `SYS_TbColumn.nID` from the insert column list, keep the exact target column list beside the generator, and count every `SYS_TbColumn` tuple and every `SYSWSPACE` tuple with a parser that understands quoted strings. Require the expected arity before connecting to SQL Server; do not rely on visual alignment.

Verification: assert tuple counts, per-tuple arity, unique `RID` values, generated `控件` all equal `E`, explicit `主键`/`关键字段` cardinality, `标识 IS NULL`, and `admin=1`. Run the same checks again against the inserted rows.

## Workspace Number Conflicts Require A Migration Decision

Symptom: a new module cannot be opened even though its tables and metadata are valid, or deployment would overwrite an existing module's menu/permission nodes.

Likely cause: `SYSWSPACE_BH` is a shared namespace. A desired parent/leaf number may already belong to an older module whose label differs from the new ER diagram; copying the number silently creates duplicate or conflicting navigation and permissions.

Safe fix pattern: perform a read-only subtree query before metadata writes. If any parent, leaf, or operation number exists, stop and ask whether to rename/reuse the existing subtree or allocate a new number; do not delete or overwrite existing workspace rows as part of a new-form deployment.

Verification: assert the complete parent/child/operation hierarchy is unique, parent references exist, labels match the approved mapping, and every newly inserted node has all actual role columns authorized. Treat a successful table/metadata insert as incomplete until this namespace decision is recorded.

## ER Diagram Revisions Invalidate Generated Contracts

Symptom: a form generated from a previous ER version has stale fields, dangling lookup metadata, or a module title/relationship that no longer matches the current diagram.

Likely cause: ER revisions are contract changes, not only documentation changes. Physical columns, lookup routes, `SYS_TbColumn`, workspace labels, tests, and rollback scripts can all retain old names or module wording.

Safe fix pattern: parse the current ER artifact first, record its exact path and timestamp, compare the expected table/field set with the deployment contract, and regenerate the affected artifacts. Keep out-of-scope dynamic bills separate; do not infer that a newly drawn bill is safe to deploy without its full `IOBDZD`/`BDJB` contract.

Verification: assert every deployed physical field is present in the current diagram, no expected field is omitted, all `GLZD`/`帮助` routes close against current `IOJCBDZD`, and the README states which ER entities were intentionally deferred.

## Generated SQL Must Compile Under The Actual sqlcmd Session

Symptom: a generated deployment script fails before changing data with error 1934 around `FOR XML ... .value(...)`, error 102 near `+` in `sp_executesql`, or error 156 near a seemingly harmless result alias such as `RowCount`.

Likely cause: the script was only statically inspected or executed under a different SSMS session. XML data-type methods require compatible SET options, `sp_executesql` expects a variable/expression that has already been evaluated rather than an inline concatenated command in this legacy form, and generated aliases can collide with reserved keywords.

Safe fix pattern:

1. Put `SET ANSI_NULLS ON; SET QUOTED_IDENTIFIER ON;` before any `FOR XML ... .value(...)` expression, and preserve the same session assumptions in forward and verification scripts.
2. Build dynamic SQL into a variable (`SET @sql = ...`) and execute `sp_executesql @sql`; do not pass a concatenation expression directly as the procedure argument.
3. Bracket generated aliases that may be reserved words, or choose an unambiguous alias such as `[RowCount]`.
4. Keep these fixes in the generated artifact and generator/template, not only in the one failing run.

Verification: run every preflight, forward, verification, and test script through the same `sqlcmd -b` path used for deployment, capture the exit code, and require a clean compile/execution before claiming the migration is safe. After a failed transactional forward, assert that no partial tables, metadata, or workspace rows remain.

## Visible Form Names Must Be Unique Across IOJCBDZD And SYS_TbColumn

Symptom: a new physical table and metadata are valid, but the client opens the old form, reports ambiguous data, or resolves the wrong field set.

Likely cause: `IOJCBDZD_MC` and `SYS_TbColumn.表名` are visible-name namespaces. An existing legacy form can already own a label such as a generic “车间” while pointing to a different physical table. Registering a second route with the same visible name is not a safe replacement.

Safe fix pattern: read the existing `IOJCBDZD` route, `SYS_TbColumn` rows, business table, and menu/workspace usage before writing. Preserve an active legacy route unless explicit migration authorization exists. For a new module, use an approved non-conflicting visible-name mapping (for example, an asset-specific prefix), keep physical ER table names unchanged, and use the same mapping in metadata, help labels, workspace leaves, operation names, verification, CRUD, and rollback scripts.

Verification: assert one-to-one visible-name ownership for every new route, confirm the visible name maps to the intended `TABLE/VKEY`, and confirm the old route remains unchanged. Do not treat successful insertion of six physical tables as proof that the form route is unambiguous.


## BTYPE=1 单表重复开发应走契约脚手架

症状：单表基础资料字段已经确认，但每次仍重复手写建表、`IOJCBDZD`、`SYS_TbColumn`、`SYSWSPACE`、验证和 CRUD SQL，耗时长且容易漏写 `nID`、权限列、父节点或回滚条件。

可能原因：没有把“字段契约”和三阶段门禁分离，模型在每个表单上重新发现相同的 IMES 元数据约定。

安全修复模式：将目标库、实例、物理表、可见名称、BTYPE=1 路由、工作区和字段属性收敛为一份 JSON 契约；用 `scripts/scaffold_basic_form.py` 一次生成 preflight、forward、verification、隔离 CRUD、rollback-preflight、rollback 和 README。生成器只写文件不连接数据库；preflight 冲突、字段前缀不一致、唯一键缺失、父节点缺失或权限边界未知时拒绝生成/部署。新生成元数据控件统一为 `E`，不按 bit/日期/标签推导特殊控件，`标识=NULL`，`SYS_TbColumn.nID` 不写入。

验证：同一份契约生成的脚本通过 Python 生成器烟测；使用同一 `sqlcmd -b -f 65001` 路径依次执行 preflight、forward、verification、CRUD；验证客户端等价首屏查询不含 `FF_BS`，角色列全部授权，父子工作区完整，CRUD 测试零残留。若对象需要表头/明细、审核/撤审、上下游或库存回写，停止快速通道并改用动态单据契约。

## 复杂表单应固化为四阶段契约包

症状：模板、记录或审核表头/表体单据重复手工准备表、IOBDZD、维护页、查询页、审核布局、BDJB、SYSWSPACE 和测试 SQL，容易漏掉查询页、审核底边、控件默认值或权限列。

可能原因：把 ER 图当成完整运行契约，或把复杂表单误走 BTYPE=1 单表路径；ER 图无法证明真实类型、主键策略、IOBDZD 路由、同版本审核坐标和生命周期规则。

安全修复模式：先读 `references/complex-form-fast-path.md`，用 `scripts/scaffold_complex_form.py` 从 ER SVG 生成 `review-blocked` 契约包；回填只读 preflight/reference-evidence 结果后，再将表头/表体、外键、维护/查询字段集、审核底边、BDJB rows 和 workspace rows 收敛到同一份 `contract.json`。只有契约完整时生成 forward；新生成元数据中物理 `date`/`datetime`/`datetime2` 字段使用 `类型=D`，其他字段为 `S`；普通字段 `控件=E`，`*_PJLX`/凭证类型字段 `控件=S`，不按 bit、数值精度或标签推导其他值，`SYS_TbColumn.标识` 保持 NULL，不插入 `nID`，动态角色列及 `SYSWSPACE.admin` 后权限列默认授权。审核坐标和宽度必须来自同版本有效单据，不得复制未经核实的坐标。

验证：Python self-test 和 skill validator 通过；ER 生成包的 forward/verification/crud/rollback 明确阻断；完整契约生成十个阶段文件，维护页/查询页字段集闭合、审核底边和控件规则有断言、角色权限使用动态发现、CRUD 事务零残留。数据库部署仍需在确认的测试环境执行并记录实际结果，复杂表单的 MFC/C++/RC 资源另行处理。

## 复杂表单 schema-draft 误执行

症状：四阶段包的“审阅草图”被批量执行后，数据库出现只有物理表、没有外键/IOBDZD/SYS_TbColumn/BDJB/SYSWSPACE 的半成品。

可能原因：`schema-draft.sql` 虽标注 review-only，却包含可执行 `CREATE TABLE`；按目录批量运行 `.sql` 时把草图误当部署脚本。

安全修复模式：生成器将 `schema-draft.sql` 输出为注释式 DDL 草图，唯一可执行物理 DDL 只能来自带数据库/实例门禁和事务的 `forward.sql`；README 明确禁止批量执行目录内 SQL。

验证：静态断言 schema-draft 中不存在未注释的 `CREATE TABLE`、`ALTER TABLE` 或 `SET`；仅对 `preflight/reference-evidence/verification` 做只读执行，对 `forward/crud/rollback` 逐个按授权门禁执行。

## 存量元数据修复必须区分旧值和目标值

症状：修复脚本执行成功但界面仍保持原来的控件或布局，或脚本在已经正确的状态下才返回成功。

可能原因：`UPDATE` 的谓词误用了期望的新值（例如 `控件='S'`），而不是部署前实际存在的旧值（例如 `控件='E'`）；脚本因此更新 0 行或把“已正确”误报为“已修复”。

安全修复模式：在 preflight 和事务内锁定目标行，断言完整的旧值快照；forward 只允许 `旧值 -> 目标值` 的精确更新并断言影响行数为 1；更新后立即读取目标值。rollback 对称地断言目标值后恢复旧值，并在存在业务数据时拒绝回滚。

验证：同时检查维护页和查询页的目标值、固定映射/坐标/RID 未被误改；脚本在旧值已变化或行数不唯一时 fail-closed。将同版本工作单据的字段作为目标值证据，不能仅凭字段类型或标签推导控件。

## 缺少布局锚点字段导致 InitForm 后空指针崩溃

症状：iMES 客户端打开动态单据（如点检记录单）维护页或查询页时弹出 `初始化表单出错:00000000`（部分版本表现为访问冲突 `0xC0000005`），报错发生在 `InitForm()` 成功返回之后、表单控件初始化阶段，单据无法打开。

可能原因：`CBill::InitForm` 按 `v_tbcolumn` 中 `PO=1` 的表头字段名后缀填充 `billdata.iXXX` 控件 ID；当物理表头或 `SYS_TbColumn` 缺少 `_PJLX`（凭证类型）、`_YWRQ`（制单日期）、`_ZY`（摘要）等运行锚点字段时，这些 int 保持 0。`OnInitialUpdate`/`OnSize` 随后 `GetDlgItem(0)` 返回 NULL 并解引用，触发 SEH 异常；`/EHa` 编译下 `catch(...)` 捕获后 `GetLastError()` 恒为 0，对话框因此显示 `00000000`。查询页报同样错误时，根因常是查询页 `PO=1` 元数据缺少同名锚点。

安全修复模式：先定位报错代码段（客户端源码 `InitForm` 之后直接 `GetDlgItem(billdata.iXXX)` 的锚点、`OnSize` 布局锚点、保存路径 `GetDlgItemText(iYWRQ,...)`），列出全部被直接使用的锚点后缀；再选取同库同版本可正常打开、布局和生命周期等价的有效单据作为参照，镜像其经 `sys.columns` 和元数据确认的物理列类型/默认值与维护页/查询页元数据（控件/类型/坐标/`切换`/`GLZD`/`LMark`/必填/角色授权）。新行按 `PO,顺序` 排在既有最大顺序之后，`RID=MAX(RID)+1` 起连续分配，`标识=NULL`，不写入 `SYS_TbColumn.nID`（IDENTITY）；整个变更放进带数据库/实例门禁、事务与行数断言的 forward 脚本，并提供对称 rollback。只做数据库层修复，不向客户端源码补空指针判断。

验证：preflight 对照物理列、维护页与查询页 `PO=1` 行数、`MAX(RID)` 与参照证据；部署后模拟 `InitForm` 读取 `v_tbcolumn` 并按后缀匹配 `billdata.iXXX`，断言锚点字段全部存在、控件非空、坐标/类型/`GLZD` 完整、`RID` 唯一且顺序连续、参照路由未变；再做隔离事务 CRUD 写入/读取锚点字段并回滚，断言零残留；最后请用户真实打开维护页与查询页确认不再报错，并做一次新增/保存冒烟。

## 查询页字段集必须单一 PO 且显示名/标签名唯一

症状：动态单据维护页能打开，但查询页（`<IOBDZD_MC>查询`）列错位、表头重名或打开查询时报错；或查询页 `SYS_TbColumn` 中同一 `PO` 分组内出现重复 `顺序`、`显示名`、`标签名`，或混入 `表头=1` 的维护页锚点行。

可能原因：查询页被当作维护页的 `PO=1/2/...` 复制，保留了维护页的表头锚点标志并把表头/明细字段交错进不同 `PO`，导致 `顺序` 在单一可见名下重复。`CBill`/`LoadGridSet` 直接以 `顺序` 作为网格列索引，重复 `顺序` 会让多列叠到同一列；查询结果列别名来自 `显示名`，`显示名` 或 `标签名` 重复会让派生表/包装查询无法解析。

安全修复模式：把查询页视为**单一 `PO=1` 的扁平字段集**——`表头` 一律置 `0`（查询页是网格列，不是维护页的表头锚点行），`顺序` 自 `1..n` 连续且唯一，`显示名` 与 `标签名` 分别唯一。表头/明细同名同义字段按查询业务粒度去重（如 `ID→HID/FID`、`单号→单号/明细单号`、`备注→备注/行备注`），不要原样复制全部维护元数据。对既有查询页先做 `GROUP BY 顺序 // 显示名 // 标签名` 重复检查与 `MAX(PO)`/`SUM(表头=1)` 检查，再在事务内统一重排 `顺序`、清 `表头`、去重显示名/标签名，并附带 `rollback` 与只读预检。

验证：模拟客户端 `LoadGridSet` 读取 `v_tbcolumn`（`顺序` 为列索引）确认无重复；断言查询页单一 `PO`、`表头=0`、`顺序` 1..n 连续、`显示名` 与 `标签名` 各自唯一；用查询字段集与原单据 `GetCrossTable` 拼出的 `SELECT ... WHERE 1=2` 及派生表包装执行通过；最后真实重开查询页确认列序正确。

## 查询页排序必须保留单号和日期字段

症状：维护页可以打开，但查询页提示“单号无效”、无法稳定排序，或查询结果在翻页/刷新后顺序漂移。

可能原因：查询字段去重时把表头/表体的单号或日期一并删掉，或者只保留了显示列而没有保留客户端排序锚点。`CBill` 查询路径需要从独立的 `<IOBDZD_MC>查询` 字段集读取单号和日期；仅有维护页 `SYS_TbColumn` 行不能替代查询页字段。

安全修复模式：把查询页作为单一 `PO=1` 网格字段集，至少保留且唯一映射 `<HEADER>_SJDH`（单号）和 `<HEADER>_YWRQ`（日期）两个业务字段；两列必须 `显示=1`、`必填=1`，并按稳定的 `顺序` 排在查询字段集内，作为默认排序的第一、第二键（日期方向按业务确认）。如果明细也有 `_SJDH`，只能通过明确别名保留一列单号，不能让同名别名覆盖表头单号。不要用物理表中“有列”证明查询页已满足排序契约。

验证：预检查询页恰有一个单号和一个日期排序字段，字段名、显示名、标签名、别名均唯一，`必填=1` 且物理列存在；执行客户端同形的 `SELECT <查询字段> FROM <GetCrossTable> WHERE 1=2` 及派生表分页/排序包装，确认单号和日期可被外层排序引用；真实重开查询页并验证首次查询、翻页和日期/单号排序均不再报“单号无效”。

## 凭据类型宽度必须按标签和值自适应

补充口径：`IOJCBDZD` 的凭证类型帮助以 `IOBDZD_BH` 为键、以 `IOBDZD_MC` 为显示值；因此“当前路由短码长度”不能作为宽度依据。应按所有有效 `IOBDZD_MC` 的最长完整名称测量，并分别写入维护表单的 `宽度` 和查询网格的 `列宽` 契约。

症状：凭据类型（`*_PJLX`）控件或查询列能显示字段名，却放不下完整的当前最长路由值，出现截断或与相邻字段重叠。

可能原因：只按“凭据类型”四个字计算了最小宽度，或把 `SYS_TbColumn.列宽`（网格列）当成表单 `宽度`（输入控件）；路由值来自 `IOBDZD_BH`，其实际显示长度可能超过标签长度，固定写 `100`/复制其他单据宽度必然失配。

安全修复模式：分别为维护页和查询页计算 `*_PJLX` 的显示宽度，取完整标签和目标路由值（至少覆盖当前 `IOBDZD_BH` 的最长显示值）中较大的实际文本宽度，再加同版本客户端的左右内边距和控件余量，最后按该环境的网格步长向上取整。文本测量必须使用客户端当前字体/DPI 的 `GetTextExtentExPoint` 或等价证据；不能用字符数、表名长度、固定列宽或 SQL 字段长度代替。保留 `控件=S`、`类型=S`、`切换=1`、`GLZD=IOBDZD_BH` 映射，只调整经证据确认的布局宽度；自适应布局若需运行时重排，必须在创建和 resize 时重新测量，数据库初始坐标不能冒充自适应实现。

验证：枚举路由下所有 `IOBDZD_BH` 显示值，断言维护页和查询页的 `PJLX` 标签及最长值均完整落在各自的 `宽度`/`列宽` 内，宽度按步长取整且不与同一行字段相交；确认 `PJLX` 控件和映射契约未被布局修复改写。真实打开维护页和查询页，在不同窗口宽度/DPI 下检查当前最长路由值无截断、无重叠；若无法取得同版本字体测量或客户端 resize 证据，保持 review-blocked，不得宣称已自适应。

## 明细单号别名必须匹配翻前单外层过滤

症状：动态单据维护页可以打开，查询页也能加载，但点击“翻前单”时出现 `列名“单号”无效`；Release 日志中的明细 SQL 只输出 `明细单号`，外层却固定 `WHERE 单号=...`。

可能原因：明细页 `PageRowsTab` 复用了单据统一单号过滤和分录排序路径，要求派生表暴露稳定的 `单号` 别名；把 `<DETAIL>_SJDH` 标成“明细单号”只改变了输出列名，未改变物理字段，却使外层过滤失效。

安全修复模式：先读取活动源码/Release SQL，确认外层谓词和明细 `GetDataField` 投影；再以 `表名+PO+字段名` 精确锁定 `<DETAIL>_SJDH`，断言旧的 `显示名/标签名=明细单号` 后仅更新为 `单号`。维护页和查询页的单一查询单号字段要分别检查，不能通过新增业务列或改物理表掩盖别名错误。提供对称 rollback，保留旧值快照并断言影响行数。

验证：从 `v_tbcolumn` 重新生成明细投影，执行 `SELECT COUNT(*) FROM (<投影>) t WHERE t.单号=@单号`，再按客户端 `ORDER BY CAST(分录号 AS int)` 重放；确认不再出现 `列名“单号”无效`，且 `单号` 不是重复别名。最后真实重开原单据并执行翻前/翻后操作。

## 表头坐标必须来自同版本有效单据坐标，不得凭空生成

症状：动态单据维护页能打开，但表头字段叠压、错位、视图过高或页脚锚点漂移；或补入 `SYS_TbColumn` 的锚点字段沿用了另一张单据的坐标，与自身原有头部布局冲突，导致 `制单日期/单号` 与 `点检结果/备注` 叠字。

可能原因：表头字段的 `左坐标/顶坐标/宽度/高度` 被当作可随意填写的值，而 `SGSoft.cpp::CreateDlgItemWithArrayDateTime` 直接用 `rect.left=左坐标、rect.top=顶坐标、rect.right=left+宽度、rect.bottom=top+高度` 创建控件（宽/高 `<=0` 会兜底 `60/20`）。坐标是**表单客户区的像素值**，必须落在工具栏/凭证类型之下、网格(`IDC_TAB3`, `IDD_BILL_TY` 约 `DLU 19,117`)之上的头部带内；`制单人(ZDR)/审核人(SHR)/摘要(ZY)/审核(SHBZ)/凭证类型(PJLX)` 会被 `CBill::OnSize` 按窗口宽度动态重排，但初始坐标仍需用同版本同款值，否则首次绘制错位。

安全修复模式：先以**同库同版本可正常显示、布局等价的单据**为证据，抽取其 `PO=1` 标准锚点坐标和行距；再按参考布局把本单表头字段**按字段语义排布**，并让页脚锚点 `ZDR/SHR/ZY/SHBZ/PJLX` 与参考单据的完整矩形一致。只改 `左坐标/顶坐标/宽度/高度`，不改字段名/PO/RID/显示名/标签名/类型/控件/表头/必填/只读/列宽/顺序；每一行 `UPDATE` 按 `表名+PO+字段名` 精确命中并断言 `@@ROWCOUNT=1`；默认主键 `ID` 设为隐藏锚点 `0,0,0,0`。

验证：模拟 `CreateDlgItemWithArrayDateTime` 读取 `v_tbcolumn`，断言非主键字段宽/高 `>0`、左/顶非负、同一 `顶坐标` 分组内字段水平区间无重叠、页脚锚点等于标准坐标、跨维护+查询 `RID` 唯一；再用 `OnSize` 逻辑（`MoveToItemSJ/MoveToItem/MoveToMid`）核对 `ZDR/SHR/SHBZ/PJLX/ZY` 可被重排而不与网格冲突；最后真实重开维护页确认头部三行整齐、页脚锚点正常、无叠字。坐标修复只改 `SYS_TbColumn` 元数据，不触碰客户端源码或 RC。
## 审核字段必须复制同版本契约，不得写成复选框

症状：动态单据维护页/查询页能打开，但 `审核(<HEADER>_SHBZ)` 显示为复选框、不显示审核状态文字、或查询页无法按审核状态筛选；或保存时审核字段被当作可编辑布尔值。

可能原因：`SYS_TbColumn` 中 `_SHBZ` 被写成 `类型=C / 控件=C`（复选框）且 `GLZD` 为空、`必填=1`。同版本可正常显示的同模块单据均把审核状态定义为 `类型=S / 控件=E` 普通编辑框，`GLZD=LSDJZT_BH`、`切换=1`、`必填=0`、`列宽=1155`，物理列通常为 `bit NOT NULL DEFAULT 0`（0/1 即 未审核/已审核），`GLZD` 解析 `IOJCBDZD` 中 `Vkey=LSDJZT_BH` 的 `LSDJZT` 字典（-1 已否决/0 未审核/1 已审核/2 提交中/8 已通过）。维护页 `只读=1`（状态由审核/撤审流程写入），查询页 `只读=0`（允许作为筛选列）。

安全修复模式：用同库同版本、可正常运行的维护页与对应查询页提取 `_SHBZ` 的完整契约（类型/控件/GLZD/切换/默认值/必填/只读/列宽），再按 `表名+字段名` 精确更新维护页与查询页两行，每行断言影响 1 行。物理列和关联路由都必须以目标库 `sys.columns`、`IOJCBDZD` 与运行时 SQL 为准，不得照抄其他账套的字段类型、默认值或 `GLZD`。

验证：维护页应 `类型=S/控件=E/GLZD=LSDJZT_BH/切换=1/必填=0/只读=1/列宽=1155`，查询页应 `类型=S/控件=E/GLZD=LSDJZT_BH/切换=1/必填=0/只读=0/列宽=1155`；确认 `IOJCBDZD` 存在 `Vkey=LSDJZT_BH AND Table=LSDJZT AND MC=审核状态` 的字典行；物理列仍为 `bit NOT NULL`；`_SHBZ` 在维护+查询共 2 行。真实重开维护页与查询页确认审核栏显示字典文字且可筛选。

## 审核底边过低导致表头与表体之间出现大空洞

症状：动态主从单据表头字段本身没有叠压，但最后一个普通字段与“审核”之间空白过大；或者审核本来能放进当前行，却被强制单独放到下一行。由于客户端用审核底边计算表体页签顶部，表体也随审核位置一起被推得过低。

可能原因：只验证了普通字段没有越过审核底边，却机械复制了参考单据的审核顶坐标，或把 `SHBZ` 当成必须独占一栏。目标单据字段较少时，参考单据的绝对坐标会留下与字段数量不匹配的垂直空洞；带帮助字段还可能因按钮占用未计入而错误换行。

安全修复模式：先读 `CBill::OnSize` 和 `MoveToMid`，确认表体顶部等于审核底边加客户端固定间距；从同版本有效单据取得审核的左坐标、宽度、高度、完整控件 footprint 和普通表头行距。维护页按稳定 `顺序` 逐项横向装箱，审核先尝试当前行，只有完整标签/输入框/帮助占用超过右边界才换行；审核换行时按“上一行最后一个非固定可见表头字段底边 + 参考自然间距”计算顶坐标，同行时不强制垂直 gap。只更新经证据确认的坐标，并在 forward 中断言完整旧值、精确影响行数和目标值。不要移动 `ZDR/SHR/ZY` 固定页脚或修改字段契约。

验证：同时读取 `SYS_TbColumn` 和 `v_tbcolumn`，确认审核同行时同排完整 footprint 不相交；审核换行时确认上一行到审核顶坐标的自然间距至少为 10 且等于参考契约值；确认审核底边以及按 `MoveToMid` 推导出的表体顶部。带帮助字段还要确认外框宽度扣除/包含了实测浏览按钮宽度。rollback 只在审核坐标仍为本修复结果时恢复旧坐标；最后重新打开维护页确认表头和表体实际位置。

## BDJB 多脚本应合并为单过程

症状：取消审核需要维护多条重复的 `BDJB_SQL`，重启或重新配置后规则容易丢失，或新增下游单据拦截时错误提示不稳定。

可能原因：没有确认客户端 `SetTrigArray`/`ExeCmd` 的前置顺序与 `@SJDH` 文本替换，直接复制脚本；或在未保留旧规则快照的情况下覆盖 `BDJB`。

安全修复模式：先确认 `BDJB_QZJC,BDJB_ORDER` 和源码占位符替换，再把同一组只读 `IF EXISTS` 校验收敛到一个无结果集过程；专用下游错误先于通用错误，所有分支 `RAISERROR(...,16,1); RETURN`。用一个带数据库/实例、表列、旧 `BDJB_SQL` 精确门禁的 SQL 文件创建过程，并将唯一 BDJB 前置行改为 `EXEC dbo.<过程> '@SJDH'`；只读 MCP 不部署。

验证：静态确认只有一个过程；部署前用真实“有下游/无下游”单号分别验证关系计数，部署后核对 `sys.sql_modules` 和 BDJB 文本，再在获准测试环境确认错误文本、前置执行顺序、事务回滚和零结果集。详细源码入口、关系证据和重启后消失排查见 `references/bdjb-procedure-consolidation.md`。

## 主从动态单据必须通过固定九步回归门禁

症状：主从单据能建表或部分打开，但出现 BOM 版本不联动、数量放错表头、查询“单号”无效、`FROM )`/`SELECT FROM`、PJLX 截断、表头重叠、缺少审核按钮或 Release 翻前翻后失败；每次修复都重新临时判断，容易漏掉跨元数据链路。

可能原因：只验证了物理表或单一 `SYS_TbColumn` 行，没有把单据分类、固定字段、业务数量归属、BOM 参数、查询别名、客户端派生 SQL、字体/DPI 布局、BDJB/工作区/sysmenu 和真实 Release 操作作为一个闭环。

安全修复模式：强制按 `references/complex-form-fast-path.md` 的九步顺序建立证据包：

1. 目标数据库/实例、代码版本和 `IOBDZD` 主从分类；
2. 表头 `HID/YWRQ/PJLX/SJDH/PRINT/SHBZ/ZDR/SHR/ZY`、明细 `FID/SJDH/FLH` 固定字段卡，以及目标库拼音首字母缩写/前缀、保留后缀和重名检查；
3. 按本业务记录主对象、从对象及数量来源；物料需求分析类必须记录成品/BOM/分析数量与逐物料采购、需求、库存、在途、到货未检验、净需求的来源、公式、单位和空值策略；
4. 若契约涉及 BOM，则以当前成品参数过滤 BOM 版本并覆盖多版本及无 BOM 负例；不涉及 BOM 时记录不适用证据，不得臆造字段；
5. 查询页单一 `PO=1`、`表头=0`、连续顺序、唯一别名及必填“单号/日期”，明细单号按外层谓词暴露稳定“单号”；
6. 回放 `GetDataField/GetCrossTable/PageRowsTab` 的完整派生 SQL，拒绝空 `SELECT`、`FROM )`、无效列、重复别名和悬空连接；
7. 维护 `宽度` 与查询 `列宽` 分开按实测字体/DPI 计算，按同版本等价参考单据的最左坐标递推非固定字段，保留页脚锚点和审核底边；
8. 校验 BDJB、SYSWSPACE、角色列及七个标准 `sysmenu` 动作；
9. 以数据库/实例门禁、旧值断言、影响行数断言、事务和对称 rollback 部署，完成隔离 CRUD 和真实 Release 重开/翻前翻后/保存冒烟。

验证：每一步记录可复核的 SQL/源码证据和 pass/fail；任一步失败即 `review-blocked`，后续步骤不写库。只有九步全部通过，且用户完成真实客户端重开，才可报告主从单据完成；SQL 通过但未真实重开必须明确标记为未完成。

## 既有动态单据参照过滤应走窄路径

症状：已有动态单据的参照功能正常，但用户要求排除过期、失效或不满足状态的数据；如果按新建动态单据流程重新扫描 `IOBDZD`、全部元数据、权限和生命周期，会重复消耗大量时间。

可能原因：把“已有关系的过滤修复”误判成“新建单据契约”，或没有先读取精确的 `IOYYGX` 操作行。参照过滤实际由 `IOYYGX_GLTJ` 作为来源查询条件的一部分，来源字段语义仍必须由 schema、运行时 SQL 和数据确认。

安全修复模式：先读 `references/reference-fast-path.md`。核对目标身份和唯一 `IOYYGX` 行，只在活动路径使用时检查 `IOPOPDLG` 回退来源；确认结束日期/状态字段后，预览旧条件、新条件和排除数量。用户只说“过期不参照”时，最小规则是已确认结束日期为 NULL 或不早于 SQL Server 当天，例如：

```sql
AND (<ConfirmedEndDateColumn> IS NULL
     OR <ConfirmedEndDateColumn> >= CONVERT(date,GETDATE()))
```

用部署前旧值作为 `UPDATE` 谓词，在干净事务中只更新配置行并断言 `@@ROWCOUNT=1`，提供反向 rollback。不要改来源业务数据、数量或状态；不要把部署日期写死，也不要未经用户要求追加开始日期条件。若新增关系、元数据、字段、生命周期或保存行为，立即转回完整动态单据契约。

验证：重新读取精确 `IOYYGX` 值，重放客户端形状的来源 `SELECT/JOIN/别名`，确认过期行排除、结果集形状不变且业务表无写入；真实客户端参照窗口另行报告。`ALTER TABLE` 后在同一脚本继续引用新列时拆分 SQL 批次，`IDENTITY` 技术列由数据库生成，不在 `INSERT` 中显式提供。

## 动态单据上下游关系必须双向闭合

症状：单据“关联单据”窗口只能看到一侧，或 SQL 直接执行有结果但客户端打开时报列数错误、关联单据不显示；也可能是当前单据保存了多个来源单号，但只通过其中一个来源的传递关系查找，导致另一条直连关系永远缺失。

可能原因：`SearchRelation.cpp` 按 `IOYYGX_BDMC=当前单据` 读取 `SYLJ`，按 `IOYYGX_CZMC=当前单据` 读取 `XYLJ`；它只对当前名称下的配置做 `UNION ALL`，不会自动沿着 A->B->C 做传递遍历。它会先跳过 `NULL` 的 `SYLJ/XYLJ`，因此启用关系行但所需一侧 SQL 为空时窗口仍无记录。另一个常见错误是把 `GLTJ`/来源表元数据当成了上下游显示 SQL，或者让同一方向的 SQL 返回不同列数。

安全修复模式：先读取活动 `SearchRelation.cpp`，确认当前/来源方向和 `@SJDH/@FLH` 替换规则。为每个已确认的直接来源标识建立一条 reciprocal `IOYYGX` 行：当前单据到来源写入 `SYLJ`，来源到当前写入 `XYLJ`。替换占位符后，`SYLJ` 统一返回七列“单号、日期、单据类型、制单人、总量、达成、审核”，`XYLJ` 统一返回六列“单号、日期、单据类型、制单人、达成、审核”；每个配置值只保留一个可执行 `SELECT`，不放变量、临时表、调试结果集或不稳定别名。发布前对旧行做精确快照和旧值断言；不能把 `IOYYGX_ID/IOYYGX_BH` 当作唯一键，谓词还要覆盖单据名、方向标志、启用状态和旧 SQL。新增的非 identity 编号在事务锁内分配并检查冲突。

验证：分别执行每条替换后的 SQL，再验证同方向多条 SQL 的 `UNION ALL` 结果集列数、顺序和类型兼容；至少用一个真实单据证明每条直接链的上游和下游都能返回。检查 `IOYYGX_YXBZ=1`、所需 `SYLJ/XYLJ` 非 `NULL`、完整关系元组唯一、旧值/新值和回滚条件。生产发布由人工通道执行时，交付固定顺序 `preflight -> forward -> verification`，失败即停止；随后用只读连接回读实际新编号和运行时 SQL。最后把客户端关联窗口重新打开并双击验证。数据库 SQL 通过而客户端未重开时，只能报告为数据库验证完成，不能报告为最终功能完成。

## ER 字段闭合与中文映射缺失

症状：表单可以部分打开或标题 SQL 能执行，但维护页/查询页缺少 ER 字段；某些字段显示为空、显示物理字段名，或主表/从表同名字段在查询页被错误去重。

常见原因：只按元数据总行数判断完成，未按“物理表 + `PO` + 字段名”逐项比对；维护页和独立查询页被当成同一字段集；生成器用物理字段名作为缺省 `显示名/标签名`；只为已报错的几个字段补中文映射，没有把字段映射作为完整契约。

安全修复模式：先建立字段闭合矩阵，分别记录每个物理表头/表体字段到维护页和查询页的映射，以及 `显示名/标签名/查询别名`。生成时要求 ER 字段有明确的人类可读标签，禁止空标签或物理字段名回退；维护页和查询页分别执行双向集合检查，缺失和多余都 fail-closed；查询页用显式别名区分表头/表体同义字段，不删除单号、日期等运行锚点。对已有库先导出旧值，只更新已确认的映射行，不用“补一列”掩盖客户端字段路径错误。

验证：逐表输出物理字段数、维护字段数、查询字段数及缺失/多余字段；逐行检查 `字段名 -> 显示名/标签名`，拒绝空值和物理名回退；检查查询别名/标签唯一；通过 `v_tbcolumn` 回放维护字段、查询标题 SQL、派生表分页和初始加载。只有数据库等价检查通过后，才进行真实维护页、查询页和翻前/翻后重开。

## 模块级物理字段后缀迁移必须全量闭合

症状：一个示例字段改名后，另一个 EAM/设备类表单仍报“列不存在”、帮助打不开、`FROM`/JOIN 失败，或新建脚本与已部署库的字段命名不一致。

可能原因：把用户给出的两个字段当成了全部范围，只修改了物理列和一部分 `SYS_TbColumn` 行；遗漏同模块其他表、`GLZD`/帮助路由、`IOJCBDZD` 的键值、注册/布局脚本、ER 图或外键引用。通用的 `_BH` 搜索也可能漏掉没有固定前缀的 `LIKE '%_ZC_BH'` 等模式。

安全修复模式：先在确认的数据库中按模块前缀和旧后缀从 `sys.columns` 生成完整 old-to-new map，并保存类型、长度、可空性、数据量、外键列绑定和所有元数据命中数。命名规则必须由同模块现有列证明，不能因为显示标签或单个示例臆造。前向脚本在数据库/实例门禁和干净事务内逐列 `sp_rename`，然后按旧值分别更新 `SYS_TbColumn.字段名`、`SYS_TbColumn.GLZD`、`IOJCBDZD` 的 `Vkey/BYZD` 及已确认的路由字符串；每一类都做精确影响行数断言。同步更新当前建表/注册/查询/布局/验证/回滚脚本和 ER 定义；迁移前证据及反向映射可以保留旧名，但必须明确是历史或 rollback 内容。

验证：逐项证明物理新列数等于映射数、旧列为零、类型/长度/可空性未变；外键列关系数量和目标键未变；维护页与查询页 `SYS_TbColumn` 的字段闭合、`GLZD`/帮助路由无旧名且可执行；`sys.sql_modules`、当前工程脚本和 ER XML 中无未审阅旧名；运行时形状的帮助、JOIN、标题 SQL 和派生表包装可解析。回滚只在新名仍完整、旧名不存在且元数据仍是前向结果时反向执行，不能用删除业务数据替代列名回滚。

## 源码硬编码契约导致的“无异常报错”

症状：数据库对象、约束、CRUD 全部正常，但客户端弹“控件初始化时出错!”、“转译失败/数据读取失败”、单据打不开、明细页签空白，或生成的 SQL 报语法错误；错误信息里没有可用的表名或列名。

可能原因：这些错误几乎都不是数据库缺陷，而是编译进 EXE 的常量没有被满足——空的 `显示名/字段名`、`标识` 被填成 `'0'`、`GLZD` 行的 `LMark/RMark` 为 `NULL`、`PO=1` 某行 `控件/类型/RID/显示/必填/只读` 为 `NULL`、`单号`/`分录号` 别名缺失、`分录号` 不能 `cast as int`、可见名在 `IOJCBDZD/IOBDZD/SYS_TbColumn/SYSWSPACE/sysmenu` 之间不一致、`GLZD` 与 `帮助` 两条路由的键（`IOJCBDZD_MC` 与 `IOJCBDZD_BZBH`）被混用、库排序规则为大小写敏感。源码读不到的键只返回空串，空串被直接拼进 SQL，所以没有异常、没有堆栈。

安全修复模式：不要先改数据库，也不要靠“加一列”让对方不报错。先读 `references/client-source-contract.md`，用确切拼接形状回放维护页、查询页和翻前单三种 SQL，定位是字段集为空（`SELECT  FROM …`）还是跨表来源为空（`FROM )`）；再按硬规则逐条核对键、别名、控件码、后缀锚点、`顺序` 基址和可见名一致性。修复只针对已证实违反的那一项，保留旧值断言、影响行数断言和对称回滚；`码表编号` 之类属于客户端源码范围的缺失映射，报告为客户端问题，不得用新业务列掩盖。

验证：按 `client-source-contract.md` 第 7 节清单逐项取证；回放 `SELECT <GetDataField> FROM <GetCrossTable> WHERE 1=2` 与三种包装形状并确认可解析；确认 `v_tbcolumn` 无空 `显示名/字段名`、`标识` 全为 `NULL`、`GLZD` 行别名闭合；最后要求真实客户端重开单据、页签和帮助窗口验收，数据库验证通过不等于界面可用。

## 未参与编译的源码不能作为契约依据

症状：按源码里某套更“完整”的契约改了数据库（补表、补列、改别名），真机行为毫无变化；或两个界面读同一份元数据，一个正常一个报错。

可能原因：源码目录里的 `.cpp` 并不都参与编译。`SGSoft.vcxproj` 的 `<ClCompile Include>` 列表只覆盖其中一部分，其余（例如旧销售单据、旧单据维护页、旧物料单位页）是历史代码。它们可能使用完全不同的元数据模型——例如另一套 `v_fieldshow` + 独立视图表 + `表头=0/1` + 别名 `单号`/`fid`/`业务类型`，与在用的 `v_tbcolumn` + `PO` 模型并存。此外同一份元数据在 `GetDataField`、`GetGroupField`、`GetCrossTable`、`GetCrossTableS` 四个入口的投影规则并不相同（`GetGroupField` 丢弃 `标识` 非空行，`GetCrossTable` 只扫 `PO<=2`，`GetCrossTableS` 在无别名时不加 `RMark` 前缀）。

安全修复模式：定位前先做归属判断——症状对应的界面入口在哪个**已编译**文件里，它读的是哪张元数据表、用 `PO` 还是别的表头标志、投影走哪个函数。把取证范围收敛到 `<ClCompile Include>` 列表的并集，再对照该入口的确切拼接形状。不要用未编译文件里的表名或列名去改数据库；也不要假设一个字段集在所有入口都产生同样的列。

验证：先给出“入口 → 已编译文件 → 元数据表 → 投影函数”的链路，再按该链路回放 SQL；确认修改后该入口的投影确实变化，并说明其它入口是否也读同一份元数据、是否受影响。

## 元数据取值规则必须有唯一权威

症状：同一份元数据在两处 reference 里被描述成不同取值（例如某处要求日期字段 `类型=D`、另一处写 `DT`，或列宽基准一处写 `840`、另一处给了别的数字），改完之后仍不确定哪个才对；或者新加一条规则时只更新了其中一个文件，另一个继续给出旧结论。

可能原因：`类型`、`控件`、`顺序`、`RID`、`标识`、`列宽`、`主键`、`关键字段` 这些取值同时被流程层（分型、建表、注册顺序）、执行层（四阶段、九步门禁）和源码常量层描述，三处各写一份。规则演进时只改一处，其余成为过期副本；而源码常量是唯一事实来源，流程文档里的副本没有独立证据。

安全修复模式：指定唯一权威文件承载取值表（当前是 `client-source-contract.md` 第 9 节），其余文件改为声明「取值以该节为准」并只保留门禁与流程，不复述取值表。每个引用文件在标题下方放一条权威声明，明确分歧时的处理方向。新增或修改取值规则时只改权威文件，再检查引用处是否需要更新措辞。流程性内容（验收顺序、阻断条件、交付物）留在原文件，不要一并搬走。

验证：对每个取值关键词统计各文件出现次数，确认完整取值表只在权威文件中出现一次，其余为指向该节的引用；运行 skill 自测与 `quick_validate.py`；确认没有规则在搬迁中丢失（对比搬迁前后的关键词计数，丢失项必须在权威文件中能找到对应条目）。
