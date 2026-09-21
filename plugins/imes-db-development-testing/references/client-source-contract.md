# 客户端源码硬编码契约（iMES 老客户端）

本文件记录编译进 EXE 的**字面量表名、列名、别名、控件码、后缀锚点和 SQL 拼接形状**。它们不是约定，是常量：数据库可以完全合法、约束齐全、CRUD 正常，但客户端仍然报错、空白、闪退。

证据来源（`SegaERPSeven*` 客户端源码，函数名比行号稳定）：

- `SGSoft.cpp`：`CSGSoftApp::GetDataField`、`GetCrossTable`、`GetCrossTableS`、`GetStrTgValue`、`GetDoubleTgValue`、`CreateDlgItem*` / `CreateDlgItemWithArrayDateTime`、`GenInsertSqlFromGrid`、`GenUpdateSqlFromGrid`、`GenInsertSqlFromForm`、`GenUpdateSqlFromForm`、`GenDanhao`、`StartSP`、`LoadOneTextValue`(实际在 `Bill.cpp`)
- `Bill.cpp`：`CBill::InitForm`、`OnTynew`、`OnModuleMod`、`LoadOneTextValue`、菜单构建
- `PageRowsTab.cpp`：`CPageRowsTab::InitForm`、`RefreshData`
- `DataEdit.cpp`：`CDataEdit::OnShowChooseWindow`、`OnBrowse`、`OnRButtonDown`、`OnChar`、`SetType`
- `UForm1.cpp`、`UForm2.cpp`、`BaseItem.cpp`、`SearchRelation.cpp`

同一份源码版本内有效。更换客户端版本、分支或定制包后，必须重新按源码回放，不能沿用本文件结论。

### 0.1 先确定哪些文件真的进了 EXE
源码目录里有 232 个 `.cpp`，`SGSoft.vcxproj` 只编译其中 **194** 个。未参与编译的文件（`Sale.cpp`、`SaleBegin.cpp`、`SaleGet.cpp`、`BillFormD.cpp`、`BillOnlyForm.cpp`、`BaseGoodsUnit*.cpp`、`BaseFplx.cpp`、`BaseZYX.cpp`、`QuoteBill.cpp`、`PageRows.cpp`、`AppointMent.cpp`、`ReportKctz/Stock*/Stockwater.cpp`、`SysAuthoritySet.cpp`、`SegaSoftDoc.cpp`、`* - 副本.cpp` 等）**不影响运行时行为**：它们里面即使有更严格的契约，也只是历史代码。

前置步骤：从 `SGSoft.vcxproj` 提取 `<ClCompile Include="...">` 列表，只在交集范围内取证。引用未编译文件里的表名、列名或别名去修数据库，会得到“按死代码修、真机照旧报错”的结果。

```bash
grep -o '<ClCompile Include="[^"]*"' SGSoft.vcxproj | sed 's/.*Include="//;s/"//' | sort > compiled.txt
```

本文件所有结论均取自该交集；下面标注「未编译」的路径仅作历史对照。

---

## 0. 四条元规则

1. **先确定哪些文件真的进了 EXE。** 源码目录里有 232 个 `.cpp`，`SGSoft.vcxproj` 只编译其中 **194** 个。未参与编译的文件（`Sale.cpp`、`SaleBegin.cpp`、`SaleGet.cpp`、`BillFormD.cpp`、`BillOnlyForm.cpp`、`BaseGoodsUnit*.cpp`、`BaseFplx.cpp`、`BaseZYX.cpp`、`QuoteBill.cpp`、`PageRows.cpp`、`AppointMent.cpp`、`ReportKctz/Stock*/Stockwater.cpp`、`SysAuthoritySet.cpp`、`SegaSoftDoc.cpp`、`* - 副本.cpp` 等）**不影响运行时行为**：它们里面即使有更严格的契约，也只是历史代码。前置步骤是从 `SGSoft.vcxproj` 提取 `<ClCompile Include="...">` 列表，只在交集范围内取证；引用未编译文件里的表名、列名或别名去修数据库，会得到“按死代码修、真机照旧报错”的结果。

   ```bash
   grep -o '<ClCompile Include="[^"]*"' SGSoft.vcxproj | sed 's/.*Include="//;s/"//' | sort > compiled.txt
   ```

   本文件所有结论均取自该交集。

2. **源码读不到的键不报错，只返回空串。** `GetStrTgValue` 取首行首列，没有行就是 `""`；空串被直接拼进 SQL，最终表现为 `FROM )`、`select  , ...`、`字段=''`。这类错误没有异常、没有堆栈，只能靠回放 SQL 定位。
3. **表名/视图名大小写不保证一致。** `GetDataField` 用 `v_tbcolumn`，`GetCrossTable` 用 `V_TbColumn`，`UForm1` 用 `V_TBCOLUMN`。目标库排序规则必须是大小写不敏感（`Chinese_PRC_CI_AS` 一类）；若为 `_CS_`，同名不同大小写会直接报“对象名无效”。前置检查必须读 `DATABASEPROPERTYEX(DB_NAME(),'Collation')`。
4. **同一业务对象有三个不同的键，不能混用。** 路由/关联用 `IOJCBDZD_MC`，帮助用 `IOJCBDZD_BZBH`，单据用 `IOBDZD_MC`（部分路径用 `IOBDZD_BH`）。键写错不报错，只取到空值。

| 读取者 | 表 | 键列 | 取用列 |
|---|---|---|---|
| 关联显示投影 `v_tbcolumn` | `IOJCBDZD` | `IOJCBDZD_MC` = 字段的 `GLZD` | `TABLE / VKEY / BYZD / FILTER` |
| 帮助选择窗口 `CDataEdit::OnShowChooseWindow` | `IOJCBDZD` | `IOJCBDZD_BZBH` = 字段的 `帮助` | `TABLE / BZMC / VKEY / BYZD / FILTER / SXXS` |
| 参照列表 `CBaseItem::LoadData`（无 `strBZMC` 分支） | `IOJCBDZD` | `IOJCBDZD_MC` | `VKEY / BYZD / TABLE / FILTER` |
| 单据跨表来源 `GetCrossTable` | `IOBDZD` | `IOBDZD_MC` = 表单名 | `HTable / FTable / HVkey / FVkey` |
| 单据审批/编号 `StartSP` | `IOBDZD` | `IOBDZD_BH` | `HTABLE / MC` |
| 单据初始化/权限 `CBill::InitForm` | `IOBDZD` | `IOBDZD_MC` = 表单名 | `BH / DJGL / HTABLE / FTable / …` |
| 报表按钮 `CBill::InitForm` | `report` | `report_pjlx` = 表单名 | `report_mc` |
| 报表设计器选项列表 `DlgProperty` | `IOJCBDZD` | `IOJCBDZD_BZBH` = 字段 `帮助` | `TABLE / VKEY / FILTER / BYZD` |

