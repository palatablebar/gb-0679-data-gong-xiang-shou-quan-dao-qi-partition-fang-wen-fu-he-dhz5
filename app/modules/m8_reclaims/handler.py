import csv,io,json
from flask import Blueprint,request,jsonify
from app.config import ROOT
from app.errors import DomainError
from app import store
from app.modules.m8_reclaims.rules import evaluate
bp=Blueprint("reclaims",__name__)
SAMPLES={"reclaim_samples.csv"}
def load_sample(name):
    if name not in SAMPLES: raise DomainError("BAD_SAMPLE","样例不存在",404)
    return (ROOT/"sample_data"/name).read_bytes()
def _evaluate(payload):
    if not isinstance(payload,dict): raise DomainError("BAD_BODY","请求需要对象")
    params=payload.get("parameters",{})
    if not isinstance(params,dict): raise DomainError("BAD_PARAMETERS","参数需要对象")
    if "rows" in payload:
        if not isinstance(payload["rows"],list) or any(not isinstance(row,dict) for row in payload["rows"]): raise DomainError("BAD_ROWS","记录需要对象列表")
        return evaluate(payload["rows"],{"parameters":params})
    raw=payload.get("csv")
    if raw is not None:
        if not isinstance(raw,str): raise DomainError("BAD_CSV","CSV需要文本")
        data=raw.encode()
    else:
        data=load_sample(payload.get("sample","reclaim_samples.csv"))
    return evaluate(data,{"parameters":params})
@bp.route("/api/reclaims",methods=["GET","POST"])
def preview():
    "只计算回收裁决，不落库，供复核页预览"
    payload=request.get_json(silent=True) if request.method=="POST" else {}
    return jsonify(_evaluate(payload if payload is not None else {}))
@bp.route("/api/reclaims/orders",methods=["GET","POST"])
def orders():
    if request.method=="GET": return jsonify({"orders":store.reclaim_orders()})
    payload=request.get_json(silent=True) or {}
    if not isinstance(payload,dict): raise DomainError("BAD_BODY","请求需要对象")
    result=_evaluate(payload);run_id=payload.get("run_id");decision=payload.get("decision","待复核")
    if decision not in {"待复核","已复核","退回复核"}: raise DomainError("BAD_DECISION","复核状态无效")
    versions=payload.get("versions")
    if versions is not None and not isinstance(versions,dict): raise DomainError("BAD_VERSION","版本映射需要对象")
    single=payload.get("version")
    if single is not None and not isinstance(single,int): raise DomainError("BAD_VERSION","版本号需为整数")
    saved=[]
    for order in result["rows"]:
        expected=(versions or {}).get(order["order_id"], single if versions is None else None)
        if expected is not None and not isinstance(expected,int): raise DomainError("BAD_VERSION","版本号需为整数")
        saved.append(store.save_reclaim_order(order,order["fingerprint"],run_id,expected,decision))
    return jsonify({"orders":saved,"metrics":result["metrics"],"quarantine":result["quarantine"]})
@bp.route("/api/reclaims/orders/<order_id>")
def order_detail(order_id): return jsonify(store.get_reclaim_order(order_id))
@bp.route("/api/reclaims/orders/<order_id>/review",methods=["POST"])
def order_review(order_id):
    p=request.get_json(silent=True) or {}
    if not isinstance(p.get("version"),int): raise DomainError("BAD_VERSION","请提供版本号")
    return jsonify(store.review_reclaim_order(order_id,p["version"],p.get("decision")))
@bp.route("/api/reclaims/orders/<order_id>/history")
def order_history(order_id): return jsonify({"history":store.reclaim_history(order_id)})
@bp.route("/api/reclaims/orders/<order_id>/evidence")
def order_evidence(order_id):
    "唯一证据导出：直接读取已落库回收单，结论与样本清单同源，不重新计算"
    order=store.get_reclaim_order(order_id)
    stream=io.StringIO(newline="");writer=csv.writer(stream)
    writer.writerow(["order_id","feature_version","ruling","as_of","kind","subject","disposition","reason","evidence"])
    for kind,bucket,subject_key in (("sample_withdraw",order["withdraw_samples"],"sample_id"),("sample_retain",order["retain_samples"],"sample_id")):
        for row in bucket:
            writer.writerow([order["order_id"],order["feature_version"],order["ruling"],order["as_of"],kind,
                             row[subject_key],row["disposition"],row["reason"],json.dumps(row,ensure_ascii=False)])
    for grant in order["grant_basis"]:
        writer.writerow([order["order_id"],order["feature_version"],order["ruling"],order["as_of"],"grant_basis",
                         grant["grant_id"],"—","授权"+grant["state"],json.dumps(grant,ensure_ascii=False)])
    from flask import current_app
    return current_app.response_class("\ufeff"+stream.getvalue(),mimetype="text/csv",
        headers={"Content-Disposition":f'attachment; filename="evidence-{order["order_id"]}.csv"'})
