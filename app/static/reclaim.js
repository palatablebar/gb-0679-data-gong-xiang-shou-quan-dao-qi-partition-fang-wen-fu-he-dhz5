(()=>{
  const output=document.querySelector('#reclaim-output');
  const detail=document.querySelector('#reclaim-detail');
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const reasonText={DENY_ACTIVE:'显式拒绝仍有效，禁止宽授权覆盖',ALLOW_VALID:'命中有效允许授权，授权窗与分区窗均覆盖',ALLOW_EXPIRED:'原允许授权已到期，授权依据失效',NO_GRANT:'无任何授权覆盖该样本'};
  const post=async(path,payload,form=false)=>{
    const response=await fetch(path,{method:'POST',headers:form?{}:{'Content-Type':'application/json'},body:form?payload:JSON.stringify(payload)});
    const data=await response.json();
    if(!response.ok)throw Error(data.message||('HTTP '+response.status));
    return data;
  };
  const sampleTable=(rows,kind)=>`<div class="panel__head"><h2>$ samples --${kind}</h2><span>${rows.length} 条</span></div>
    <div class="table-scroll"><table class="terminal-table"><thead><tr><th>样本</th><th>主体</th><th>资源</th><th>分区</th><th>模型用途</th><th>命中授权</th><th>依据</th></tr></thead><tbody>
    ${rows.map(r=>`<tr class="${kind==='withdraw'?'denied':''}"><td>${esc(r.sample_id)}</td><td>${esc(r.principal)}</td><td>${esc(r.resource)}</td><td>${esc(r.partition)}</td><td>${esc(r.model_use)}</td><td title="${esc(r.basis.map(b=>b.grant_id+':'+b.state).join(' / '))}">${esc(r.rule_evidence)}</td><td>${esc(reasonText[r.reason]||r.reason)}</td></tr>`).join('')||'<tr><td class="empty">无</td></tr>'}
    </tbody></table></div>`;
  const basisTable=grants=>`<div class="panel__head"><h2>$ grant-basis</h2></div><div class="table-scroll"><table class="terminal-table">
    <thead><tr><th>授权</th><th>主体</th><th>资源</th><th>生效窗</th><th>分区窗</th><th>效力</th><th>裁决时刻状态</th></tr></thead><tbody>
    ${grants.map(g=>`<tr class="${g.state==='到期'?'denied':''}"><td>${esc(g.grant_id)}</td><td>${esc(g.principal)}</td><td>${esc(g.resource)}</td><td>${esc(g.start)} ~ ${esc(g.end)}</td><td>${esc(g.from_partition)} ~ ${esc(g.to_partition)}</td><td>${esc(g.effect)}</td><td><b>${esc(g.state)}</b></td></tr>`).join('')}
    </tbody></table></div>`;
  const render=result=>{
    output.textContent=`预览 ${result.metrics.feature_versions} 个特征版本 / 撤回 ${result.metrics.withdraw} 保留 ${result.metrics.retain} / 隔离 ${result.metrics.quarantine} 行`;
    detail.innerHTML=result.rows.map(o=>`<section class="panel">
      <div class="panel__head"><h2>$ order ${esc(o.order_id)}</h2><span><b>${esc(o.ruling)}</b> · ${esc(o.feature_version)} · 裁决时刻 ${esc(o.as_of)}</span></div>
      <div class="panel__body">
        <div class="kpis">
          <div class="kpi">样本合计<b>${o.sample_count}</b></div>
          <div class="kpi">必须撤回<b>${o.withdraw_count}</b></div>
          <div class="kpi">可继续使用<b>${o.retain_count}</b></div>
        </div>
        ${sampleTable(o.withdraw_samples,'withdraw')}
        ${sampleTable(o.retain_samples,'retain')}
        ${basisTable(o.grant_basis)}
      </div>
    </section>`).join('');
  };
  const preview=async payload=>{
    output.textContent='RUNNING';
    try{const r=await fetch('/api/reclaims',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload||{})});
      const data=await r.json();if(!r.ok)throw Error(data.message);render(data);}
    catch(e){output.textContent=e.message;}
  };
  document.querySelector('#reclaim-preview').addEventListener('click',()=>preview({}));
  const save=async payload=>{
    output.textContent='SUBMITTING';
    try{const data=await post('/api/reclaims/orders',payload);
      output.textContent=`已保存 ${data.orders.length} 张回收单（同版本重试不新增单据）`;
      setTimeout(()=>location.reload(),600);}
    catch(e){output.textContent=e.message;}
  };
  document.querySelector('#reclaim-save').addEventListener('click',()=>{
    const v=document.querySelector('#reclaim-version').value;
    save(v?{version:Number(v)}:{});
  });
  document.querySelector('#reclaim-import').addEventListener('click',()=>{
    const file=document.querySelector('#reclaim-csv').files[0];
    if(!file){output.textContent='请选择特征样本文件。';return;}
    const reader=new FileReader();
    reader.onload=()=>{
      const payload={csv:reader.result};
      output.textContent='RUNNING';
      fetch('/api/reclaims',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
        .then(r=>r.json().then(d=>({ok:r.ok,d}))).then(({ok,d})=>{if(!ok)throw Error(d.message);render(d);window.__pendingPayload=payload;})
        .catch(e=>output.textContent=e.message);
    };
    reader.readAsText(file);
  });
  document.querySelectorAll('.reclaim-review').forEach(btn=>btn.addEventListener('click',async()=>{
    output.textContent='SUBMITTING';
    try{
      const r=await fetch(`/api/reclaims/orders/${btn.dataset.order}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:Number(btn.dataset.version),decision:btn.dataset.decision})});
      const d=await r.json();if(!r.ok)throw Error(d.message);
      output.textContent=`回收单 ${btn.dataset.order} 已${btn.dataset.decision}，版本升至 ${d.version}`;
      setTimeout(()=>location.reload(),600);
    }catch(e){output.textContent=e.message;}
  }));
  preview({});
})();