### 0.2 表单打开的真实判定链（`CMainFrame::AutoOpen`）

打开一个表单名时，源码按**固定顺序**判定，第一个命中的分支决定行为：

1. `IsValid(当前角色, 表单名)` — 查 `SYSWSPACE` where `SYSWSPACE_MC = 角色 + 表单名`。**角色为 `ADMIN` 时直接放行**；查不到该行也**放行**（`GetBoolTgValue` 返回 false → `return true`）；查到且值为 0 → 弹“抱歉,您需要通过管理员授权。”并返回 false。
2. 查 `IOBDZD where IOBDZD_MC = 表单名`，取 `MARK/HTABLE/FTABLE/BH/TAB1/TAB2/TAB3`。**`MARK` 非空 → 走动态单据**（`OpenBillStand`）。
3. 否则查 `IOJCBDZD where IOJCBDZD_MC = 表单名` 的 `IOJCBDZD_BTYPE`：`'1'` → `UForm1` 单表；`'2'` → `UForm2` 分类树。
4. 三个分支都不命中 → **`return false`，什么都不发生**：没有报错、没有窗口。菜单项点了没反应，通常就是这里。

- **【硬规则 0.2.1】** 第 1 步的键是 **`SYSWSPACE_MC = 角色列名 + 表单名`** 的字符串拼接，不是单独的 `SYSWSPACE_MC`。角色列名本身又作为列名出现在同一条 SQL 里（`GetBoolTgValue(..., strRole, ...)`）。角色列不存在 → `_com_error` 被吞、返回 false → **静默放行**；这会让“本该受限的表单对所有人开放”，而不是报错。
- **【硬规则 0.2.2】** `IOBDZD_MARK` 为空串会让第 2 步失败并回落到 `IOJCBDZD`。一张只有 `IOBDZD` 行、`MARK` 却为空的单据**不会走单据分支**，而是继续找 `IOJCBDZD_BTYPE`，最终 `return false`。
- **【硬规则 0.2.3】** `CBill::InitForm` 在 `IOBDZD where IOBDZD_MC=表单名` **无行时 `return false`**（`adoEOF` 判定），并且它读的是 `IOBDZD_HTABLE`/`FTABLE`/`BH`/`TAB1..3` 六列——列缺失同样让 `OpenRecordsetStatic` 失败。

---

## 1. 字段投影契约：`GetDataField` / `GetCrossTable`

### 1.1 源码拼出的确切形状

```sql
-- GetDataField(表名, 过滤, bShowCovertName)
select *, case when 切换=1 then IOJCBDZD_VKEY else 字段名 end as 字段名1
from v_tbcolumn with(nolock) where 表名='<表名>' <过滤> order by 顺序
```

逐行生成投影（`bShowCovertName=true`，即维护页/查询页主路径）：

- `标识` 非空 → `sum( case FF_BS when '<标识>' then <字段名1> else 0 end) as [<显示名>]`
- 否则 `GLZD<>''` 且 `切换=1` → `<LMark.><IOJCBDZD_BYZD> as [<显示名>]`
- 否则 → `<RMark.><字段名1> as [<显示名>]`
- `bShowCovertName=false` → `<LMark.><字段名1> as [<显示名>]`（不区分 `切换`）

```sql
-- GetCrossTable(表单名)
select * from V_TbColumn where len(GLZD)>0 and 表名='<表单名>' and PO<=2 order by PO,顺序
```

FROM 来源按顺序回退，第一个非空胜出：

1. `IOBDZD` by `IOBDZD_MC` → `IOBDZD_HTable`（+ 若有 `IOBDZD_FTable`：`HTable left join FTable on HVkey=FVkey`）
2. `IOPOPDLG` by `IOPOPDLG_MC` → `IOPOPDLG_JOINSTR`
3. `IOJCBDZD` by `IOJCBDZD_MC` → `IOJCBDZD_Table`

再对每条 `GLZD` 非空行追加 JOIN：

- `LMark` 为空 → ` left join <IOJCBDZD_Table> on [<RMark>.]<字段名>=<IOJCBDZD_VKEY>`（**关联表不加别名**）
- `LMark` 非空 → ` left join <IOJCBDZD_Table> as <LMark> on [<RMark>.]<字段名>=<LMark>.<IOJCBDZD_VKEY>`

### 1.2 硬规则

- **【硬规则 1.2.1】** 投影行 `显示名` 为空 → 源码弹“转译失败”并**返回空字段串**，最终生成 `SELECT  FROM …`。每一条 `v_tbcolumn` 行的 `显示名`、`标签名` 都必须非空。
- **【硬规则 1.2.2】** `切换=0` 分支下 `字段名` 为空 → 弹“数据读取失败”并返回空串。`字段名` 必须非空，且不得用中文标签顶替。
- **【硬规则 1.2.3】** `标识` 非空即 FF_BS 开关（`FF_BS` 是业务表里的物理列）。普通字段 `标识` 必须保持 `NULL`；字符串 `'0'` 也会触发 `sum(case FF_BS …)`。
- **【硬规则 1.2.4】** `GLZD` 非空的每一行，`字段名`、`IOJCBDZD_Table`、`IOJCBDZD_VKEY`、`LMark`、`RMark` 都必须有值且闭合；空别名写 `''` 而不是 `NULL`（源码不做 Trim/NULL 兜底，`NULL` 会被当成有值）。任一为空 → JOIN 不可执行。
- **【硬规则 1.2.5】** `GetCrossTable` 的 `IOBDZD` 分支只认 `IOBDZD_MC`。表单名在 `IOBDZD` 里不存在时，若 `IOJCBDZD_MC` 也查不到表，FROM 为空 → 生成 `FROM )`。
- **【硬规则 1.2.6】** `GetDataField` 的 `表名` 与物理表无关：它是 `SYS_TbColumn.表名`，可以是可见表单名、`<表单名>查询`、或 `BTYPE=2` 的 `LBNAME`/`MC`。`IOJCBDZD_MC`、`IOBDZD_MC`、`SYSWSPACE_MC`、`SYS_TbColumn.表名`、`sysmenu.sysmenu_bdmc` 必须使用**同一个可见名**。
- **【硬规则 1.2.7】** 动态单据必须有独立的 `<表单名>查询` 字段集；`StartSP` 与单据查询页读取的是 `GetDataField(<表单名>查询, '', true)` 配 `GetCrossTable(<表单名>)`。缺这套元数据 → 查询页/审批条件 SQL 报列名无效。
- **【硬规则 1.2.8】** `GetDataField` 与 `GetCrossTable` 是**两条独立查询**：前者按 `表名` 取字段清单，后者按 `表单名` 取 FROM 来源。`GetCrossTable` 只扫 `PO<=2` 且 `len(GLZD)>0` 的行——**`PO>=3` 的明细页签字段不参与跨表 JOIN**，它们的 `GLZD` 不会生成 JOIN。给第三个及以后页签写 `GLZD` 不会生效，也不会报错。
- **【硬规则 1.2.9】** `GetDataField` 里 `LMark` 与 `RMark` 的用法**不对称**：`LMark` 用于关联表别名（加在 `IOJCBDZD_BYZD`/`字段名` 前），`RMark` 只出现在 `切换` 为假的分支。`bShowCovertName=false` 时只认 `LMark`，`RMark` 被忽略。同一个字段在两条入口下投影可能不同，必须按调用点分别回放。
- **【硬规则 1.2.10】** 源码里同一查询写了三种大小写：`v_tbcolumn`、`V_TbColumn`、`V_TBCOLUMN`。它们必须在目标库里指向同一个可解析对象（视图或表），且库排序规则大小写不敏感。三者中任一被建成同名不同物的两个对象，会出现“有的界面正常、有的报列名无效”。

