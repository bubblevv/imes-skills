# 复杂表单四阶段快速通道

## 适用范围

模板、记录、审核、出入库/转移等表头表体单据，以及任何同时依赖 `IOBDZD`、`SYS_TbColumn`、独立查询页、`BDJB` 或 `SYSWSPACE` 的元数据表单。复杂表单必须走真正的 `IOBDZD` 路径，不能套用 `BTYPE=1/UForm1` 单表脚手架。

## 四阶段

### 1. 字段契约确认

先建立 `contract.json`，把不确定事项写成阻断项，不要猜：

- `header`、`detail` 物理表和完整字段集；每个字段给出真实 SQL 类型、nullable、主键/identity、默认值和测试值；
- 单号字段、分录号字段、表头到表体的外键以及唯一性；
- `route`：IOBDZD 编号、MARK、FORMAT、表头/表体名、HVKey/FVKey、页签名；`FORMAT` 是 `PRD_GETDANHAO` 的编号格式，缺失或空白时固定默认为 `YYMM####`，不能生成 `NULL`/空串；
- `metadata.maintain_fields` 和 `metadata.query_fields`，字段集必须闭合；契约固定声明 `rid_strategy: "runtime-max-plus-offset"`，由部署事务读取当前 `MAX(RID)+1` 并为维护页和查询页连续分配唯一正整数；物理 `date`、`datetime`、`datetime2` 字段的元数据 `类型` 固定为 `D`，其余字段固定为 `S`；普通字段控件固定为 `E`，`*_PJLX`/凭证类型字段固定为 `S`，不生成其他控件代码；`SYS_TbColumn.标识` 必须保持 `NULL`，不要插入 `nID`；`列宽` 默认按 `scripts/metadata_width.py` 对该行可见 `标签名` 的完整显示宽度生成，不复制参考单据的内容列宽；以本客户端 `分录号=840` 为 3 个汉字基准，4 个汉字取 `1125`，ASCII 按半宽单元计算并按 `15` 单位向上取整，显式更宽值可以保留，显式小于标签最小宽度则阻断生成；`宽度` 仅表示控件布局宽度时必须使用独立的 `column_width` 保存表格列宽；
- 维护页和查询页必须在每个 `(表名, PO)` 内将 `顺序` 重新编号为 `1..n`；生成器不得沿用 0 基索引、旧序号、重复值或跳号。
- 每个 `(表名,PO)` 元数据组必须恰好一个 `主键=1`；`关键字段` 不得默认继承 identity 主键；查询页全体字段只允许一个 `关键字段=1`，且查询输出别名必须唯一。
- 查询页（`<IOBDZD_MC>查询`）本身必须是单一 `PO=1` 的扁平字段集：不得拆成多个 `PO` 分组，`表头` 一律为 `0`（查询页是网格列，不是维护页的表头锚点行）；`顺序` 从 `1..n` 连续且唯一；`显示名` 与 `标签名` 均须唯一（表头/明细同名同义字段要按查询粒度去重，例如 `ID→HID/FID`、`单号→单号/明细单号`、`备注→备注/行备注`）。生成器对 `query_fields` 强制 `po=1`、`header=0` 并做去重校验；部署后验证再核对查询页单一 `PO`、无表头锚点行、`显示名`/`标签名` 唯一。
- `metadata.audit.field`、审核控件矩形 `left/top/width/height/bottom`、审核推导的 `min_header_width`、来自参考单据的 `natural_gap` 和同版本有效参考单据；审核左坐标/宽度/高度及自然间距禁止凭经验填写。字段较少时，审核顶坐标应按最后一个非固定可见表头字段底边加 `natural_gap` 推导，不要机械复制参考单据留下大空洞；表头普通字段不得越过审核前的自然间距、审核底边或最低宽度；
- 字段闭合与文案映射矩阵：每个物理表头/表体字段必须逐项映射到维护页 `PO` 和独立查询页，维护/查询两套字段集合都要做“物理列 -> 元数据”和“元数据 -> 物理列/已证实投影”的双向检查；每个可见字段必须有明确中文或经确认的人类可读 `显示名/标签名`，禁止空文案、物理字段名回退和仅按行数判断完整；
- 对要求自适应的表头：每行第一个普通输入框使用参考单据最左普通输入框坐标；后续输入框的左坐标固定按 `前一输入框右边界 + 视觉间隔 + 下一标签运行时实测宽度 + 5` 推导，标签宽度是当前字体/DPI 下 `CDataEdit::GetTextExtentExPoint` 结果加控件 `6` 单位创建边距。不得用固定列、字数、网格列宽或每字像素估算。`SYS_TbColumn` 只定义初始矩形；若窗口、字体或 DPI 改变后仍需自适应，契约必须列入客户端初次创建和 `OnSize` 流式重排。没有同版本实测和客户端实现时，保持 `review-blocked`；
- `bdjb.rows` 或已审阅的审核/撤审规则；`workspace.rows`。角色权限列和 `admin` 后权限列由部署脚本动态发现并默认授权，不能硬编码角色名。

