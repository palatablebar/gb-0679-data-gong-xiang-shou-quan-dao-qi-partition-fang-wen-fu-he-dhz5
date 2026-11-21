# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file。/api/runs/<id>/archive只导出一份带清单与证据的CSV。

## M8 特征版本回收

- `GET/POST /api/reclaims`：预览回收裁决，不落库。POST可传`csv`、`rows`或默认`reclaim_samples.csv`，`parameters.as_of`覆盖裁决时刻，`parameters.grants`覆盖授权登记。返回的`rows`为回收单（每特征版本一张）。
- `GET /api/reclaims/orders`：已落库回收单清单。
- `POST /api/reclaims/orders`：按预览结论落库。同一特征版本仅保留一张回收单：结论指纹相同为重试，幂等不新增；结论变化时按`version`（单版本）或`versions:{order_id:version}`（批量逐单）做条件更新，版本不符返回409并保留旧版与原授权依据。
- `GET /api/reclaims/orders/<order_id>`：回收单详情，含必须撤回/可继续使用样本与逐授权依据。
- `POST /api/reclaims/orders/<order_id>/review`：body需要`version`与`decision`（已复核/退回复核），陈旧版本409，旧结论进入历史。
- `GET /api/reclaims/orders/<order_id>/history`：该回收单全部历史版本，任一版本的授权依据均可追溯。
- `GET /api/reclaims/orders/<order_id>/evidence`：唯一证据导出CSV，直接读取已落库回收单，不重新计算；每行结论（ruling、disposition、reason）与回收单同源。