### 1.3 字段投影的其它入口（同一套元数据、不同投影）

| 入口 | 过滤 | 投影差异 |
|---|---|---|
| `GetDataField(表名, 过滤, true)` | 调用方给 | 见 1.1 |
| `GetDataField(表名, 过滤, false)` | 调用方给 | 只用 `LMark` 前缀，不做 `切换`/`BYZD` 转换 |
| `GetGroupField(表名, 过滤, true)` | 调用方给 | `标识` 非空的行**跳过**（不生成 `FF_BS` 聚合）；其余同 1.1 |
| `GetCrossTable` | 固定 `PO<=2` | FROM 来源 + `GLZD` JOIN |
| `GetCrossTableS` | 固定 `PO=1` | 同上，但只扫表头；`LMark` 为空分支**不加 `RMark` 前缀** |

- **【硬规则 1.3.1】** `GetGroupField` 对 `标识` 非空的行是**直接丢弃**而不是聚合。同一个字段集在报表分组路径下会少列，若报表按 `显示名` 找列会失败。含 `标识` 的元数据不能假定在所有入口都出现。
- **【硬规则 1.3.2】** `GetCrossTableS`（表头专用）在 `LMark` 为空时用 `字段名=IOJCBDZD_VKEY` 且**不加任何前缀**；`GetCrossTable` 在同一分支会加 `RMark.` 前缀。同一行元数据在两条路径生成的 JOIN 不同，回放时必须分开验证。

### 1.4 两种空来源症状的区分

| 生成结果 | 含义 |
|---|---|
| `select  from <合法 JOIN>` | 字段集为空：`SYS_TbColumn` 对该 `表名` 无行，或 `显示名`/`字段名` 为空导致提前返回 |
| `select <字段> from )` | `GetCrossTable` 返回空：`IOBDZD_MC` / `IOPOPDLG_MC` / `IOJCBDZD_MC` 三条回退都取不到表 |

---

## 2. 关联显示与帮助的双路由

- **编号输入行**：`GLZD=<关联路由>`、`切换=1`。物理列存编号；显示值来自 `IOJCBDZD_BYZD`；保存时源码执行
  `select <IOJCBDZD_VKEY> from <IOJCBDZD_TABLE> where <IOJCBDZD_BYZD>='<控件文本>'`。
- **【硬规则 2.1】** 该反查必须唯一命中。命中不到时源码返回 `""`，直接写成 `字段名=''`——**用户选了值，保存后编号却是空**。任何 `切换=1` 行都要验证 `BYZD` 值在业务表唯一，或至少有稳定的排序命中行。
- **【硬规则 2.2】** `帮助` 值走的是 `IOJCBDZD_BZBH`，与 `GLZD` 走的 `IOJCBDZD_MC` 是两条独立路由。帮助打不开、开了就关，先查 `IOJCBDZD_BZBH` 是否有该行，再看它的 `IOJCBDZD_VKEY`/`IOJCBDZD_BYZD`/`IOJCBDZD_TABLE` 是否非空——`CBaseItem::LoadData` 在 `VKEY` 为空时直接 `OnCancel()`（窗口一闪即关，无报错）。
- **【硬规则 2.3】** 帮助窗口的取数 SQL 是 `select <VKEY> as 编号,<BYZD> as 名称 from <TABLE> where 1=1 <FILTER> order by <VKEY>`。`TABLE` 为空 → 列名/对象名无效。
- **【软规则 2.4】** `帮助` 值为 `GYSBZ`/`KHBZ`（供应商/客户）和 `WLBZ`（物料）时走内置窗口，不读 `IOJCBDZD_TABLE`；这是写死的特例，不要为它们补 `IOJCBDZD` 表映射来“修好”帮助。
- **【硬规则 2.5】** 关联显示行（`GLZD=''`、只读、投影别名列）不是可选装饰：物理表里即使有同名 Name/规格列，也不得据此删除或改写关联行。

---

## 3. 表头控件创建契约（`CreateDlgItemWithArrayDateTime`，动态单据 `PO=1`）

源码按 `控件` 再按 `类型` 分派，生成不同控件类：

| `控件` | `类型` | 实际控件 |
|---|---|---|
| `S` | 任意 | `CMystatic` 静态文本（无输入） |
| `RG` | 任意 | 单选按钮（`WS_GROUP`） |
| `R` | 任意 | 单选按钮 |
| `C` | 任意 | 复选框（`BS_AUTOCHECKBOX`） |
| 其它（`E`/`EM`） | `D` | `CDataEdit`，`showtype=1`：日期格式框，**右键弹日历**；源码强制 `bReadyonly=true`，键盘输入被 `OnChar` 拦截（仅 Ctrl 组合可输入） |
| 其它 | `DT` | `CMyDateTimePicker`，格式 `yyyy-MM-dd HH:mm`，初始未勾选 |
| `EM` | 任意 | 多行编辑框（`ES_MULTILINE|WS_VSCROLL`，左对齐） |
| 其它 | 其它（含 `S`） | 普通编辑框，`showtype=2`：**右键按 `帮助` 打开选择窗口** |