### 2. 前期只读准备

运行 `preflight.sql` 和 `reference-evidence.sql`，核对 `DB_NAME()`、`@@SERVERNAME`、物理字段、`IOBDZD`、`SYS_TbColumn/v_tbcolumn`、`BDJB`、`SYSWSPACE` 和同版本参考单据。参考证据必须来自已运行的同类单据，不得把新单据本身当布局证据。

前期只读结果要回填契约，特别是：真实字段类型、主键策略、IOBDZD 路由、`FORMAT/BascData/CurMonth/ModifyDate` 编号状态、`PO=1/2/...` 字段集、审核/制单/摘要锚点、最后一个非固定表头字段底边、`natural_gap`、查询页、BDJB 生命周期规则、工作区编号和角色列。源码核对要确认 `GenDanhao` 传入的是可见名 `IOBDZD_MC`；不要用 `BH` 或 `BILLNO` 代替编号查找键。

### 3. 中期事务部署

只有契约完整且 `deployment_ready=true` 才生成可执行 `forward.sql`。脚本按一个事务部署：物理表/约束 → IOBDZD → 维护页和查询页元数据 → BDJB → SYSWSPACE；动态更新 `RID` 后角色列及 `admin` 后工作区权限列为 `1`。`schema-draft.sql` 只能是注释式审阅产物，不得包含可执行 `CREATE TABLE`，不能把整个目录的 `.sql` 直接批量喂给 `sqlcmd`。脚本不创建 MFC/C++/RC 资源。

### 4. 后期验证与隔离 CRUD

按顺序运行 `verification.sql`、`crud-test.sql`。验证必须检查路由唯一、维护页和查询页字段集闭合、字段不悬空、`标识` 为 NULL、`RID` 非空/正数/跨维护页和查询页唯一、逐字段 `类型/控件/标签/显示/必填/只读/布局` 契约，以及同样的 `v_tbcolumn` 投影；它应模拟 `CBill::InitForm`/`CreateDlgItemWithArrayDateTime` 的强制读取，而不是只统计基础表行数。还要检查最后一个非固定表头字段底边到审核顶坐标的 `natural_gap`、审核底边、按 `MoveToMid` 推导的表体顶部、物理表头体查询形状和工作区/权限。CRUD 必须在事务中回滚并断言零残留。数据库验证通过后仍必须让用户真实重新打开维护页和查询页；若当前会话未完成该动作，明确报告“数据库等价控件初始化验证通过，尚未完成真实客户端重新打开验证”。回滚前先运行 `rollback-preflight.sql`，有业务数据时拒绝回滚。

## 主从动态单据固定九步回归门禁

所有新建或修复的 `IOBDZD` 主从单据都按以下九步执行，顺序不可跳过。每一步都要在证据包中留下查询结果、断言结果和失败原因；任一步失败即停止后续写入并标记 `review-blocked`。

