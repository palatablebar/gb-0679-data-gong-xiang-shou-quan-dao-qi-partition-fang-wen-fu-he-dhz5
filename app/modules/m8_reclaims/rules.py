import csv,hashlib,io,json
from app.config import RECLAIM_COLUMNS,RECLAIM_GRANTS,RECLAIM_AS_OF
from app.errors import DomainError
from app.reasons import reject
from app.values import instant
from app.modules.m1_accesses.rules import decode

def validate_grants(grants):
    if not isinstance(grants,list) or not grants: raise DomainError("BAD_GRANT","授权登记为空")
    ids=set()
    for g in grants:
        if not isinstance(g,dict): raise DomainError("BAD_GRANT","授权版本无效")
        if g["id"] in ids or instant(g["start"])>=instant(g["end"]) or g["effect"] not in {"allow","deny"} or g["from_partition"]>=g["to_partition"]:
            raise DomainError("BAD_GRANT","授权版本无效")
        ids.add(g["id"])
    return grants

def parse_samples(raw):
    "解析特征样本CSV，沿用访问采信的编码/引号/隔离约定，保证来源行不丢"
    text,encoding=decode(raw)
    if not text: raise DomainError("EMPTY_FILE","文件为空")
    if not text.strip(): raise DomainError("BLANK_ONLY","全部为空行")
    stream=csv.reader(io.StringIO(text,newline=""));header=next(stream,None)
    if header!=RECLAIM_COLUMNS: raise DomainError("BAD_HEADER","表头不匹配")
    rows=[];bad=[];seen={};duplicate=blank=repeated=count=0
    try:
        for cells in stream:
            count+=1;line=stream.line_num
            if not cells or not any(c.strip() for c in cells): blank+=1;continue
            if cells==header: repeated+=1;continue
            row={"_line":line,"_sources":[line],"_raw":cells}
            if len(cells)!=len(header): bad.append(reject(row,"BAD_COLUMNS","列数不匹配"));continue
            row.update(dict(zip(header,[x.strip() for x in cells])))
            if not row["sample_id"]: bad.append(reject(row,"EMPTY_VALUE","样本键为空"));continue
            if not row["feature_version"]: bad.append(reject(row,"EMPTY_VALUE","特征版本为空"));continue
            key=row["sample_id"]
            if key in seen:
                if cells==seen[key]["_raw"]: duplicate+=1
                else: bad.append(reject(row,"DUPLICATE_CONFLICT","同样本不同值"))
                continue
            seen[key]=row;rows.append(row)
    except csv.Error: raise DomainError("BAD_CSV","引号未闭合或文件损坏")
    if count==0: raise DomainError("HEADER_ONLY","仅有表头")
    if not rows and not bad: raise DomainError("BLANK_ONLY","全部为空行")
    return rows,bad,{"input":count,"accepted":len(rows),"quarantine":len(bad),"duplicate":duplicate,"blank":blank,"repeated_headers":repeated,"encoding":encoding}

def _partition_ok(grant,partition):
    return grant["from_partition"]<=partition<grant["to_partition"]

def classify(sample,grants,as_of):
    "按样本复算授权：采集时须命中资源/分区/生效窗，裁决时刻仍有效方可继续使用，拒绝优先"
    at=instant(sample["sample_time"]);partition=sample["partition"]
    covering=[g for g in grants if g["principal"]==sample["principal"] and g["resource"]==sample["resource"]
              and instant(g["start"])<=at<instant(g["end"]) and _partition_ok(g,partition)]
    covering=sorted(covering,key=lambda g:g["id"])
    basis=[]
    for g in covering:
        state="有效" if instant(g["start"])<=as_of<instant(g["end"]) else "到期"
        basis.append({"grant_id":g["id"],"effect":g["effect"],"state":state,
                      "window":f'{g["start"]}~{g["end"]}',"partition_window":f'{g["from_partition"]}~{g["to_partition"]}'})
    active_deny=[b for b in basis if b["effect"]=="deny" and b["state"]=="有效"]
    active_allow=[b for b in basis if b["effect"]=="allow" and b["state"]=="有效"]
    if active_deny:
        disposition,reason="必须撤回","DENY_ACTIVE"
    elif active_allow:
        disposition,reason="可继续使用","ALLOW_VALID"
    elif covering:
        disposition,reason="必须撤回","ALLOW_EXPIRED"
    else:
        disposition,reason="必须撤回","NO_GRANT"
    return {"sample_id":sample["sample_id"],"feature_version":sample["feature_version"],"principal":sample["principal"],
            "resource":sample["resource"],"partition":partition,"sample_time":at.isoformat(),"model_use":sample.get("model_use",""),
            "source_lines":list(sample.get("_sources",[])),"disposition":disposition,"reason":reason,
            "matched_rules":[b["grant_id"] for b in basis],"rule_evidence":" / ".join(b["grant_id"] for b in basis) or "NO_GRANT","basis":basis}