- **【硬规则 3.1】** `D` 是“日期格式框且只读”，不是日期选择器；需要可直接输入的日期时间用 `DT`。把日期字段建成 `D` 会得到右键才能选的只读框，把 `DT` 建成普通字段会丢掉时间选择器。控件码只能按同版本源码 + 同库工作单据决定，不能按物理列类型推断。
- **【硬规则 3.2】** `类型`/`字段名`/`标签名`/`控件` 被直接转成字符串；`显示`、`必填`、`只读` 被直接转 `bool`；`RID` 被转 `(int)(double)`。这些列出现 `NULL` 会抛异常并被 `catch(...)` 吞掉，最终只显示“控件初始化时出错!”——**表单打不开，菜单已建好**。每个 `PO=1` 行都必须有非空 `控件`、`类型`、`字段名`、`标签名`、`RID`，以及非空布尔标志和布局值。
- **【硬规则 3.3】** `左坐标/顶坐标/宽度/高度` 为空时回退到 `40/60/100/80`，多个空坐标字段会叠在同一处；可见控件必须有正数宽高。
- **【硬规则 3.4】** 源码还会按**角色名**取同名列（`GetCollect(<当前角色>)`）决定可见性。角色列缺失会被内层 `catch(...)` 吞掉，不报错；但若误把权限列当表单标志填错，会静默隐藏字段。
- **【硬规则 3.5】** 创建控件用的 `RID` 必须能通过 `GetDlgItem(RID)` 命中；`GenUpdateSqlFromForm` 对 `主键=1` 行直接 `GetDlgItem(RID)->...`，`RID` 指向不存在的控件会在保存时崩溃。

---

## 4. 表头字段名后缀锚点

`CreateDlgItemWithArrayDateTime` 通过 `字段名.Find("_XXX") > 0` 定位运行期锚点控件，顺序靠后（`顺序` 更大）的同后缀行会**覆盖**前者：

`_ZY`（摘要/备注）、`_ID`、`_PJLX`、`_SHBZ`、`_SHR`、`_SJDH`、`_YWRQ`、`_ZDR`。

- **【硬规则 4.1】** 每个锚点后缀在 `PO=1` 里必须**恰好一条**行，且 `字段名` 必须以该后缀结尾。两条 `_SJDH` 会让单号控件指向后写入的那条。
- **【硬规则 4.2】** `Find` 用的是子串匹配，不是后缀匹配。任何包含 `_ID`、`_ZY`、`_SJDH` 等子串的普通字段名都会抢锚点；新增字段前必须先跑一遍已存在的 `PO=1` 字段名做子串冲突检查。
- **【硬规则 4.3】** `顺序` 决定覆盖顺序，因此锚点行在重排 `顺序` 时不能被推到冲突位置。

---

## 5. 明细页与翻前单（`PageRowsTab`）

- **【硬规则 5.1】** 每个明细页 `PO=iPos+1`（`iPos` 为 0 基页签下标），所以 `PO=2` 是第一个明细页签。`GetDataField(表单名, ' and PO=<n> ', true)` 为空时 `InitForm` 直接 `return false`，页签空白。
- **【硬规则 5.2】** 明细表名不是从 `IOBDZD` 读的，而是取该 `PO` 组**`顺序=1` 那条字段的 `字段名`**，再截取第一个 `_` 之前的部分。`顺序=1` 的字段名必须是 `<明细物理表名>_xxx`；截不出前缀 → 页签无法定位物理表。
- **【硬规则 5.3】** 明细 `顺序` 同时是 Grid 列下标（`GenInsertSqlFromGrid` 用 `grid->GetValueMatrix(rowsel, (int)顺序)`）。必须是 `1..n` 连续、无重复、无空值，且首列占 1。
- **【硬规则 5.4】** 翻前单 SQL 写死两个别名：
  `select * from (select <明细字段> from <跨表来源>) t where 单号='<单号>' order by cast(分录号 as int)`
  **维护页**明细字段集必须投影出别名 `单号` 和 `分录号`，且 `分录号` 必须能 `cast(... as int)`（非空、数字）。`分录号` 为空或含非数字 → 直接 SQL 错误。Grid 也按 `GetColPos("单号")` 定位列头。**查询页**明细如果与表头同名单号，必须改用去重别名（例如 `明细单号`），因为查询页被包在派生表里，别名不能重复；不要把维护页和查询页的别名规则混用。
- **【硬规则 5.5】** 明细单元格行为由 Grid 字段决定（`类型`、`帮助`、`管道字符`、`只读`、`列宽`、关联映射），`控件` 在明细里只是保留字段，不是编辑器开关。
- **【硬规则 5.6】** `类型` 在明细里决定保存格式：`S`/`T` 文本、`M` 下拉框（**保存的是索引，不是文本**）、`D` 日期文本、`DT` 日期时间控件、`C`/`R` 复选框（1/0）、`N*` 数值精度（`NF`=发票精度、`NB`/`NJ`/`N2`=2、`ND`=单价精度、`NZ`=数量精度、`N1..N6`=定点）。其它值落到文本分支——不报错，但按文本写入。

---

## 6. 单据路由、编号、审核与菜单

- **【硬规则 6.1】** `CBill::InitForm` 由表单名取 `IOBDZD_BH`，写入 `billdata.strPJLX`，并生成固定过滤器 ` and <表头表>_PJLX='<BH>'`。所有表头读写都带这个条件。**物理表头表必须有 `<表头表>_PJLX` 列，且每张单都写入正确的 `IOBDZD_BH`**；否则单据打开为空白、保存后“查不到自己”。
- **【硬规则 6.2】** 单号由 `GenDanhao` → `exec dbo.[PRD_GETDANHAO] '<表单名>', @dat output`。过程缺失、`IOBDZD_FORMAT` 为空、月份/基数状态未初始化都会返回空串（不抛错）。`IOBDZD_BH` 还必须能作为唯一键反查 `IOBDZD_HTABLE`/`IOBDZD_MC`（`StartSP`/审批路径按 `IOBDZD_BH` 查），重复 `BH` 会静默取到别人的表。
- **【硬规则 6.3】** 审核状态：源码多处直接比较 `<表头>_SHBZ="1"` 判断“已审核”。`SHBZ` 的取值与含义必须来自同版本 `LSDJZT` 字典 + `GLZD=LSDJZT_BH`；写成 `bit`/`C` 复选框或改掉 `1` 的含义会破坏审核、撤审、删除保护。
- **【硬规则 6.4】** `BDJB` 的匹配键是**可见表单名**（`BDJB_PJLX = <表单名>`），不是 `IOBDZD_BH`。审核/撤审脚本写错键 → 零命中、无任何提示。
- **【硬规则 6.5】** 审批流路径（`StartSP`）引用固定表 `SH1`、`SH2`、`SHDY1`、`SHDY2` 和 `<表头表>_SPID`。注册了审批定义（`SHDY1_BDDJ = IOBDZD_BH`）却没有这些表/列，会在提交时失败。
- **【硬规则 6.6】** 按钮由 `sysmenu` 按 `sysmenu_bdmc = <表单名>` 构建，并按 `sysmenu_topfloor/sysmenu_submenu` 分成三组菜单；同时把 `IOYYGX`（`IOYYGX_BDMC=<表单名>`、`IOYYGX_YXBZ=1`、`GLTJ` 非空）的 `IOYYGX_CZMC` 合并进最后一级。缺行 → 按钮消失；`sysmenu_uid`/`sysmenu_pmenu` 写成空字符串而非空格会改变菜单挂载。
- **【硬规则 6.7】** `BTYPE=1/UForm1` 的搜索按钮写死 `charindex('<输入>', 码表编号)>0` 和 `GetDataField(表名,' ',true)`。表单字段集必须能投影出别名 `码表编号`（以及 `码表` 路由下的 `码表名称`），否则搜索恒定报“列名 '码表编号' 无效”。这是**客户端范围**问题：不得用新增物理列去伪装。初始加载成功不代表搜索可用，两条路径必须分别回放。
- **【硬规则 6.8】** `BTYPE=1` 的 `顺序` 是真实 0 基列下标（`UForm1` 与 `BTYPE=2` 右侧数据集都用 `顺序` 直接做 `GetValueMatrix/GetTextMatrix` 的列号）；`BTYPE=2` 右侧数据集还写死 `<右侧表>_LBBH='<树节点编号>'` 过滤。动态单据明细是 `1..n`。两套规则不可互换。

