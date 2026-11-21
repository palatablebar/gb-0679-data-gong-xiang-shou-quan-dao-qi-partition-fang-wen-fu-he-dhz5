from pathlib import Path
import os
ROOT=Path(__file__).resolve().parent.parent
DATA_DIR=Path(os.environ.get("DATA_DIR", "/tmp/grantpartition"))
TITLE='数据共享授权到期与分区访问复核'
SHORT='grantpartition'
COLUMNS=['event_id', 'principal', 'resource', 'partition', 'access_time', 'observed', 'reported', 'note']
RECLAIM_COLUMNS=['sample_id', 'feature_version', 'principal', 'resource', 'partition', 'sample_time', 'model_use']
# 特征样本授权登记：营销模型共享分区授权，全部条件同时匹配，[start,end) 半开区间
RECLAIM_GRANTS=[{"id":"RG-01","principal":"marketing","resource":"orders","start":"2026-01-01T00:00:00Z","end":"2027-01-01T00:00:00Z","from_partition":"2026-01","to_partition":"2026-12","effect":"allow"},{"id":"RG-02","principal":"marketing","resource":"customers","start":"2026-01-01T00:00:00Z","end":"2026-11-01T00:00:00Z","from_partition":"2026-01","to_partition":"2026-12","effect":"allow"},{"id":"RG-03","principal":"marketing","resource":"orders","start":"2026-01-01T00:00:00Z","end":"2027-01-01T00:00:00Z","from_partition":"2026-03","to_partition":"2026-04","effect":"deny"},{"id":"RG-04","principal":"growth","resource":"orders","start":"2026-01-01T00:00:00Z","end":"2027-01-01T00:00:00Z","from_partition":"2026-01","to_partition":"2026-12","effect":"allow"}]
# 回收裁决基准时刻（可由参数 as_of 覆盖），到期点立即失效
RECLAIM_AS_OF="2026-11-21T00:00:00Z"
MODULES=[('accesses', '访问采信'), ('resources', '资源映射'), ('grants', '授权定版'), ('conflicts', '冲突裁决'), ('partitions', '分区判定'), ('audit', '访问对账'), ('seals', '审计归档'), ('reclaims', '特征回收')]
RULE_VERSION="2026.11.17-r1"
