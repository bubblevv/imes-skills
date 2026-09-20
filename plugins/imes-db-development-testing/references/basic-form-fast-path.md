# BTYPE=1 单表基础资料快速通道

适用于：一张业务表对应一个 `IOJCBDZD_BTYPE=1` / `UForm1` 基础资料维护表单；没有表头/明细联动、审核/撤审、上下游单据、库存回写或独立查询页。

不适用于：`IOBDZD` 单据、`BTYPE=2/UForm2` 分类树、点检模板/记录单、需要审核状态或表头/表体统一保存的对象。遇到这些特征立即切换到 `document-form-contract.md`，不得套用本快速通道。

## 目标

把一次单表开发压缩成一个可审阅的字段契约，再由脚手架一次生成：

```text
contract.json
preflight.sql
forward.sql
verification.sql
crud-test.sql
rollback-preflight.sql
rollback.sql
README.md
```

生成器只生成脚本，不连接数据库、不写库。部署仍按目标项目的授权和安全门禁执行。角色列不需要逐个录入：默认把真实 `RID` 后的 `bit` 角色列、以及 `SYSWSPACE.admin` 后的权限列全部授权为 `1`，除非契约明确要求例外。`SYS_TbColumn.顺序` 是 `UForm1` 的实际 FlexGrid/字段访问下标，必须在每个 `(表名, PO)` 内从 `0` 开始连续编号为 `0..n-1`；隐藏 identity 主键通常是 `0`。不能使用 `1..n`，也不能保留旧序号。

## 最小输入契约

模型在第一次询问/确认时只收集以下信息；已经从 ER 图或目标库证实的内容不重复询问：

```json
{
  "expected_database": "TEST_DATABASE",
  "expected_server": "TEST_INSTANCE",
  "schema": "dbo",
  "table": "BASICTABLE",
  "visible_name": "示例基础资料",
  "route": {
    "bh": "BASICTABLE",
    "btype": 1,
    "vkey": "BASICTABLE_CODE",
    "byzd": "BASICTABLE_CODE,BASICTABLE_NAME"
  },
  "workspace": {
    "root_bh": "0014",
    "root_name": "示例根节点",
    "leaf_bh": "001401",
    "leaf_name": "示例基础资料",
    "loc": "1",
    "create_root": false
  },
  "fields": [
    {"name":"BASICTABLE_ID", "sql":"int identity(1,1)", "pk":true, "identity":true, "visible":false},
    {"name":"BASICTABLE_CODE", "sql":"varchar(20)", "nullable":false, "unique":true, "label":"编码"},
    {"name":"BASICTABLE_NAME", "sql":"varchar(50)", "nullable":false, "label":"名称"},
    {"name":"BASICTABLE_REMARK", "sql":"varchar(200)", "nullable":true, "label":"备注"}
  ]
}
```

可选字段属性：`default`、`label`、`width`、`required`、`readonly`、`filter`、`key_field`、`help`、`glzd`、`type`、`control`、`metadata_default`。不确定的字段类型、可空性、帮助关联或唯一性必须先查库/ER 或提一个问题，不得由脚手架猜测。

## 三阶段门禁

### 1. 前期准备（只读）

按固定顺序执行，避免无效扫描：

1. 核对 `DB_NAME()`、`@@SERVERNAME`、SQL Server 版本/兼容级别。
2. 检查物理表、业务编号、可见名称、`SYS_TbColumn.表名`、工作区编号是否冲突。
3. 检查 `IOJCBDZD`、`SYS_TbColumn`、`SYSWSPACE` 的实际列；确认 `nID` 为 identity、`RID` 为元数据权限边界、`admin` 为工作区权限边界。
4. 确认每个字段都能映射到 `sys.columns`，主键/唯一键/外键和帮助路由闭合。
5. 看到旧同名表单或旧工作区节点时 fail-closed：保留旧路由，改用批准的可见名称/编号；不覆盖、不删除。

前期通过条件：目标身份正确、无冲突、字段契约完整、表单确实属于 BTYPE=1。

### 2. 中期部署（最小写入）