---

## 6A. 工作区、角色与权限（`SYSWSPACE`）

工作区不是“菜单树装饰”，它是**表单可见性和打开权限的唯一来源**，而且规则全部写死在 `MainFrm.cpp` / `WorkspaceBar*.cpp` 的 SQL 里。

源码实际执行的过滤（`CMainFrame::BuildWorkspaceTree` 与 `CWorkspaceBar::AddSubTree` 一类）：

```sql
select ... from SYSWSPACE
where len(SYSWSPACE_BH) in (4,6,8,10) and SYSWSPACE_BTN=0
  and SYSWSPACE_MX=1 and [<角色列>]=1 and SYSWSPACE_MC like '%<搜索词>%'
order by SYSWSPACE_MC
```

- **【硬规则 6A.1】** `SYSWSPACE_BH` 的**长度就是层级**：`4` = 一级节点，`6` = 二级，`8` = 三级，`10` = 四级。子节点的 `BH` 必须是父节点 `BH` 加两位后缀，父节点由 `a.Mid(0, a.GetLength()-2)` 反查。长度不在 `{4,6,8,10}` 的节点**永远不出现在树里**——不报错，只是看不见。
- **【硬规则 6A.2】** `SYSWSPACE_MX=1` 才是叶子（可打开的表单）；`MX=0` 是分组节点。`SYSWSPACE_BTN=0` 才是树节点，`BTN<>0` 是按钮类记录，不参与树构建。
- **【硬规则 6A.3】** 可见性由**角色列**决定：`[<角色列>]=1`。角色列名来自登录用户的 `strRole`，直接作为列名拼进 SQL。列不存在 → `_com_error` → 该节点对所有人不可见（树构建里是静默失败）。角色列必须真实存在于 `SYSWSPACE`。
- **【硬规则 6A.4】** `SYSWSPACE_MC` 同时承担两个职责：**树的显示文本**，以及 `AutoOpen` 权限判定里的 `SYSWSPACE_MC = 角色列名 + 表单名`。它必须与 `IOBDZD_MC`/`IOJCBDZD_MC`/`SYS_TbColumn.表名` 同名；改显示文本等于改权限键。
- **【硬规则 6A.5】** `SYSWSPACE_LOC` 区分工作区类别（源码中出现 `LOC=1`、`LOC=3` 两套查询）。新节点必须放进与同类表单相同的 `LOC`，否则挂到另一棵树。
- **【硬规则 6A.6】** 用户报表叶子额外要求 `SYSWSPACE_BH like '30%'`。报表类叶子放错编号段，右键/报表菜单找不到它。
- **【硬规则 6A.7】** 权限查询失败是**放行**而非拒绝（`IsValid` 在 `GetBoolTgValue` 返回 false 时 `return true`）。因此“权限没配好”在 `ADMIN` 账号下完全看不出来，只在受限角色下暴露为“看不见”或“点不开”。任何权限结论必须在**非 ADMIN 角色**下验证。

---

## 6B. 其它被硬编码引用的系统表

这些表名写死在已编译代码里，缺表或缺列会以“某个功能没反应/报列名无效”的形式出现：

| 表 | 硬编码键列 | 取用列 | 消费方 |
|---|---|---|---|
| `report` | `report_pjlx` = 表单名 | `report_mc` | `CBill` 打印按钮列表、`DlgChoosePrint`、`ReportGdtc` |
| `SYSFMA` | `SYSFMA_MC` + `SYSFMA_CFX` | `SYSFMA_mdx`、`SYSFMA_GS`、`SYSFMA_fxbz` | `CGridForm` 自定义计算公式 |
| `SYSYHZD` | `SYSYHZD_BH` | `SYSYHZD_MC`、`SYSYHZD_YXBZ` | `SysAuthority` 角色/用户列表 |
| `SYSMONTH` | `SYSMONTH_QJ` | `SYSMONTH_BEGIN`、`SYSMONTH_END` | 会计期间起止日期，几乎所有报表 |
| `LSZTXX` | `LSZTXX_DQQJ` | — | 当前期间，与 `SYSMONTH` 联接 |
| `SYSFILTERSET` | `SYSFILTERSET_TBNAME` + `_NO` | `_logic/_name/_relation/_value/_L/_R` | `CChooseScreen` 高级筛选方案 |
| `SYS_TbColumn` | 表名 + **角色列名** | 全部 | `PrintView` 隐藏无权限列、`GroupSet` 分组汇总字段 |
| `V_BALL` / `V_BALLWL` | `FF_WLBH` / `FF_DWBH` | `FF_SL`、`FF_JE`、`FF_FLAG`、`FF_SHBZ` … | 库存/往来余额视图，MRP、报表、选货窗口直接查 |

- **【硬规则 6B.1】** 这些表都是**跨模块共享**的：注册一张新单据时如果顺手改了 `SYSMONTH`、`SYSYHZD` 或 `SYSFILTERSET`，影响面远超该单据。默认不动；确需修改时按全库影响面评估。
- **【硬规则 6B.2】** `report` 的键是 `report_pjlx = 表单名`（与 `BDJB_PJLX` 同一约定）。打印按钮为空 = 该表单没有 `report` 行，不是权限问题。
- **【硬规则 6B.3】** `PrintView` 与 `GroupSet` 都把**当前角色名当列名**查 `SYS_TbColumn`（`... and [<角色>]=0`）。因此 `SYS_TbColumn` 的角色列缺失会让“隐藏无权限列/分组字段”静默失效，而不是报错。
- **【硬规则 6B.4】** `V_BALL`/`V_BALLWL` 是视图，列名一律 `FF_` 前缀，且 `FF_FLAG` 是红蓝字方向标志（`sum(FF_SL*FF_FLAG)`）。这些列由视图定义决定，不是业务表列；修业务表不会改变视图列。