1. **目标身份与单据分类**：确认 `DB_NAME()`、`@@SERVERNAME`、授权范围和代码版本；依据 `1:N` 外键、单号生命周期、`PO` 页签和审核链将对象定性为 `IOBDZD`，记录物理表数与表单数，不把主从表压扁成单表。
2. **固定字段卡与命名**：逐项核对表头 `HID/YWRQ/PJLX/SJDH/PRINT/SHBZ/ZDR/SHR/ZY` 和明细 `FID/SJDH/FLH` 的物理列、默认值、可空性、主键及维护/查询元数据；业务字段沿用目标库现有的拼音首字母缩写和前缀规则，先查 `sys.columns`/既有表的重名、同音异义和保留后缀，禁止临时英文名或只改中文标签。日期物理类型只映射 `类型=D`，其他新字段 `类型=S`，普通控件 `E`，`*_PJLX` 控件 `S`，`SHBZ` 物理非空时必须有非空默认值。
3. **业务语义与数量归属**：按本单据业务写出主对象、从对象和所有数量的归属；物料需求分析类必须明确“成品/分析物料、BOM 版本、成品分析数量”与“物料、采购单价、需求数量、库存、在途、到货未检验、净需求”的归属。表头不得承载逐物料数量；每个数量列必须注明来源表、单位、计算公式、累计/覆盖语义和空值策略。
4. **BOM 版本联动（适用时）**：若契约包含成品/BOM 字段，必须证明物料帮助返回当前成品的有效 BOM 版本，版本帮助以当前成品物料参数过滤并在切换成品后清空/重载；静态 `GLZD` 或未带成品参数的帮助过滤不算联动通过，至少执行多版本和无 BOM 负例。若业务不涉及 BOM，记录 `N/A` 及不适用证据，不得凭空增加 BOM 字段。
5. **查询页字段及别名**：`<单据名>查询` 必须是单一 `PO=1`、`表头=0`、`顺序=1..n` 连续集；`显示名`/`标签名` 唯一；必须有唯一可见必填“单号”和“日期”（日期 `类型=D`），并验证 `ORDER BY 日期,单号` 和外层谓词。明细 `<DETAIL>_SJDH` 若被翻前单固定按“单号”过滤，投影别名必须为“单号”。
6. **客户端派生 SQL 回放**：按 `GetDataField`、`GetCrossTable`、`PageRowsTab` 的真实包装重放维护初始加载、查询标题、派生表分页/排序、翻前/翻后单和明细分录排序；硬性扫描并拒绝 `SELECT  FROM`、`FROM )`、无效“单号/日期”列、重复别名、悬空 `LEFT JOIN`。数据库只读连接只能取证，不能代替授权部署。
7. **PJLX 宽度与表头布局**：维护控件 `宽度` 与查询网格 `列宽` 分开计算；以活动字体/DPI 实测完整标签和最长 `IOBDZD_MC` 显示值并加余量，禁止按短码、字数或固定 1470/2250。表头从同版本、同布局的有效单据最左坐标开始，按稳定顺序逐项尝试当前行，`SHBZ` 能放下就与当前行字段同行，只有完整标签/输入框/帮助 footprint 越过右边界才换行；固定 `ZDR/SHR/ZY` 页脚锚点不移动，审核底边作为表头下限。带非空 `帮助` 的 `CDataEdit` 默认预留 20 个浏览按钮单位，定制图标按 `max(20,imageWidth+8)` 实测；验证标签和帮助占用都包含在碰撞检测中，审核换行时才验证上一行自然间距。
8. **BDJB、工作区、sysmenu、角色权限**：核对有效审核/撤审 `BDJB` 及下游关系；核对 `SYSWSPACE` 父/叶/操作行和实际角色列；动态主从单据补齐并逐项校验七个标准 `sysmenu` 动作（显示关联单据、保存列宽、列配置、从EXCEL导入、说明、附件、复制分录），不得只验证 admin。
9. **事务部署、回滚、Release 实测**：所有写入使用数据库/实例门禁、完整旧值快照、影响行数断言和单事务；提供对称 rollback 与 `rollback-preflight`，有业务数据时拒绝回滚。部署后依次跑 verification、隔离 CRUD（零残留）、维护页/查询页/翻前翻后/新增保存的真实 Release 冒烟；未完成真实重开必须明确标记未完成，不能以 SQL 通过代替。

### 九步错误映射

| 症状 | 优先门禁 | 典型首个断言 |
|---|---:|---|
| `凭证类型` 无效/空、`NULL` 插入 `SHBZ` | 2 | 固定字段物理非空、默认值、`PJLX`/`SHBZ` 元数据完整 |
| BOM 版本不随物料刷新 | 4 | 帮助 SQL 含当前成品参数，切换后清空并重载 |
| “单号”无效、翻前单失败 | 5/6 | 查询单号日期别名存在；明细外层 `WHERE 单号` 可解析 |
| `SELECT FROM`、`FROM )` | 6 | 客户端同形投影/派生表包装可解析 |
| 凭证类型截断、表头重叠或空洞 | 7 | 实测字体宽度、标签-inclusive 碰撞、固定锚点和审核底边 |
| 查得到但没有审核/关联/复制按钮 | 8 | BDJB、SYSWSPACE、七个标准 `sysmenu` 行及角色列 |
| Release 翻前/翻后/保存仍报错 | 9 | 真实客户端流程；SQL 验证不能单独结案 |

## 脚手架

```text
scripts/scaffold_complex_form.py
```

从 ER 图只生成审阅阻断包：

```powershell
python -X utf8 scripts/scaffold_complex_form.py `
  --er-svg docs/资产ER图.svg --header-table HEADER_TABLE --detail-table DETAIL_TABLE `
  --bill-name 目标单据 --form-kind target_bill `
  --expected-database <confirmed-test-database> --expected-server <confirmed-instance> `
  --output-dir diagnostics/complex-form/inspection-template --force
```

ER 图只能加速表和字段初稿，不能直接生成可部署 SQL。补齐契约后：

```powershell
python -X utf8 scripts/scaffold_complex_form.py `
  --contract diagnostics/complex-form/inspection-template/contract.json `
  --bill-name 目标单据 --output-dir diagnostics/complex-form/target-bill --force
```

## 完成/阻断标准

- **review-blocked**：缺任一关键证据，`forward/verification/crud/rollback` 只输出明确 `THROW`，不得伪装成可部署脚本。
- **deployment-ready**：物理字段、主键/外键、路由、维护/查询页元数据、审核布局、BDJB、工作区和测试值均确认；生成完整十文件包（含契约、草案、前置、证据、部署、验证、CRUD、回滚前置、回滚和 README）。
- 数据库 MCP 调查连接只用于只读证据；写入部署必须由用户在确认的测试库执行，或使用明确授权的安全执行通道。输出文件不含凭据。