def order_id(feature_version):
    return "RO-"+hashlib.sha1(feature_version.encode()).hexdigest()[:12]

def build_order(version,entries,grants,as_of):
    withdraw=[e for e in entries if e["disposition"]=="必须撤回"];retain=[e for e in entries if e["disposition"]=="可继续使用"]
    grant_basis=[{"grant_id":g["id"],"principal":g["principal"],"resource":g["resource"],"start":g["start"],"end":g["end"],
                  "from_partition":g["from_partition"],"to_partition":g["to_partition"],"effect":g["effect"],
                  "state":"有效" if instant(g["start"])<=as_of<instant(g["end"]) else "到期"} for g in sorted(grants,key=lambda g:g["id"])]
    ruling="整套版本撤回" if not retain else "按样本回收"
    payload={"feature_version":version,"ruling":ruling,"as_of":as_of.isoformat(),
             "sample_count":len(entries),"withdraw_count":len(withdraw),"retain_count":len(retain),
             "withdraw_samples":withdraw,"retain_samples":retain,"grant_basis":grant_basis}
    payload["order_id"]=order_id(version)
    payload["fingerprint"]=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return payload

def evaluate(raw_or_rows,context=None):
    context=context or {};params=context.get("parameters",{})
    grants=validate_grants(params.get("grants",RECLAIM_GRANTS))
    as_of=instant(params.get("as_of",RECLAIM_AS_OF))
    if isinstance(raw_or_rows,(bytes,bytearray)):
        rows,bad,intake=parse_samples(bytes(raw_or_rows))
    else:
        rows=list(raw_or_rows);bad=[];intake={"input":len(rows),"accepted":len(rows),"quarantine":0,"duplicate":0,"blank":0,"repeated_headers":0,"encoding":"rows"}
    good=[];invalid=list(bad)
    for row in rows:
        try:
            part=row.get("partition","")
            if len(part)!=7 or part[4]!="-" or not part[:4].isdigit() or not part[5:].isdigit() or not 1<=int(part[5:])<=12:
                invalid.append(reject(row,"BAD_PARTITION","分区必须为YYYY-MM"));continue
            if not row.get("principal"): invalid.append(reject(row,"EMPTY_PRINCIPAL","样本主体为空"));continue
            instant(row["sample_time"]);good.append(row)
        except DomainError as e: invalid.append(reject(row,e.code,e.message))
        except KeyError as e: invalid.append(reject(row,"MISSING_FIELD",f"缺少字段 {e.args[0]}"))
    entries=[classify(s,grants,as_of) for s in good]
    versions={}
    for entry in entries: versions.setdefault(entry["feature_version"],[]).append(entry)
    orders=[build_order(version,versions[version],grants,as_of) for version in sorted(versions)]
    metrics={**intake,"quarantine":len(invalid),"feature_versions":len(orders),"samples":len(entries),
             "withdraw":sum(o["withdraw_count"] for o in orders),"retain":sum(o["retain_count"] for o in orders),
             "full_withdrawals":sum(o["ruling"]=="整套版本撤回" for o in orders),
             "sample_reclaims":sum(o["ruling"]=="按样本回收" for o in orders),
             "balanced":intake["input"]==len(entries)+len(invalid)+intake["duplicate"]+intake["blank"]+intake["repeated_headers"]}
    return {"rows":orders,"quarantine":invalid,"metrics":metrics}