---

## 7. 建一个“合格表格/表单”的 fail-closed 清单

生成 `forward.sql` 之前，逐条给出证据；任何一条拿不到证据就停，不要部署：

0. 已从 `SGSoft.vcxproj` 确认本次涉及的每个界面入口都在**已编译文件**里，且用的是 `v_tbcolumn`+`PO` 还是别的模型（见 0.1 与 8.1）。
1. `DB_NAME()`、`@@SERVERNAME`、排序规则（必须 CI）已记录。
2. 可见名在 `IOJCBDZD_MC`、`IOBDZD_MC`、`SYS_TbColumn.表名`、`SYSWSPACE_MC`、`sysmenu_bdmc` 五处一致且全局唯一。
3. 路由键闭合：`GLZD → IOJCBDZD_MC`、`帮助 → IOJCBDZD_BZBH`、`IOBDZD_* → IOBDZD_MC/BH` 三组各自唯一命中。
4. `v_tbcolumn` 每行 `字段名`、`显示名`、`标签名` 非空；`标识` 为 `NULL`（除非同版本源码证明是 FF_BS）。
5. `GLZD` 非空行的 `LMark`/`RMark` 为 `''` 或有效别名，`IOJCBDZD_Table/VKEY/BYZD` 非空，生成的 JOIN 可执行；且该行 `PO<=2`（否则 JOIN 不生成）。
6. 表头锚点后缀 `_ID/_SJDH/_YWRQ/_PJLX/_SHBZ/_ZDR/_SHR/_ZY` 各一条，且无其它字段名子串冲突。
7. `PO=1` 每行 `控件`/`类型`/`RID`/布尔标志非空；控件码来自同版本源码 + 同库工作单据。
8. 明细 `PO` 组 `顺序` 为 `1..n` 连续无重复，`顺序=1` 的 `字段名` 以 `<明细表名>_` 开头。
9. 明细字段集投影出 `单号`、`分录号`（且 `分录号` 可 `cast as int`）。
10. 独立 `<表单名>查询` 字段集存在，`显示名` 唯一，含 `单号`、`日期` 锚点。
11. `CBill` 固定字段卡齐全（`_ID/_YWRQ/_PJLX/_SJDH/_PRINT/_SHBZ/_ZDR/_SHR/_ZY` 与明细 `_ID/_SJDH/_FLH`），物理列与元数据同时存在。
12. `IOBDZD` 的 `BH`/`MARK`/`FORMAT`/`HTABLE`/`FTable`/`Vkey`/`TAB1..3` 齐全且唯一；`MARK` 非空（决定 `AutoOpen` 走不走单据分支）；编号过程 `PRD_GETDANHAO` 存在。
13. `SHDY1/SHDY2/SH1/SH2/<表头>_SPID` 只在确实注册审批流时要求。
14. `BDJB_PJLX` 用可见表单名；审核/撤审成对存在。
15. `sysmenu` 七个标准按钮行齐全。
16. `SYSWSPACE`：`BH` 长度在 `{4,6,8,10}`、父节点存在且为其前缀、`MX=1`、`BTN=0`、`LOC` 与同类一致；每个角色列真实存在并在**非 ADMIN 角色**下验证过可见性与 `AutoOpen` 放行。
17. 需要打印时 `report` 有 `report_pjlx = 表单名` 行；需要期间过滤时 `SYSMONTH`/`LSZTXX` 有当前期间行。
18. 空来源回放：`SELECT <GetDataField> FROM <GetCrossTable> WHERE 1=2` 与维护页、查询页、翻前单三种包装形状都能解析并返回 0 行。

---

## 8. 症状 → 根因 → 最小只读检查

