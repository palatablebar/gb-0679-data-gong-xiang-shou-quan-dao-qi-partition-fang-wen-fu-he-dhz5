import csv,io
from app.config import ROOT,RECLAIM_GRANTS
from app.modules.m8_reclaims.rules import evaluate,validate_grants,order_id,parse_samples
from app.errors import DomainError
from app import store
import pytest
def load_reclaim_sample(name="reclaim_samples.csv"): return (ROOT/"sample_data"/name).read_bytes()
@pytest.fixture
def sample(): return load_reclaim_sample()
@pytest.fixture
def result(sample): return evaluate(sample)
def test_real_sample_balanced(result):
    m=result["metrics"]
    assert m["balanced"] is True
    assert m["input"]==m["samples"]+m["quarantine"]+m["duplicate"]+m["blank"]+m["repeated_headers"]
def test_real_sample_quarantine_reasons(result):
    codes={r["reason"] for r in result["quarantine"]}
    assert {"BAD_PARTITION","EMPTY_PRINCIPAL","DUPLICATE_CONFLICT"} <= codes
def test_real_sample_one_order_per_version(result):
    versions=[o["feature_version"] for o in result["rows"]]
    assert len(versions)==len(set(versions))==4
    assert len({o["order_id"] for o in result["rows"]})==4
def test_real_sample_mixed_version_ruled_per_sample(result):
    mkt7=next(o for o in result["rows"] if o["feature_version"]=="FV-MKT-7")
    assert mkt7["ruling"]=="按样本回收" and mkt7["withdraw_count"]==6 and mkt7["retain_count"]==3
def test_real_sample_full_expired_version_withdrawn(result):
    mkt8=next(o for o in result["rows"] if o["feature_version"]=="FV-MKT-8")
    assert mkt8["ruling"]=="整套版本撤回" and mkt8["retain_count"]==0 and mkt8["withdraw_count"]==4
def test_real_sample_clean_version_fully_retained(result):
    growth=next(o for o in result["rows"] if o["feature_version"]=="FV-GROWTH-2")
    assert growth["ruling"]=="按样本回收" and growth["withdraw_count"]==0 and growth["retain_count"]==3
def test_real_sample_order_lists_basis_and_evidence(result):
    mkt7=next(o for o in result["rows"] if o["feature_version"]=="FV-MKT-7")
    expired=next(s for s in mkt7["withdraw_samples"] if s["sample_id"]=="S1005")
    assert expired["reason"]=="ALLOW_EXPIRED" and any(b["state"]=="到期" for b in expired["basis"])
    retained=next(s for s in mkt7["retain_samples"] if s["sample_id"]=="S1001")
    assert retained["reason"]=="ALLOW_VALID" and all(b["state"]=="有效" for b in retained["basis"])
def test_real_sample_grant_basis_marked_expired(result):
    mkt7=next(o for o in result["rows"] if o["feature_version"]=="FV-MKT-7")
    rg02=next(g for g in mkt7["grant_basis"] if g["grant_id"]=="RG-02")
    assert rg02["state"]=="到期"
def test_deny_grant_overrides_broad_allow():
    rows=[{"sample_id":"D1","feature_version":"FV-D","principal":"marketing","resource":"orders","partition":"2026-03","sample_time":"2026-06-01T00:00:00Z","model_use":"训练"}]
    out=evaluate(rows)["rows"][0]
    s=out["withdraw_samples"][0]
    assert s["reason"]=="DENY_ACTIVE" and "RG-03" in s["matched_rules"] and "RG-01" in s["matched_rules"]
    assert out["ruling"]=="整套版本撤回"
def test_no_grant_default_withdraw():
    rows=[{"sample_id":"N1","feature_version":"FV-N","principal":"marketing","resource":"inventory","partition":"2026-03","sample_time":"2026-06-01T00:00:00Z","model_use":"训练"}]
    s=evaluate(rows)["rows"][0]["withdraw_samples"][0]
    assert s["reason"]=="NO_GRANT" and s["rule_evidence"]=="NO_GRANT"
def test_expiry_endpoint_excluded_half_open():
    "授权到期点立即失效：as_of 落在 end 上时授权已到期"
    rows=[{"sample_id":"E1","feature_version":"FV-E","principal":"marketing","resource":"customers","partition":"2026-05","sample_time":"2026-06-01T00:00:00Z","model_use":"训练"}]
    out=evaluate(rows,{"parameters":{"as_of":"2026-11-01T00:00:00Z"}})
    assert out["rows"][0]["withdraw_samples"][0]["reason"]=="ALLOW_EXPIRED"
    before=evaluate(rows,{"parameters":{"as_of":"2026-10-31T23:59:59Z"}})
    assert before["rows"][0]["retain_samples"][0]["reason"]=="ALLOW_VALID"
def test_partition_window_half_open():
    rows=[{"sample_id":"P1","feature_version":"FV-P","principal":"growth","resource":"orders","partition":"2026-12","sample_time":"2026-06-01T00:00:00Z","model_use":"训练"}]
    assert evaluate(rows)["rows"][0]["withdraw_samples"][0]["reason"]=="NO_GRANT"
def test_invalid_grant_rejected():
    with pytest.raises(DomainError): validate_grants([{**RECLAIM_GRANTS[0],"end":RECLAIM_GRANTS[0]["start"]}])
    with pytest.raises(DomainError): validate_grants([])
def test_bad_header_and_encoding(sample):
    with pytest.raises(DomainError) as e: evaluate(b"sample_id,wrong\n1,2\n")
    assert e.value.code=="BAD_HEADER"
    from app.pipeline import load_sample
    with pytest.raises(DomainError): evaluate(load_sample("legacy.csv"))
