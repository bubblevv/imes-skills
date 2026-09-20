# 既有动态单据参照快速路径

## 适用范围

用于已有 `IOBDZD` 单据通过 `IOYYGX`/`IOPOPDLG` 参照来源单据或来源数据，用户只要求：

- 调整参照过滤条件；
- 排除过期、失效或不满足来源状态的数据；
- 修复已有参照关系的配置值。

不用于新建动态单据、增加物理字段/元数据、修改审核回填、数量消耗或上下游生命周期。出现这些变化时，转读 `references/document-form-contract.md`。

## 最短闭环

### 1. 固定入口

先记录目标单据、参照操作名、来源单据、精确请求和是否允许写入。用户给出的操作名或关系行是第一入口，不先做全库 `IOYYGX`/`IOPOPDLG` 扫描。

### 2. 身份与关系

先执行：

```sql
SELECT DB_NAME() AS CurrentDatabase, @@SERVERNAME AS CurrentServer;
```

再按目标单据和操作名读取唯一 `IOYYGX` 行，至少确认：

- `IOYYGX_YXBZ=1`；
- `IOYYGX_CZLX`/`IOYYGX_BDLX` 与活动客户端分支一致；
- `IOYYGX_FROMTABLE`、`IOYYGX_TABLE`、`IOYYGX_GLTJ` 与来源路径一致；
- `IOYYGX_GLTJ` 中使用的别名和字段可由目标表、主从路由或已验证的回退关系解析。

只有当活动路径依赖回退来源时，才读取对应 `IOPOPDLG`。已有闭合的 `IOBDZD` 主从来源不需要重复发现无关关系。

### 3. 日期/状态语义

从 `sys.columns`、活动 SQL 和少量实际数据确认来源字段。不要仅凭“预测区间”“有效期”“截止日期”等中文名称猜测开始/结束列。

用户只要求“过期的不参照”时，最小过滤是结束日期条件：

```sql
AND (<ConfirmedEndDateColumn> IS NULL
     OR <ConfirmedEndDateColumn> >= CONVERT(date,GETDATE()))
```

这会保留未到期的未来数据；结束日期为空按未封闭处理。只有用户明确要求“当前日期必须落在整个区间内”或“未开始的不显示”时，才增加：

```sql
AND (<ConfirmedStartDateColumn> IS NULL
     OR <ConfirmedStartDateColumn> <= CONVERT(date,GETDATE()))
```

`GETDATE()` 使用 SQL Server 当前日期，不把部署日期写死。若业务要求使用客户端本地日期，必须先证明日期参数/时钟契约；不能在 SQL 中私自加减天数。

### 4. 预览

修改前必须同时得到：

1. 目标 `IOYYGX` 旧过滤值，且精确命中一行；
2. 原过滤条件的来源数量；
3. 新过滤条件的来源数量；
4. 将被排除的过期数量；
5. 代表性来源行的开始/结束日期、单号和分录号。

预览只读，不修改来源单据、目标单据、数量或状态。

### 5. 最小部署

只更新已有 `IOYYGX` 配置行，并满足：

- 数据库/实例门禁；
- `@@TRANCOUNT=0` 的干净会话；
- `UPDATE` 谓词使用部署前旧值，而不是目标新值；
- `@@ROWCOUNT=1`；
- 事务、失败回滚和反向 rollback；
- 部署后立即读取新值。

若同时包含 `ALTER TABLE`、视图刷新或依赖新增列的语句，把结构变更和后续引用拆成独立 SQL 批次；SQL Server 同一批次的编译可能看不到刚新增的列。目标表的 `IDENTITY` 列（例如关系/元数据技术 ID）由数据库自动生成，不能在 `INSERT` 中显式提供。

### 6. 验证

至少验证：

- 精确 `IOYYGX` 行为新过滤值；
- 来源查询的 `SELECT` 列表、JOIN、别名和结果集形状未变；
- 新过滤条件实际排除所有过期行；
- 未发生业务表写入；
- 客户端真实参照窗口是否已重新打开，必须单独报告。

## 何时停止快速路径

遇到以下任一情况，停止配置行修复并转完整动态单据契约：

- `IOYYGX` 不唯一、来源路由不闭合或旧值不唯一；
- 需要新增 `IOYYGX`、`IOPOPDLG`、`IOBDZD`、`SYS_TbColumn`、权限或生命周期行；
- 需要改变参照带出后的保存、数量消耗、回填、审核、撤审或上下游状态；
- 开始/结束日期或状态含义无法由 schema、活动 SQL 和数据证明；
- 客户端生成的来源 SQL 出现空字段列表、空 `FROM`、无效列、重复别名或悬空 JOIN。

快速路径降低重复调查，不降低目标身份、旧值、影响行数、事务、回滚和运行时 SQL 验证门禁。
