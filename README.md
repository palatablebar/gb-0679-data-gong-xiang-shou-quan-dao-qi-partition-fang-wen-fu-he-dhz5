# 数据共享授权到期与分区访问复核

供企业数据共享审计专员核对原始记录、处理差异并封存证据。

## 启动

```sh
docker compose up --build -d
docker compose exec -T app pytest -q
```

打开 http://localhost:18248 。首次进入自动运行仓内脏样例。工具条可重跑、切换样例或上传CSV。SQLite保存在命名卷records中，重建服务保留批次。

## 模块

- 1. 访问采信：`/accesses`，`/api/accesses`。
- 2. 资源映射：`/resources`，`/api/resources`。
- 3. 授权定版：`/grants`，`/api/grants`。
- 4. 冲突裁决：`/conflicts`，`/api/conflicts`。
- 5. 分区判定：`/partitions`，`/api/partitions`。
- 6. 访问对账：`/audit`，`/api/audit`。
- 7. 审计归档：`/seals`，`/api/seals`。
- 8. 特征回收：`/reclaims`，`/api/reclaims`（回收单 `/api/reclaims/orders`，证据 `/api/reclaims/orders/<id>/evidence`）。

## 核心规则

拒绝规则优先于允许，授权必须同时命中资源、分区和生效窗；显式拒绝不得被宽授权覆盖。

## 演示

1. 打开首页，核对当次计算、差异和隔离原因。
2. 切换模块查看源行及裁决依据。
3. 重跑相同样例，批次号与行数保持一致。
4. 复核后导出一份证据CSV。版本已变化的复核提交返回409。

## 输入与输出

输入列见 `docs/DATA-DICTIONARY.md`。项目包含dirty.csv、clean.csv、legacy.csv，统一走实际导入路径。上传限制4MB，拒绝不带时区的时间。业务键按字符串保留，Decimal参与计算，空值不会当零。

`POST /api/runs` 接收sample或csv；`GET /api/runs`返回历史批次；`POST /api/runs/<id>/review`需要version与decision；`GET /api/runs/<id>/archive`返回唯一证据导出。

## 范围

样例均为虚构。单机复核工具不连接生产系统；不提供登录、远端数据库或自动支付。内存计算按4MB输入上限控制，SQLite事务保证结果完整写入。

## 特征版本回收

营销模型的特征版本由多个共享分区拼成，单个授权到期不必整套撤回。M8按样本复算授权（采集时刻命中资源/分区/生效窗，裁决时刻仍有效），每个特征版本形成唯一回收单：

- 同时列清**必须撤回**（到期授权、显式拒绝、无授权覆盖）与**可继续使用**（有效允许）的样本，并逐授权标注有效/到期状态作为依据。
- 版本内仍有可使用样本时裁决**按样本回收**，全部失效才**整套版本撤回**，避免中断授权内训练样本与进行中的评估。
- 同一版本重试为幂等操作，不新增回收单；结论切换走版本条件更新，版本不符返回409，旧版与原授权依据进入历史且不丢失。
- 证据导出直接读取已落库回收单，撤回/保留清单与裁决结论同源，不会因重算而漂移。

## 目录

app为服务与规则，sample_data为输入，tests为测试，docs为定义与深度登记。