| 症状 | 根因 | 只读检查 |
|---|---|---|
| 弹出“转译失败 / 数据读取失败”，随后 SQL 报错 | `显示名` 或 `字段名` 为空，`GetDataField` 提前返回 `""` | `v_tbcolumn` 该 `表名` 行里 `显示名`/`字段名` 为空或 `IS NULL` 的行 |
| 单据标题 SQL 语法错误，`FROM` 后为空 | `IOBDZD_MC`/`IOPOPDLG_MC`/`IOJCBDZD_MC` 三条回退全空 | 按上述三个键分别查表；检查 `GLZD` 行的 `LMark/RMark` 是否 `NULL` |
| `SELECT  FROM <合法 JOIN>` | 字段集为空或提前返回 | `SYS_TbColumn` 该 `表名` 行数；`显示名`/`字段名` 空值数 |
| 打开单据报“控件初始化时出错!” | `PO=1` 某行 `控件`/`类型`/`RID`/`显示`/`必填`/`只读` 为 `NULL` | `PO=1` 行按 `顺序` 列出上述列的空值分布 |
| 表头某字段位置叠在一起 | `左坐标/顶坐标/宽度/高度` 为空 | 同上，列出空坐标行 |
| 日期字段不能键盘输入 | `类型='D'` 走只读日期框（右键日历） | 确认是否应为 `DT` |
| 明细页签空白 | 该 `PO` 的 `GetDataField` 返回空 | `SYS_TbColumn` 该 `(表名,PO)` 行数 |
| 翻前单/明细 SQL 报错 | 缺 `单号`/`分录号` 别名，或 `分录号` 不能 `cast as int` | 回放 `select * from (select … ) t where 单号=… order by cast(分录号 as int)` |
| 保存后关联编号变空 | `切换=1` 反查 `BYZD→VKEY` 未唯一命中 | 用控件显示值反查业务表 `BYZD` 列，检查行数与空值 |
| 帮助窗口一闪即关 | `IOJCBDZD_BZBH` 行的 `IOJCBDZD_VKEY` 为空 | 按 `帮助` 值查 `IOJCBDZD_BZBH`，检查 `VKEY/BYZD/TABLE` |
| 搜索恒报“列名 '码表编号' 无效” | 字段集没有 `码表编号` 别名 | 回放 `OnSearch` 形状的 `charindex(…,码表编号)`；属客户端范围，不得新增业务列 |
| 单据保存后查不到 | 物理 `<表头>_PJLX` 未写 `IOBDZD_BH`，或 `BH` 不唯一 | 表头 `_PJLX` 空值分布；`IOBDZD_BH` 重复行 |
| 新单号为空 | `PRD_GETDANHAO` 缺失或 `IOBDZD_FORMAT` 空 | 过程是否存在；路由按 `IOBDZD_MC` 的 `FORMAT/BascData/CurMonth/ModifyDate` |
| 审核/撤审没反应 | `BDJB_PJLX` 用了 `IOBDZD_BH` 而不是可见表单名 | `BDJB_PJLX` 与 `IOBDZD_MC` 逐行比对 |
| 按钮缺失 | `sysmenu_bdmc` 不是可见表单名，或缺标准行 | `sysmenu` 该 `bdmc` 的行数与 `topfloor/submenu` 分组 |
| SQL 报“对象名无效”，同名对象存在 | 库排序规则为 `_CS_` | `DATABASEPROPERTYEX(DB_NAME(),'Collation')` |
| **点菜单完全没反应**（无报错、无窗口） | `AutoOpen` 四个分支全不命中：无 `IOBDZD_MARK`、无 `IOJCBDZD_BTYPE` | 按表单名分别查 `IOBDZD_MC` 与 `IOJCBDZD_MC`；确认 `IOBDZD_MARK` 非空 |
| 工作区里看不到表单节点 | `SYSWSPACE_BH` 长度不在 `{4,6,8,10}`，或 `MX<>1`/`BTN<>0`/角色列 `<>1` | `LEN(SYSWSPACE_BH)`、`MX`、`BTN`、各角色列 |
| 受限角色下点开提示“需要通过管理员授权” | `SYSWSPACE_MC = 角色名 + 表单名` 那行角色列为 0 | 按拼接名精确查该行 |
| 本该受限的表单所有人都能打开 | 角色列不存在导致权限查询异常被吞、按放行处理 | 确认角色列真实存在于 `SYSWSPACE` |
| 打印按钮列表为空 | `report` 无 `report_pjlx = 表单名` 行 | 按表单名查 `report` |
| 报表/打印缺少列或列不隐藏 | `PrintView` 按 `SYS_TbColumn.表头=0` + 角色列过滤 | `SYS_TbColumn` 的 `表头` 列与角色列是否存在 |
| 分组/汇总字段缺失 | `GroupSet` 丢弃 `标识` 非空的行 | 该 `表名` 下 `标识` 非空的行 |
| 报表按显示名找不到列 | 同一字段集在 `GetGroupField` 下少列 | 对照 `GetDataField` 与 `GetGroupField` 两次投影 |
| 会计期间/报表日期范围为空 | `SYSMONTH` 无 `SYSMONTH_QJ = 当前期间` 行，或 `LSZTXX_DQQJ` 不匹配 | `SYSMONTH` 与 `LSZTXX` 联接结果 |
| 高级筛选方案打不开或为空 | `SYSFILTERSET` 无该 `TBNAME`/`NO` 行 | 按 `SYSFILTERSET_TBNAME` 查 |
| 库存/往来金额对不上 | 视图 `V_BALL`/`V_BALLWL` 的 `FF_*` 列定义，而非业务表 | 读视图定义，确认 `FF_FLAG` 方向与 `FF_SHBZ` 过滤 |

### 8.1 排除法：先确认不是死代码

同一症状在**未编译**文件里可能有一套更“正确”的契约。例如 `Sale.cpp` 用 `v_fieldshow` + `strViewTable` + `表头=0/1` + 别名 `单号`/`fid`/`业务类型` 的一套完全不同的模型，但 `Sale.cpp` 不在编译列表里。若照它的契约去建表或补列，真机不会有任何变化。

因此每次定位前先做一次归属判断：这个症状对应的界面入口在**哪个已编译文件**里，该文件用的是 `v_tbcolumn` 还是 `v_fieldshow`，是 `PO` 还是 `表头`。两套模型不能混用。

---

## 9. 元数据取值契约（唯一权威）

**本节是 `类型`、`控件`、`顺序`、`RID`、`标识`、`列宽`、`主键`、`关键字段` 取值的唯一权威。** `document-form-contract.md` 与 `complex-form-fast-path.md` 只保留流程与清单，不再各自复述取值规则；若三者出现分歧，以本节为准。

### 9.1 `类型`（决定控件类、保存格式、网格编辑器）

源码取值分支（`SGSoft.cpp::CreateDlgItemWithArrayDateTime`、`GenInsertSqlFromForm`、`GenUpdateSqlFromForm`、`GenInsertSqlFromGrid`、`GenUpdateSqlFromGrid`）：

| `类型` | 表头控件 | 保存/更新时的取值 | 明细网格 |
|---|---|---|---|
| `S` / `T` | 普通编辑框 | 文本，转义 `'` | 文本 |
| `D` | `CDataEdit`，**只读日期格式框**（右键日历） | 文本，去掉 `.` | 文本 |
| `DT` | `CMyDateTimePicker`（`yyyy-MM-dd HH:mm`） | 未勾选写 `null`，否则 `yyyy-MM-dd HH:mm:00` | 日期时间控件 |
| `M` | （表头少见） | **保存下拉索引，不是文本** | 下拉框，保存索引 |
| `C` / `R` | 复选框（`C` 表头分支） | `1` / `0` | 复选框 `1`/`0` |
| `N*` | 数值 | 按精度格式化 | 按精度格式化 |
| 其它 | 普通编辑框 | 按文本处理（不报错） | 按文本处理 |

`N*` 精度映射：`NF`=发票精度、`NB`/`NJ`/`N2`=2、`NW`=4、`ND`=单价精度、`NZ`=数量精度、`N1..N6`=定点 1..6 位，其它 `N*`=0。

**新生成元数据的硬规则：**

- **【硬规则 9.1.1】** 物理 `date`/`datetime`/`datetime2` → `类型='D'`；其余 → `类型='S'`。不得按 bit、精度、标签或布局推断其它值。
- **【硬规则 9.1.2】** 需要键盘输入或带时间的选择器时用 `DT`，不要用 `D`——`D` 在表头是只读框，只有右键日历能改值（`CDataEdit::OnChar` 拦截键盘，仅 Ctrl 组合可输入）。
- **【硬规则 9.1.3】** 存量修复只有在同版本源码证据下才能保留非默认 `类型`（例如既有 `N*`/`C` 业务字段），并在独立逐字段契约中记录；不得用一个默认值无条件覆盖整列。

### 9.2 `控件`（仅表头 `PO=1` 参与控件创建）