def test_order_id_stable_for_version():
    assert order_id("FV-MKT-7")==order_id("FV-MKT-7") and order_id("FV-MKT-7")!=order_id("FV-MKT-8")
def test_duplicate_exact_row_counted_not_admitted(sample):
    rows,bad,intake=parse_samples(sample)
    ids=[r["sample_id"] for r in rows]
    assert ids.count("S1001")==1 and intake["duplicate"]==1
# ---- persistence ----
def test_save_idempotent_same_conclusion(sample):
    first=evaluate(sample)
    a=[store.save_reclaim_order(o,o["fingerprint"]) for o in first["rows"]]
    b=[store.save_reclaim_order(o,o["fingerprint"]) for o in first["rows"]]
    assert [x["order_id"] for x in a]==[x["order_id"] for x in b]
    assert all(x["version"]==1 for x in b) and len(store.reclaim_orders())==4
def test_retry_does_not_add_order(sample,client):
    client.post("/api/reclaims/orders",json={"sample":"reclaim_samples.csv"})
    client.post("/api/reclaims/orders",json={"sample":"reclaim_samples.csv"})
    assert len(client.get("/api/reclaims/orders").get_json()["orders"])==4
def test_changed_conclusion_versions_and_archives_old(sample):
    oid=order_id("FV-MKT-7")
    order=next(o for o in evaluate(sample)["rows"] if o["order_id"]==oid)
    store.save_reclaim_order(order,order["fingerprint"])
    changed=evaluate(sample,{"parameters":{"as_of":"2030-01-01T00:00:00Z"}})
    new_order=next(o for o in changed["rows"] if o["order_id"]==oid)
    updated=store.save_reclaim_order(new_order,new_order["fingerprint"],expected_version=1)
    assert updated["version"]==2 and updated["ruling"]=="整套版本撤回"
    history=store.reclaim_history(oid)
    assert len(history)==1 and history[0]["version"]==1
    assert history[0]["payload"]["ruling"]=="按样本回收"
    assert history[0]["payload"]["grant_basis"]==order["grant_basis"]
def test_stale_switch_keeps_old_version_and_basis(sample):
    oid=order_id("FV-MKT-7")
    order=next(o for o in evaluate(sample)["rows"] if o["order_id"]==oid)
    store.save_reclaim_order(order,order["fingerprint"])
    changed=evaluate(sample,{"parameters":{"as_of":"2030-01-01T00:00:00Z"}})
    new_order=next(o for o in changed["rows"] if o["order_id"]==oid)
    with pytest.raises(DomainError) as e: store.save_reclaim_order(new_order,new_order["fingerprint"],expected_version=99)
    assert e.value.code=="STALE_VERSION"
    kept=store.get_reclaim_order(oid)
    assert kept["version"]==1 and kept["ruling"]=="按样本回收" and kept["fingerprint"]==order["fingerprint"]
    assert store.reclaim_history(oid)==[]
def test_review_version_guard_and_history(client):
    p=client.post("/api/reclaims/orders",json={"sample":"reclaim_samples.csv"}).get_json()
    oid=p["orders"][0]["order_id"];url=f"/api/reclaims/orders/{oid}/review"
    assert client.post(url,json={"version":1,"decision":"已复核"}).status_code==200
    assert client.post(url,json={"version":1,"decision":"退回复核"}).status_code==409
    h=client.get(f"/api/reclaims/orders/{oid}/history").get_json()["history"]
    assert h[0]["decision"]=="已复核"
    assert client.post(url,json={"version":2,"decision":"bad"}).status_code==422
def test_evidence_follows_stored_conclusion(client):
    p=client.post("/api/reclaims/orders",json={"sample":"reclaim_samples.csv"}).get_json()
    target=next(o for o in p["orders"] if o["feature_version"]=="FV-MKT-7")
    ev=list(csv.reader(io.StringIO(client.get(f"/api/reclaims/orders/{target['order_id']}/evidence").data.decode("utf-8-sig"))))
    assert ev[0][:3]==["order_id","feature_version","ruling"]
    body=ev[1:]
    assert sum(1 for r in body if r[4]=="sample_withdraw")==target["withdraw_count"]
    assert sum(1 for r in body if r[4]=="sample_retain")==target["retain_count"]
    assert all(r[2]==target["ruling"] for r in body)
    assert any(r[4]=="grant_basis" and "到期" in r[7] for r in body)
def test_evidence_reflects_switched_conclusion(client):
    p=client.post("/api/reclaims/orders",json={"sample":"reclaim_samples.csv"}).get_json()
    target=next(o for o in p["orders"] if o["feature_version"]=="FV-MKT-7")
    switched=client.post("/api/reclaims/orders",json={"sample":"reclaim_samples.csv","parameters":{"as_of":"2030-01-01T00:00:00Z"},"versions":{target["order_id"]:1}}).get_json()
    now=next(o for o in switched["orders"] if o["order_id"]==target["order_id"])
    ev=list(csv.reader(io.StringIO(client.get(f"/api/reclaims/orders/{target['order_id']}/evidence").data.decode("utf-8-sig"))))
    assert all(r[2]=="整套版本撤回" for r in ev[1:])
    assert sum(1 for r in ev[1:] if r[4]=="sample_withdraw")==now["withdraw_count"]
def test_missing_order_404(client):
    assert client.get("/api/reclaims/orders/RO-nope").status_code==404
    assert client.get("/api/reclaims/orders/RO-nope/evidence").status_code==404
def test_reclaim_page_and_nav(client):
    r=client.get("/reclaims");assert r.status_code==200 and "特征回收".encode() in r.data
    assert client.get("/api/reclaims").status_code==200