1. 用同一份 `contract.json` 生成 forward/rollback/verification/CRUD 脚本，禁止手工复制字段元组。
2. forward 先建表，再建唯一键/外键，再写 `IOJCBDZD`、`SYS_TbColumn`、`SYSWSPACE`；整个变更使用显式事务，失败即回滚。
3. 不插入 `SYS_TbColumn.nID`；插入后用临时表捕获新行，再按 `RID` 之后的实际 bit 角色列授权为 `1`。
4. 新生成元数据中，物理 `date`、`datetime`、`datetime2` 字段的 `类型` 固定为 `D`，其他字段固定为 `S`；控件固定为 `E`。不得按 bit、数值精度或标签自由推导 `C/N/EM/R/RG` 等值；单表基础资料 `标识=NULL`。
5. 新生成可见字段的 `列宽` 按字段 `标签` 的完整显示宽度设置：使用 `scripts/metadata_width.py` 的统一规则，3 个汉字为 `840`，4 个汉字为 `1125`，ASCII 按半宽单元计算并按 `15` 单位向上取整；显式更宽值可以保留，显式更窄值必须阻断，不能把控件布局 `宽度` 或 `100` 回退值当作列宽。
6. 只有契约显式给出 `GLZD/帮助` 时才写帮助关联；帮助路由必须已有或在同一 forward 中明确生成，不能写悬空编码。
7. 部署命令固定使用目标环境自己的 SQL 客户端和 `-b` 失败退出；UTF-8 脚本用 `-f 65001`，避免中文脚本被 sqlcmd 静默跳过。不要把密码写入契约、脚本或日志。

推荐执行形状（连接参数由环境安全注入，不写死凭据）：

```text
sqlcmd -S <server> -d <database> -b -f 65001 -i preflight.sql
sqlcmd -S <server> -d <database> -b -f 65001 -i forward.sql
sqlcmd -S <server> -d <database> -b -f 65001 -i verification.sql
sqlcmd -S <server> -d <database> -b -f 65001 -i crud-test.sql
```

中期停止条件：任何 preflight 冲突、目标列不匹配、父节点缺失、未知权限边界、生成脚本静态校验失败，立即停止，不部分部署。

### 3. 后期校验（只读 + 隔离 CRUD）

按固定顺序执行：

1. `verification.sql`：身份、表/列/键、路由唯一性、元数据映射、控件/标识、帮助闭环、工作区父子层级、角色授权。
2. 执行客户端等价查询：按 `IOJCBDZD_TABLE/ VKEY/ BYZD` 生成的首屏查询必须成功，且 SQL 中不得出现 `FF_BS`。
3. `crud-test.sql`：插入、更新、重复唯一键、错误外键（如有）、事务回滚；测试值使用唯一前缀，最终断言零残留。
4. 只有上述脚本全部通过后，才提示重启客户端人工确认菜单、打开、新增、编辑、删除、帮助和筛选。

## 默认规则（仅在目标库契约已证实时使用）

- 新生成字段统一使用 `类型='S'`、`控件='E'`，不是把 SQL 类型、表体/表头或标签误分成不同默认值。
- `SYS_TbColumn` 的权限列从 `RID` 之后识别；`显示/新增/更新/关键字段` 等业务标志不是角色列。
- `SYSWSPACE` 的权限列从真实 `admin` 边界识别，默认全部授权为 `1`。
- identity 字段不写入业务新增值，也不写入 `SYS_TbColumn.nID`。
- 不为 BTYPE=1 基础资料凭空创建 `<可见名称>查询`、`IOBDZD`、`IOYYGX`、`IOPOPDLG`、`BDJB`。
- `BTYPE=1/UForm1` 的每个 `(表名, PO)` 组都必须满足 `MIN(顺序)=0`、`MAX(顺序)=COUNT(*)-1`、无重复、无 NULL；动态单据的 `PO=1/2/...` 顺序规则另行处理。

## 省 token 的执行格式

开发对话只保留一张“单表契约卡”：

```text
目标库/实例：<database>/<server>
物理表：<schema.table>
可见名/路由：<visible_name> / <BH>
工作区：<root BH>/<leaf BH>
字段：<name sql nullable key unique label help...>
已证实规则：<旧路由、角色边界、前缀、外键>
授权：<是否允许测试库写入>
```

如果契约卡完整且 preflight 没有冲突，直接生成并执行四件套；不要再次全文扫描仓库或重复询问已证实字段。