| `控件` | 生成控件 |
|---|---|
| `S` | `CMystatic` 静态文本（无输入） |
| `RG` | 单选按钮（带 `WS_GROUP`） |
| `R` | 单选按钮 |
| `C` | 复选框 |
| `E` | 普通编辑框（默认） |
| `EM` | 多行编辑框（`ES_MULTILINE|WS_VSCROLL`，左对齐） |
| 其它 | 落到普通编辑框分支 |

- **【硬规则 9.2.1】** 普通字段 `控件='E'`；字段名以 `_PJLX` 结尾的凭证类型字段 `控件='S'`。两者都必须在**维护页和查询页**同时成立。
- **【硬规则 9.2.2】** 明细 Grid 的单元格编辑器由 `类型`、`帮助`、`管道字符`、`只读`、`列宽`、关联映射决定，`控件` 在明细里只是保留字段。
- **【硬规则 9.2.3】** `PO=1` 每一行（含隐藏 ID 行）都必须有非空 `控件`；为 `NULL` 会在控件创建时抛异常并被吞掉，表单打不开。

### 9.3 `顺序`

- **【硬规则 9.3.1】** 动态单据（`IOBDZD`）：每个 `(表名, PO)` 组编译后重排为 `1..n` 连续、无重复、无空值、不跨 `PO` 复用。
- **【硬规则 9.3.2】** `BTYPE=1/UForm1`：每个 `(表名, PO)` 组必须是 `0..n-1`，隐藏主键行占 `0`。**两套规则不可互换。**
- **【硬规则 9.3.3】** 明细页 `顺序` 同时是 Grid 列下标；表头 `顺序` 还决定锚点覆盖顺序（见第 4 节）。
- **【硬规则 9.3.4】** `PageRowsTab` 用 `顺序=1` 那条字段的 `字段名` 前缀推导明细物理表名（见第 5 节）。

### 9.4 `RID`

- **【硬规则 9.4.1】** 维护页与查询页全体行内为正整数且唯一；新部署按目标库当前 `MAX(RID)+offset` 在事务内分配，不写死跨环境数字、不写 `NULL`。
- **【硬规则 9.4.2】** `RID` 是 `GetDlgItem(RID)` 的控件 ID：`GenUpdateSqlFromForm` 对 `主键=1` 行直接取控件，`RID` 指向不存在的控件会在保存时崩溃。
- **【硬规则 9.4.3】** 表头锚点字段（`_ID/_SJDH/_YWRQ/_PJLX/_SHBZ/_ZDR/_SHR/_ZY`）的 `RID` 会被写入 `HeaderRIDOut` 供运行期使用（见第 4 节）。

### 9.5 `标识`（`FF_BS` 开关）

- **【硬规则 9.5.1】** 普通元数据行 `标识` 必须为 `NULL`。非空（含字符串 `'0'`）会让投影变成 `sum( case FF_BS when '<标识>' then <字段> else 0 end) as [<显示名>]`，要求业务表存在物理列 `FF_BS`。
- **【硬规则 9.5.2】** `GetGroupField` 对 `标识` 非空的行是**直接丢弃**而非聚合；同一字段集在报表分组路径下会少列。
- **【硬规则 9.5.3】** 只有当同版本源码与工作单据证明该行确实是 `FF_BS` 生产者时才填写。

### 9.6 `列宽` 与 `宽度`（两套独立契约）

- **【硬规则 9.6.1】** `宽度` 是维护页控件外框宽度，`列宽` 是网格列宽，两者独立计算，不得互相复制。
- **【硬规则 9.6.2】** 首屏最小宽度按可见 `标签名` 计算，统一用 `scripts/metadata_width.py`：3 个汉字 = `840`，1 个全角字符 = `280`，ASCII 按半宽单元计，结果按 `15` 单位向上取整（4 个汉字 → `1125`）。低于标签最小宽度必须阻断。
- **【硬规则 9.6.3】** 新建元数据默认取标签宽度；显式更宽可保留；不得用 `100` 回退值或参考单据的内容宽度代替。
- **【硬规则 9.6.4】** `*_PJLX` 的宽度不是标签宽度：按当前库最长 `IOBDZD_MC` 显示值（`GLZD=IOBDZD_BH` + `IOJCBDZD_BYZD=IOBDZD_MC`）加同版本字体/DPI 余量实测，维护页 `宽度` 与查询页 `列宽` 分别计算；装不下必须阻断。

### 9.7 `主键` 与 `关键字段`

- **【硬规则 9.7.1】** 每个 `(表名, PO)` 组**恰好一行** `主键=1`，不支持复合元数据主键。
- **【硬规则 9.7.2】** `关键字段` 必须显式指定，不得默认继承 identity 主键；明细页按运行需要至少一个业务输入字段为 `关键字段=1`。
- **【硬规则 9.7.3】** 查询页全体字段**恰好一行** `关键字段=1`。
- **【硬规则 9.7.4】** 查询页的 `显示名`（派生表别名）必须唯一，否则分页/筛选包装 SQL 失败。

### 9.8 锚点与保留后缀

- **【硬规则 9.8.1】** 表头锚点后缀 `_ID/_SJDH/_YWRQ/_PJLX/_SHBZ/_ZDR/_SHR/_ZY` 各恰好一条，且 `字段名` 必须以该后缀结尾。
- **【硬规则 9.8.2】** 源码用子串匹配定位锚点，任何包含这些子串的普通字段名都会抢锚点（靠后的 `顺序` 获胜）。新增字段前必须做子串冲突扫描。
- **【硬规则 9.8.3】** 明细页固定别名：`单号`、`分录号`（且可 `cast as int`）；`分录号` 为空或非数字会直接 SQL 错误。

---

## 10. 与其他 reference 的分工

- **本文件**是**源码常量层**：键、别名、控件码、取值规则、SQL 拼接形状、症状对照。第 9 节是元数据取值的唯一权威。
- `references/document-form-contract.md` 是**动态单据流程层**：分型、建表、注册顺序、验收矩阵。
- `references/complex-form-fast-path.md` 是**四阶段执行层**：契约、前置、部署、验证与九步门禁。
- `references/basic-form-fast-path.md` 是 `BTYPE=1` 单表层。
- 本文件不能作为“客户端一定会显示某控件”的承诺：`_Font.h`、DPI、窗口尺寸和 `CBill::OnSize` 的运行期重排仍会改变最终几何。
- 静态可判定的部分已固化进 `scripts/validate_dynamic_bill_artifacts.py`：`PO=1` 锚点后缀唯一性与结尾匹配、`GLZD` 非空行的 `LMark/RMark` 不得为 `NULL`、`标识=NULL`、`类型`/`控件` 取值、`RID`/`顺序` 契约。需要连接目标库才能证明的部分（键唯一性、排序规则、`PRD_GETDANHAO`、权限行、真实 CRUD）仍必须按第 7 节清单单独取证。
