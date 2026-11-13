"""Génère docs/index.html : dashboard statique (GitHub Pages ou ouverture locale)."""
from __future__ import annotations

import json
from datetime import date, timedelta


def render(state: dict, cfg: dict, generated: str) -> str:
    stale = (date.today() - timedelta(days=cfg["stale_after_days"])).isoformat()
    offers = sorted(state["offers"].values(), key=lambda o: (-o["score"], o["first_seen"]), reverse=False)
    for o in offers:
        o["stale"] = o["last_seen"] < stale
    payload = json.dumps({"offers": offers, "generated": generated, "runs": state.get("runs", [])[-10:]},
                         ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", payload)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Veille startup — Founder Associate / Chief of Staff</title>
<style>
:root{--bg:#f6f5f1;--card:#fff;--ink:#1d1d1b;--mute:#6b6a65;--line:#e4e2db;--acc:#1f4fd1;--good:#11845b;--warn:#b26a00;--bad:#b3261e}
@media(prefers-color-scheme:dark){:root{--bg:#141413;--card:#1e1e1c;--ink:#ecebe6;--mute:#a09f99;--line:#33322f;--acc:#7aa2ff;--good:#4cc38a;--warn:#e0a34a;--bad:#ff8a80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
header{padding:22px 28px 10px}h1{margin:0;font-size:20px;letter-spacing:-.01em}.sub{color:var(--mute);margin-top:4px}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 28px;border-bottom:1px solid var(--line)}
input,select,button{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
input[type=search]{min-width:220px}button{cursor:pointer}button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.kpis{display:flex;gap:18px;padding:12px 28px;color:var(--mute)}.kpis b{color:var(--ink);font-size:16px}
main{padding:6px 28px 40px;display:grid;gap:10px}
.o{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:grid;grid-template-columns:52px 1fr auto;gap:12px;align-items:start}
.o.dim{opacity:.45}.sc{font-weight:700;font-size:18px;text-align:center;border-radius:10px;padding:6px 0}
.s-hi{background:color-mix(in srgb,var(--good) 16%,transparent);color:var(--good)}.s-mid{background:color-mix(in srgb,var(--acc) 14%,transparent);color:var(--acc)}.s-lo{background:color-mix(in srgb,var(--mute) 14%,transparent);color:var(--mute)}
.t a{color:var(--ink);font-weight:600;text-decoration:none;font-size:15px}.t a:hover{color:var(--acc)}
.meta{color:var(--mute);margin-top:2px}.why{margin-top:6px;display:flex;flex-wrap:wrap;gap:5px}
.tag{font-size:12px;padding:1px 7px;border-radius:99px;border:1px solid var(--line);color:var(--mute)}.tag.new{border-color:var(--good);color:var(--good);font-weight:600}.tag.old{border-color:var(--warn);color:var(--warn)}
.st select{font-size:12.5px}.empty{color:var(--mute);padding:40px;text-align:center}
footer{color:var(--mute);padding:0 28px 30px;font-size:12px}
</style></head><body>
<header><h1>Veille startup · Founder/CEO Associate · Chief of Staff · BizOps</h1>
<div class="sub">Freelance ~3,5 j/sem ou stage alterné · janv.→juin 2027 · Paris/IDF + remote · <span id="gen"></span></div></header>
<div class="bar">
 <input type="search" id="q" placeholder="Filtrer (titre, boîte, raison…)">
 <select id="src"><option value="">Toutes sources</option></select>
 <button data-f="internship">Stage</button><button data-f="freelance">Freelance</button><button data-f="part_time">Temps partiel</button>
 <label>Score ≥ <input type="number" id="min" value="35" min="0" max="100" style="width:64px"></label>
 <select id="stf"><option value="open">À traiter</option><option value="">Tous statuts</option><option value="interesse">Intéressant</option><option value="postule">Postulé</option><option value="ecarte">Écartés</option></select>
 <button id="newb">Nouvelles (3 j)</button><button id="staleb">Inclure expirées</button>
 <button id="exp" title="Sauvegarder tes statuts">Exporter statuts</button><button id="imp">Importer</button>
</div>
<div class="kpis" id="kpis"></div><main id="list"></main>
<footer id="runs"></footer>
<script>
const D=__DATA__;const KEY="veille-startup-status";
let ST={};try{ST=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(ST))}catch(e){}};
const F={fmt:new Set(),onlyNew:false,stale:false};
const $=s=>document.querySelector(s);const esc=s=>String(s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
$("#gen").textContent="MAJ "+D.generated;
[...new Set(D.offers.map(o=>o.source.split(" · ")[0]))].sort().forEach(s=>$("#src").insertAdjacentHTML("beforeend",`<option>${esc(s)}</option>`));
const d3=new Date(Date.now()-3*864e5).toISOString().slice(0,10);
function draw(){
 const q=$("#q").value.toLowerCase(),src=$("#src").value,min=+$("#min").value||0,stf=$("#stf").value;
 const rows=D.offers.filter(o=>{
  const s=ST[o.id]||"";
  if(o.score<min)return false; if(src&&!o.source.startsWith(src))return false;
  if(!F.stale&&o.stale&&!s)return false; if(F.onlyNew&&o.first_seen<d3)return false;
  if(F.fmt.size&&![...F.fmt].some(f=>(o.formats||[]).includes(f)))return false;
  if(stf==="open"&&(s==="ecarte"||s==="postule"))return false; if(stf&&stf!=="open"&&s!==stf)return false;
  if(q&&!(o.title+" "+o.company+" "+(o.why||[]).join(" ")+" "+o.location).toLowerCase().includes(q))return false;
  return true}).sort((a,b)=>b.score-a.score||b.first_seen.localeCompare(a.first_seen));
 $("#kpis").innerHTML=`<span><b>${rows.length}</b> affichées</span><span><b>${D.offers.filter(o=>o.first_seen>=d3).length}</b> nouvelles (3 j)</span><span><b>${Object.values(ST).filter(v=>v==="postule").length}</b> postulé</span><span><b>${D.offers.length}</b> en base</span>`;
 $("#list").innerHTML=rows.length?rows.map(o=>{const s=ST[o.id]||"";const cl=o.score>=60?"s-hi":o.score>=40?"s-mid":"s-lo";
  return `<div class="o ${s==="ecarte"?"dim":""}"><div class="sc ${cl}">${o.score}</div>
  <div class="t"><a href="${esc(o.url)}" target="_blank" rel="noopener">${esc(o.title)}</a>
  <div class="meta">${esc(o.company)}${o.location?" · "+esc(o.location):""}${o.contract?" · "+esc(o.contract):""} · ${esc(o.source)} · vue le ${o.first_seen}</div>
  <div class="why">${o.first_seen>=d3?'<span class="tag new">nouveau</span>':""}${o.stale?'<span class="tag old">plus vue depuis '+o.last_seen+'</span>':""}${(o.why||[]).map(w=>`<span class="tag">${esc(w)}</span>`).join("")}${(o.alt_urls||[]).map((u,i)=>`<a class="tag" href="${esc(u)}" target="_blank">autre lien ${i+1}</a>`).join("")}</div></div>
  <div class="st"><select data-id="${esc(o.id)}">${[["","À voir"],["interesse","Intéressant"],["postule","Postulé"],["ecarte","Écarté"]].map(([v,l])=>`<option value="${v}" ${v===s?"selected":""}>${l}</option>`).join("")}</select></div></div>`}).join(""):'<div class="empty">Aucune offre avec ces filtres.</div>';
}
document.addEventListener("change",e=>{if(e.target.dataset.id){ST[e.target.dataset.id]=e.target.value;if(!e.target.value)delete ST[e.target.dataset.id];save();draw()}});
document.querySelectorAll("[data-f]").forEach(b=>b.onclick=()=>{const f=b.dataset.f;F.fmt.has(f)?F.fmt.delete(f):F.fmt.add(f);b.classList.toggle("on");draw()});
$("#newb").onclick=e=>{F.onlyNew=!F.onlyNew;e.target.classList.toggle("on");draw()};
$("#staleb").onclick=e=>{F.stale=!F.stale;e.target.classList.toggle("on");draw()};
["#q","#src","#min","#stf"].forEach(s=>$(s).addEventListener("input",draw));
$("#exp").onclick=()=>{const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(ST,null,1)],{type:"application/json"}));a.download="statuts-veille.json";a.click()};
$("#imp").onclick=()=>{const i=document.createElement("input");i.type="file";i.accept=".json";i.onchange=async()=>{try{Object.assign(ST,JSON.parse(await i.files[0].text()));save();draw()}catch(e){alert("Fichier invalide")}};i.click()};
$("#runs").innerHTML="Derniers passages : "+D.runs.slice().reverse().map(r=>`${esc(r.at)} → ${r.new} nouv. / ${r.kept} retenues (${esc(JSON.stringify(r.sources))})`).join(" · ");
draw();
</script></body></html>"""
