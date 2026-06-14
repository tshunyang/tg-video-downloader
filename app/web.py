import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .telegram_client import is_authorized, start_login, complete_login, get_listened_chats, set_listened_chats, is_listening, start_listening, stop_listening, list_dialogs, logout
from .downloader import list_tasks, pause_task, cancel_task, retry_task, get_dashboard_stats, batch_action, cleanup_orphan_partial_files
from .config import settings

app = FastAPI(title="TG资源自动下载器")


def ensure_dir(path_str: str) -> str:
    if not path_str:
        return ""
    path = Path(path_str)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def safe_dir_listing(path_str: str | None = None) -> dict:
    if path_str:
        current = Path(path_str).expanduser()
    else:
        current = settings.project_root.anchor and Path(settings.project_root.anchor) or Path.cwd()
    current = current.resolve()
    if not current.exists():
        current.mkdir(parents=True, exist_ok=True)
    if not current.is_dir():
        raise RuntimeError("目标不是目录")

    parents = []
    probe = current
    while True:
        parents.append(str(probe))
        if probe.parent == probe:
            break
        probe = probe.parent

    entries = []
    try:
        for item in sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if item.name.startswith('.'):
                continue
            entries.append({
                "name": item.name,
                "path": str(item),
                "isDir": item.is_dir(),
            })
    except PermissionError:
        raise RuntimeError("没有权限读取该目录")

    return {"current": str(current), "parents": parents, "entries": entries}


def render_page(ctx: dict) -> str:
    html = r'''<!doctype html>
<html data-theme="__THEME__">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>TG资源自动下载器</title>
<style>
:root{--card:rgba(18,26,49,.88);--card2:rgba(255,255,255,.06);--text:#e8ecf7;--muted:#9aa6c3;--line:rgba(255,255,255,.08);--primary:#6ea8fe;--primary2:#7c5cff;--success:#35d39a;--danger:#ff6b81;--warning:#ffb84d;--bg:linear-gradient(180deg,#0a0f1f 0%,#111a33 100%)}
html[data-theme='light']{--card:rgba(255,255,255,.92);--card2:rgba(15,23,42,.04);--text:#162234;--muted:#60708a;--line:rgba(15,23,42,.08);--primary:#2563eb;--primary2:#7c3aed;--success:#059669;--danger:#dc2626;--warning:#d97706;--bg:linear-gradient(180deg,#f8fbff 0%,#eef4ff 100%)}
@media (prefers-color-scheme: light){html[data-theme='system']{--card:rgba(255,255,255,.92);--card2:rgba(15,23,42,.04);--text:#162234;--muted:#60708a;--line:rgba(15,23,42,.08);--primary:#2563eb;--primary2:#7c3aed;--success:#059669;--danger:#dc2626;--warning:#d97706;--bg:linear-gradient(180deg,#f8fbff 0%,#eef4ff 100%)}}
*{box-sizing:border-box} body{margin:0;font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif;color:var(--text);background:var(--bg)}
.shell{max-width:1280px;margin:0 auto;padding:24px}.hero{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:20px}.title{font-size:32px;font-weight:900;margin:0}.subtitle{color:var(--muted);margin-top:8px}.top-actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.badge,.card,.pane,input,select,button,table th{border:1px solid var(--line)} .badge{display:inline-flex;gap:8px;align-items:center;padding:8px 14px;border-radius:999px;background:rgba(255,255,255,.08)} .dot{width:9px;height:9px;border-radius:50%;display:inline-block}.dot.ok{background:var(--success)}.dot.off{background:var(--danger)}
.theme-icons{display:flex;gap:8px;align-items:center}.theme-btn{width:40px;height:40px;padding:0;border-radius:999px;background:rgba(255,255,255,.06);color:var(--text);font-size:18px}.theme-btn.active{background:linear-gradient(135deg,var(--primary),var(--primary2));color:#fff}
.card{background:var(--card);border-radius:18px}.pane{background:var(--card2);border-radius:16px;padding:18px}.login-wrap{max-width:760px;margin:64px auto 0}.login-card{padding:28px}.login-grid,.grid,.stat-grid,.dashboard-grid{display:grid;gap:14px}.login-grid,.grid,.stat-grid{grid-template-columns:repeat(2,minmax(260px,1fr))}.stat-grid{grid-template-columns:repeat(3,1fr)}.dashboard-grid{grid-template-columns:1.2fr .8fr}
.layout{display:grid;grid-template-columns:260px 1fr;gap:20px}.sidebar{padding:18px;position:sticky;top:20px;height:fit-content}.nav{display:flex;flex-direction:column;gap:10px;margin-top:18px}.nav-btn{width:100%;display:flex;gap:10px;justify-content:flex-start}.nav-btn.active{background:linear-gradient(135deg,var(--primary),var(--primary2));color:#fff}.content{display:flex;flex-direction:column;gap:20px}.section{padding:22px;display:none}.section.active{display:block}
.section-head,.row,.checkline{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.section-head{justify-content:space-between;margin-bottom:18px}.muted{color:var(--muted)} label{display:block;color:var(--muted);font-size:14px;margin-bottom:4px}.field{display:flex;flex-direction:column;gap:8px}.type-row{display:grid;grid-template-columns:140px 1fr auto auto;gap:12px;align-items:center;margin-bottom:10px}.setting-title{font-size:16px;font-weight:800;margin-bottom:12px}.hint{font-size:12px;color:var(--muted);line-height:1.6}.setting-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}.slider-field{display:grid;grid-template-columns:1fr 120px;gap:12px;align-items:center}.slider-field input[type=range]{padding:0;height:6px;accent-color:var(--primary);border:0}.range-pair{position:relative;height:34px;margin:8px 0 10px}.range-pair:before{content:"";position:absolute;left:0;right:0;top:14px;height:6px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid var(--line)}.range-fill{position:absolute;top:14px;height:6px;border-radius:999px;background:linear-gradient(90deg,var(--primary),var(--primary2));pointer-events:none}.range-pair input[type=range]{position:absolute;inset:8px 0 auto 0;width:100%;padding:0;border:0;background:transparent;pointer-events:none;-webkit-appearance:none;appearance:none}.range-pair input[type=range]::-webkit-slider-runnable-track{height:6px;background:transparent;border:0}.range-pair input[type=range]::-moz-range-track{height:6px;background:transparent;border:0}.range-pair input[type=range]::-moz-range-progress{background:transparent}.range-pair input[type=range]::-webkit-slider-thumb{pointer-events:auto;-webkit-appearance:none;appearance:none;width:18px;height:18px;margin-top:-6px;border-radius:999px;background:linear-gradient(135deg,var(--primary),var(--primary2));border:2px solid var(--card);box-shadow:0 0 0 1px var(--line)}.range-pair input[type=range]::-moz-range-thumb{pointer-events:auto;width:18px;height:18px;border-radius:999px;background:linear-gradient(135deg,var(--primary),var(--primary2));border:2px solid var(--card);box-shadow:0 0 0 1px var(--line)}.size-values{display:grid;grid-template-columns:1fr 1fr;gap:12px}.size-values .slider-field{grid-template-columns:1fr}.task-switch{display:inline-flex;gap:8px;align-items:center;padding:10px 12px;border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.06);color:var(--text);font-size:14px}.task-switch input{width:auto}.metric{display:flex;justify-content:space-between;color:var(--muted);font-size:12px}.switchline{display:flex;gap:8px;align-items:center;margin-top:12px}.switchline input{width:auto}.status-pill{display:inline-flex;align-items:center;padding:4px 9px;border-radius:999px;background:rgba(255,255,255,.08);font-size:12px;font-weight:800}.status-pill.completed{color:var(--success)}.status-pill.downloading{color:var(--primary)}.status-pill.error,.status-pill.canceled{color:var(--danger)}.status-pill.paused{color:var(--warning)}.table-wrap{width:100%;overflow:auto;border:1px solid var(--line);border-radius:14px}.task-table{min-width:980px;table-layout:fixed}.task-table th:nth-child(1){width:44px}.task-table th:nth-child(2){width:170px}.task-table th:nth-child(3){width:80px}.task-table th:nth-child(4){width:260px}.task-table th:nth-child(5){width:110px}.task-table th:nth-child(6){width:170px}.task-table th:nth-child(7){width:280px}.task-table th:nth-child(8){width:220px}.ellipsis{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.path-cell{word-break:normal}
input,select{width:100%;padding:12px 14px;border-radius:12px;background:rgba(255,255,255,.06);color:var(--text)}input:disabled,select:disabled{opacity:.52;background:rgba(255,255,255,.025);color:var(--muted);cursor:not-allowed} select option{color:#111} button{border-radius:12px;padding:10px 14px;background:linear-gradient(135deg,var(--primary),var(--primary2));color:#fff;font-weight:700;cursor:pointer} button.secondary{background:rgba(255,255,255,.06);color:var(--text)} button.warning{background:linear-gradient(135deg,#ffb84d,#ff8f3d)} button.danger{background:linear-gradient(135deg,#ff6b81,#ff4d6d)} button.success{background:linear-gradient(135deg,#35d39a,#25b97f)}
table{width:100%;border-collapse:collapse} th,td{border-bottom:1px solid var(--line);padding:12px;text-align:left;vertical-align:top} th{background:rgba(255,255,255,.04)} code{background:rgba(255,255,255,.06);padding:3px 6px;border-radius:8px}.notice{margin-top:12px;min-height:20px}
.bar{width:150px;height:10px;background:rgba(255,255,255,.08);border-radius:999px;overflow:hidden;border:1px solid var(--line)} .bar>span{display:block;height:100%;background:linear-gradient(90deg,var(--success),#68a8ff)} .stat{padding:16px;border-radius:16px;background:var(--card2);border:1px solid var(--line)} .stat .k{color:var(--muted);font-size:13px}.stat .v{font-size:26px;font-weight:800;margin-top:6px}
.pie-wrap{display:flex;gap:18px;flex-wrap:wrap;align-items:center}.pie{width:180px;height:180px;border-radius:50%;background:__CHART__}.legend{display:flex;flex-direction:column;gap:10px}.legend .item{display:flex;gap:10px;align-items:center}.sw{width:12px;height:12px;border-radius:999px;display:inline-block}.trend{display:flex;gap:12px;align-items:flex-end;height:180px}.trend-col{flex:1;display:flex;flex-direction:column;align-items:center;gap:8px}.trend-bar-wrap{height:120px;display:flex;align-items:flex-end}.trend-bar{width:28px;border-radius:10px 10px 4px 4px;background:linear-gradient(180deg,var(--primary),var(--primary2))}.trend-date,.trend-num{font-size:12px;color:var(--muted)}
.toast{position:fixed;right:22px;top:22px;z-index:10000;display:flex;flex-direction:column;gap:10px}.toast-item{min-width:220px;max-width:360px;padding:12px 14px;border-radius:12px;border:1px solid var(--line);background:var(--card);box-shadow:0 18px 45px rgba(0,0,0,.28);font-weight:700}.toast-item.ok{color:var(--success)}.toast-item.err{color:var(--danger)}.toast-item.info{color:var(--text)}.dir-modal{position:fixed;inset:0;background:rgba(0,0,0,.45);display:none;align-items:center;justify-content:center;z-index:9999;padding:24px}.dir-modal.open{display:flex}.dir-browser{width:min(900px,100%);max-height:85vh;overflow:hidden;padding:12px;border:1px solid var(--line);border-radius:16px;background:var(--card);box-shadow:0 20px 60px rgba(0,0,0,.35)} .dir-list{max-height:50vh;overflow:auto;margin-top:10px}.dir-item{display:flex;justify-content:space-between;gap:10px;padding:8px 10px;border-radius:8px}.dir-item:hover{background:rgba(255,255,255,.06)} .dir-path{font-size:12px;color:var(--muted);word-break:break-all}
@media (max-width:900px){.layout,.dashboard-grid,.login-grid,.grid,.stat-grid,.type-row{grid-template-columns:1fr}.sidebar{position:static}}
</style></head><body><div id="toast" class="toast"></div><div class="shell"><div class="hero"><div><h1 class="title">TG资源自动下载器</h1><div class="subtitle">释放我，填满你</div></div><div class="top-actions"><div class="theme-icons"><button type="button" class="theme-btn __SYSTEM_ACTIVE__" onclick="setTheme('system')">🖥️</button><button type="button" class="theme-btn __LIGHT_ACTIVE__" onclick="setTheme('light')">☀️</button><button type="button" class="theme-btn __DARK_ACTIVE__" onclick="setTheme('dark')">🌙</button></div><div class="badge"><span class="dot __DOT__"></span>__AUTH__</div>__LOGOUT__</div></div>__BODY__</div>
<script>
let activePathTarget = null;
async function api(url, options){const resp=await fetch(url, options||{}); const data=await resp.json(); if(!resp.ok) throw new Error(data.detail||'请求失败'); return data;}
function setNotice(id,text){const el=document.getElementById(id); if(el) el.textContent=text;}
function toast(text,type='info'){const box=document.getElementById('toast'); if(!box)return; const item=document.createElement('div'); item.className='toast-item '+type; item.textContent=text; box.appendChild(item); setTimeout(()=>item.remove(),3200);}
function initClickFeedback(){document.addEventListener('click',e=>{const btn=e.target.closest('button'); if(!btn||btn.classList.contains('nav-btn')||(btn.type==='submit'&&btn.closest('form'))||btn.closest('.dir-list'))return; toast('\u64cd\u4f5c\u5df2\u63d0\u4ea4','info');},true)}
function esc(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));}
function renderProgress(percent){const safe=Math.max(0,Math.min(100,percent||0)); return `<div class="bar"><span style="width:${safe}%"></span></div><div style="margin-top:6px;">${safe}%</div>`;}
function collectConfig(){const baseDir=document.getElementById('baseDir')?.value||''; return {download_dir:baseDir,web_port:parseInt(document.getElementById('webPort')?.value||'8080',10),theme_mode:document.documentElement.getAttribute('data-theme')||'system',enabled_types:Array.from(document.querySelectorAll('.type-check:checked')).map(x=>x.value),min_size_mb:parseFloat(document.getElementById('minSizeMb')?.value||'0'),max_size_mb:parseFloat(document.getElementById('maxSizeMb')?.value||'0'),min_free_percent:parseFloat(document.getElementById('minFreePercent')?.value||'0'),min_free_gb:parseFloat(document.getElementById('minFreeGb')?.value||'0'),unify:document.getElementById('unifyPaths')?.checked??true,base_dir:baseDir,video_dir:document.getElementById('videoDir')?.value||'',image_dir:document.getElementById('imageDir')?.value||'',document_dir:document.getElementById('documentDir')?.value||'',other_dir:document.getElementById('otherDir')?.value||'',naming_pattern:document.getElementById('namingPattern')?.value||'{original}',date_format:document.getElementById('dateFormat')?.value||'%Y-%m-%d',conflict_strategy:document.getElementById('conflictStrategy')?.value||'rename',resume_enabled:document.getElementById('resumeEnabled')?.checked??true}}
function applyNamingPreset(value){const input=document.getElementById('namingPattern'); if(input && value) input.value=value;}
function statusLabel(status){const text=status||'pending'; return `<span class="status-pill ${text}">${text}</span>`;}
function bindRange(rangeId,inputId){const range=document.getElementById(rangeId); const input=document.getElementById(inputId); if(!range||!input)return; const syncRange=()=>{const value=parseFloat(input.value||'0'); range.value=String(Math.max(parseFloat(range.min||'0'),Math.min(parseFloat(range.max||'100'),value)))}; const syncInput=()=>{input.value=range.value}; range.addEventListener('input',syncInput); input.addEventListener('input',syncRange); syncRange();}
function updateSizeRangeFill(){const minR=document.getElementById('minSizeMbRange'),maxR=document.getElementById('maxSizeMbRange'),fill=document.getElementById('sizeRangeFill'); if(!minR||!maxR||!fill)return; const limit=parseFloat(maxR.max||'10240'); const min=parseFloat(minR.value||'0'); const max=parseFloat(maxR.value||'0')||limit; fill.style.left=(min/limit*100)+'%'; fill.style.right=(100-(max/limit*100))+'%';}
function bindSizeRange(){const minR=document.getElementById('minSizeMbRange'),maxR=document.getElementById('maxSizeMbRange'),minI=document.getElementById('minSizeMb'),maxI=document.getElementById('maxSizeMb'); if(!minR||!maxR||!minI||!maxI)return; const clamp=()=>{let min=parseFloat(minI.value||'0'),max=parseFloat(maxI.value||'0'); min=Math.max(0,Math.min(10240,min)); max=Math.max(0,Math.min(10240,max)); if(max>0&&min>max)min=max; minI.value=String(min); maxI.value=String(max); minR.value=String(min); maxR.value=String(max||10240); updateSizeRangeFill();}; minR.addEventListener('input',()=>{const max=parseFloat(maxI.value||'0'); let value=parseFloat(minR.value||'0'); if(max>0&&value>max)value=max; minI.value=String(value); clamp()}); maxR.addEventListener('input',()=>{let value=parseFloat(maxR.value||'0'); const min=parseFloat(minI.value||'0'); if(value>0&&value<min)value=min; maxI.value=String(value); clamp()}); minI.addEventListener('input',clamp); maxI.addEventListener('input',clamp); clamp();}
function initSliders(){bindSizeRange();bindRange('minFreePercentRange','minFreePercent');bindRange('minFreeGbRange','minFreeGb'); const base=document.getElementById('baseDir'); if(base) base.addEventListener('input',syncUnifiedPaths);}
async function setTheme(mode){try{document.documentElement.setAttribute('data-theme',mode); const payload=collectConfig(); payload.theme_mode=mode; await api('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); document.querySelectorAll('.theme-btn').forEach(x=>x.classList.remove('active')); if(mode==='system') document.querySelectorAll('.theme-btn')[0].classList.add('active'); if(mode==='light') document.querySelectorAll('.theme-btn')[1].classList.add('active'); if(mode==='dark') document.querySelectorAll('.theme-btn')[2].classList.add('active'); toast('\u4e3b\u9898\u5df2\u5207\u6362','ok');}catch(err){toast('\u4e3b\u9898\u5207\u6362\u5931\u8d25: '+err.message,'err')}}
async function sendCode(e){e.preventDefault(); setNotice('sendCodeResult','\u53d1\u9001\u4e2d...'); try{await api('/api/login/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:document.getElementById('phone').value.trim()})}); setNotice('sendCodeResult','\u9a8c\u8bc1\u7801\u5df2\u53d1\u9001\u3002'); toast('\u9a8c\u8bc1\u7801\u5df2\u53d1\u9001','ok')}catch(err){setNotice('sendCodeResult','\u9519\u8bef: '+err.message); toast('\u53d1\u9001\u5931\u8d25: '+err.message,'err')}}
async function verifyCode(e){e.preventDefault(); setNotice('verifyCodeResult','\u767b\u5f55\u4e2d...'); try{await api('/api/login/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:document.getElementById('code').value.trim()})}); toast('\u767b\u5f55\u6210\u529f','ok'); location.reload()}catch(err){setNotice('verifyCodeResult','\u9519\u8bef: '+err.message); toast('\u767b\u5f55\u5931\u8d25: '+err.message,'err')}}
async function doLogout(){if(!confirm('\u786e\u5b9a\u9000\u51fa\u5f53\u524d Telegram \u767b\u5f55\u72b6\u6001\uff1f'))return; try{await api('/api/logout',{method:'POST'}); toast('\u5df2\u9000\u51fa\u767b\u5f55','ok'); location.reload()}catch(err){toast('\u9000\u51fa\u5931\u8d25: '+err.message,'err')}}
function initTabs(){document.querySelectorAll('.nav-btn').forEach(btn=>btn.addEventListener('click',()=>{const tab=btn.dataset.tab; document.querySelectorAll('.nav-btn').forEach(x=>{x.classList.add('secondary');x.classList.remove('active')}); btn.classList.remove('secondary'); btn.classList.add('active'); document.querySelectorAll('.section').forEach(sec=>sec.classList.remove('active')); const target=document.getElementById('tab-'+tab); if(target) target.classList.add('active'); if(tab==='channels') loadDialogs(); if(tab==='tasks') loadTasks()}))}
function syncUnifiedPaths(){const base=document.getElementById('baseDir')?.value||''; if(document.getElementById('unifyPaths')?.checked){['videoDir','imageDir','documentDir','otherDir'].forEach(id=>{const el=document.getElementById(id); if(el) el.value=base})}}
function togglePathMode(){const unify=document.getElementById('unifyPaths')?.checked; const base=document.getElementById('baseDir'); if(base) base.disabled=!unify; ['videoDir','imageDir','documentDir','otherDir'].forEach(id=>{const el=document.getElementById(id); if(el) el.disabled=!!unify}); syncUnifiedPaths()}
async function openDirBrowser(targetId){activePathTarget = targetId; const modal = document.getElementById('dirModal'); if(modal) modal.classList.add('open'); const current = document.getElementById(targetId)?.value || document.getElementById('baseDir')?.value || ''; await browseDir(current);}
async function browseDir(path){const list = document.getElementById('dirList'); const cur = document.getElementById('dirCurrent'); if(!list || !cur) return; list.innerHTML='读取中...'; try{const data = await api('/api/fs/list?path='+encodeURIComponent(path||'')); window.__dirCurrent = data.current; cur.textContent = data.current; const rows = [`<div class="row"><button class="secondary" onclick="selectCurrentDir()">选择当前目录</button><button class="secondary" onclick="browseParent()">返回上级</button></div>`]; for(const x of data.entries){const icon = x.isDir ? '📁' : '📄'; const enterBtn = x.isDir ? `<button class="secondary" data-path="${encodeURIComponent(x.path)}" onclick="browseDir(decodeURIComponent(this.dataset.path))">进入</button>` : ''; rows.push(`<div class="dir-item"><div><strong>${icon} ${x.name}</strong><div class="dir-path">${x.path}</div></div>${enterBtn}</div>`);} list.innerHTML = rows.join('');}catch(err){list.textContent='错误: '+err.message;}}
function browseParent(){const cur = window.__dirCurrent || ''; if(!cur) return; const normalized = cur.replace(/[\\/]+$/,''); const parent = normalized.replace(/[\\/][^\\/]+$/,'') || normalized; browseDir(parent===normalized ? cur : parent);}
function selectCurrentDir(){if(!activePathTarget) return; const cur = window.__dirCurrent || ''; const input = document.getElementById(activePathTarget); if(input) input.value = cur; closeDirBrowser(); syncUnifiedPaths(); toast('\u76ee\u5f55\u5df2\u9009\u62e9','ok');}
function closeDirBrowser(){const modal=document.getElementById('dirModal'); if(modal) modal.classList.remove('open');}
async function createDirFromBrowser(){const name = prompt('\u65b0\u5efa\u6587\u4ef6\u5939\u540d\u79f0\uff1a'); if(!name) return; try{const cur = window.__dirCurrent || ''; const res = await api('/api/fs/mkdir',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base:cur,name})}); await browseDir(res.path); toast('\u6587\u4ef6\u5939\u5df2\u521b\u5efa','ok');}catch(err){toast('\u521b\u5efa\u5931\u8d25: '+err.message,'err')}}
async function makeDir(targetId){const input=document.getElementById(targetId); const base=input?.value||''; const name=prompt('\u65b0\u5efa\u6587\u4ef6\u5939\u540d\u79f0\uff1a'); if(!name)return; try{const res=await api('/api/fs/mkdir',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base,name})}); if(input) input.value=res.path; setNotice('configResult','\u76ee\u5f55\u5df2\u521b\u5efa\uff1a'+res.path); syncUnifiedPaths(); toast('\u76ee\u5f55\u5df2\u521b\u5efa','ok');}catch(err){toast('\u521b\u5efa\u5931\u8d25: '+err.message,'err')}}
async function loadDialogs(){const box=document.getElementById('dialogs'); if(!box) return; box.textContent='\u8bfb\u53d6\u4e2d...'; try{const items=await api('/api/dialogs'); box.innerHTML='<table><thead><tr><th><input type=\"checkbox\" onchange=\"toggleAllChats(this.checked)\" /></th><th>\u6807\u9898</th><th>ID</th><th>\u7c7b\u578b</th><th>\u7528\u6237\u540d</th></tr></thead><tbody>'+items.map(x=>`<tr><td><input type=\"checkbox\" class=\"chat-check\" value=\"${x.id}\" ${x.selected?'checked':''} /></td><td>${x.title}</td><td><code>${x.id}</code></td><td>${x.kind}</td><td>${x.username||''}</td></tr>`).join('')+'</tbody></table>'; toast('\u4f1a\u8bdd\u5217\u8868\u5df2\u5237\u65b0','ok')}catch(err){box.textContent='\u9519\u8bef: '+err.message; toast('\u8bfb\u53d6\u4f1a\u8bdd\u5931\u8d25: '+err.message,'err')}}
function toggleAllChats(checked){document.querySelectorAll('.chat-check').forEach(x=>x.checked=checked)}
async function saveSelectedChats(){const ids=Array.from(document.querySelectorAll('.chat-check:checked')).map(x=>x.value); setNotice('listenResult','\u4fdd\u5b58\u4e2d...'); try{await api('/api/listen/chats',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_ids:ids})}); setNotice('listenResult',`\u5df2\u4fdd\u5b58 ${ids.length} \u4e2a\u76d1\u542c\u5bf9\u8c61\u3002`); toast('\u76d1\u542c\u5bf9\u8c61\u5df2\u4fdd\u5b58','ok')}catch(err){setNotice('listenResult','\u9519\u8bef: '+err.message); toast('\u4fdd\u5b58\u5931\u8d25: '+err.message,'err')}}
async function toggleListening(on){setNotice('listenResult',on?'\u5f00\u542f\u4e2d...':'\u505c\u6b62\u4e2d...'); try{await api(on?'/api/listen/start':'/api/listen/stop',{method:'POST'}); setNotice('listenResult',on?'\u5df2\u5f00\u542f\u76d1\u542c\u3002':'\u5df2\u505c\u6b62\u76d1\u542c\u3002'); toast(on?'\u76d1\u542c\u5df2\u5f00\u542f':'\u76d1\u542c\u5df2\u505c\u6b62','ok'); location.reload()}catch(err){setNotice('listenResult','\u9519\u8bef: '+err.message); toast('\u76d1\u542c\u64cd\u4f5c\u5931\u8d25: '+err.message,'err')}}
async function updateDashboardPeriod(period){try{const data=await api('/api/dashboard?period='+encodeURIComponent(period)); const pie=document.getElementById('dashboardPie'); if(pie) pie.style.background=data.today_chart; const title=document.getElementById('chartTitle'); if(title) title.textContent=data.period_label+'\u4e0b\u8f7d\u6570\u91cf\u5360\u6bd4'; const c=document.getElementById('legendCompleted'); if(c) c.textContent='\u5df2\u5b8c\u6210\uff1a'+data.today_completed; const d=document.getElementById('legendDownloading'); if(d) d.textContent='\u4e0b\u8f7d\u4e2d\uff1a'+data.today_downloading; const o=document.getElementById('legendOther'); if(o) o.textContent='\u5176\u4ed6\uff1a'+data.today_other; toast('\u7edf\u8ba1\u89c6\u56fe\u5df2\u5237\u65b0','ok')}catch(err){toast('\u5237\u65b0\u7edf\u8ba1\u5931\u8d25: '+err.message,'err')}}
async function saveConfig(e){e.preventDefault(); setNotice('configResult','\u4fdd\u5b58\u4e2d...'); try{await api('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(collectConfig())}); setNotice('configResult','\u914d\u7f6e\u5df2\u4fdd\u5b58\uff1b\u5982\u679c\u4fee\u6539\u4e86\u7aef\u53e3\uff0c\u8bf7\u7528\u65b0\u7aef\u53e3\u91cd\u65b0\u8bbf\u95ee\u3002'); togglePathMode(); toast('\u914d\u7f6e\u5df2\u4fdd\u5b58','ok')}catch(err){setNotice('configResult','\u9519\u8bef: '+err.message); toast('\u4fdd\u5b58\u914d\u7f6e\u5931\u8d25: '+err.message,'err')}}
async function taskAction(taskId, action){try{await api(`/api/tasks/${taskId}/${action}`,{method:'POST'}); await loadTasks(true); toast('\u4efb\u52a1\u64cd\u4f5c\u5df2\u5b8c\u6210','ok')}catch(err){toast('\u64cd\u4f5c\u5931\u8d25: '+err.message,'err')}}
function toggleAllTasks(checked){document.querySelectorAll('.task-check').forEach(x=>x.checked=checked)}
async function batchTask(action){const ids=Array.from(document.querySelectorAll('.task-check:checked')).map(x=>x.value); if(!ids.length){toast('\u8bf7\u5148\u52fe\u9009\u4efb\u52a1','err'); return;} if(action==='cancel'&&!confirm(`\u786e\u5b9a\u53d6\u6d88\u9009\u4e2d\u7684 ${ids.length} \u4e2a\u4efb\u52a1\uff0c\u5e76\u5220\u9664\u5df2\u4e0b\u8f7d\u7684\u90e8\u5206\u6587\u4ef6\uff1f`))return; try{await api('/api/tasks/batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_ids:ids,action})}); await loadTasks(true); const names={pause:'\u6279\u91cf\u6682\u505c\u5df2\u5b8c\u6210',resume:'\u6279\u91cf\u7ee7\u7eed\u5df2\u5b8c\u6210',cancel:'\u5df2\u53d6\u6d88\u5e76\u5220\u9664\u90e8\u5206\u6587\u4ef6'}; toast(names[action]||'\u6279\u91cf\u64cd\u4f5c\u5df2\u5b8c\u6210','ok')}catch(err){toast('\u6279\u91cf\u64cd\u4f5c\u5931\u8d25: '+err.message,'err')}}
async function cleanupParts(){if(!confirm('\u786e\u5b9a\u6e05\u7406\u4e0b\u8f7d\u76ee\u5f55\u4e2d\u7684\u5b64\u513f .part \u4e34\u65f6\u6587\u4ef6\uff1f\u6b63\u5728\u4e0b\u8f7d\u6216\u53ef\u7eed\u4f20\u7684\u4efb\u52a1\u4e34\u65f6\u6587\u4ef6\u4f1a\u88ab\u4fdd\u7559\u3002'))return; try{const res=await api('/api/tasks/cleanup-parts',{method:'POST'}); toast(`\u5df2\u6e05\u7406 ${res.deleted_count} \u4e2a\u4e34\u65f6\u6587\u4ef6\uff0c\u91ca\u653e ${(res.deleted_bytes/1024/1024/1024).toFixed(2)} GB\u3002`,'ok'); await loadTasks(true)}catch(err){toast('\u6e05\u7406\u5931\u8d25: '+err.message,'err')}}
async function saveResumeSetting(checked){try{const payload=collectConfig(); payload.resume_enabled=checked; await api('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); toast('\u65ad\u70b9\u7eed\u4f20\u8bbe\u7f6e\u5df2\u4fdd\u5b58','ok');}catch(err){toast('\u4fdd\u5b58\u65ad\u70b9\u7eed\u4f20\u8bbe\u7f6e\u5931\u8d25: '+err.message,'err')}}
async function loadTasks(showToast=false){const box=document.getElementById('tasks'); if(!box) return; try{const allItems=await api('/api/tasks'); const visibleStatuses=new Set(['pending','downloading','paused','error']); const items=allItems.filter(x=>visibleStatuses.has(x.status||'')); const hidden=allItems.length-items.length; if(showToast) toast('\u4efb\u52a1\u5217\u8868\u5df2\u5237\u65b0','ok'); if(!items.length){box.innerHTML=`<p class=\"muted\">\u5f53\u524d\u6ca1\u6709\u9700\u8981\u5904\u7406\u7684\u4e0b\u8f7d\u4efb\u52a1\u3002\u5df2\u9690\u85cf\u5b8c\u6210/\u53d6\u6d88\u4efb\u52a1\uff0c\u5171 ${hidden} \u4e2a\u3002</p>`; return;} box.innerHTML=`<div class=\"hint\" style=\"margin-bottom:10px;\">\u4ec5\u663e\u793a\u5f85\u5904\u7406\u4efb\u52a1\uff1a${items.length} \u4e2a\uff1b\u5df2\u9690\u85cf\u5b8c\u6210/\u53d6\u6d88\u4efb\u52a1\uff1a${hidden} \u4e2a\u3002\u52fe\u9009\u4efb\u52a1\u540e\u4f7f\u7528\u4e0a\u65b9\u6279\u91cf\u6309\u94ae\u64cd\u4f5c\u3002</div>`+'<div class=\"table-wrap\"><table class=\"task-table\"><thead><tr><th><input type=\"checkbox\" onchange=\"toggleAllTasks(this.checked)\" /></th><th>ID</th><th>\u7c7b\u578b</th><th>\u539f\u6587\u4ef6\u540d</th><th>\u72b6\u6001</th><th>\u8fdb\u5ea6</th><th>\u76ee\u6807 / \u4e34\u65f6\u8def\u5f84</th><th>\u9519\u8bef</th></tr></thead><tbody>'+items.map(x=>{const target=x.saved_path||x.target_path||x.temp_path||''; return `<tr><td><input type=\"checkbox\" class=\"task-check\" value=\"${esc(x.id)}\" /></td><td><code class=\"ellipsis\" title=\"${esc(x.id)}\">${esc(x.id)}</code></td><td>${esc(x.media_type||'')}</td><td class=\"path-cell\"><span class=\"ellipsis\" title=\"${esc(x.file_name)}\">${esc(x.file_name)}</span></td><td>${statusLabel(x.status)}</td><td>${renderProgress(x.progress_percent)}</td><td class=\"path-cell\"><span class=\"ellipsis\" title=\"${esc(target)}\">${esc(target)}</span></td><td class=\"path-cell\"><span class=\"ellipsis\" title=\"${esc(x.error||'')}\">${esc(x.error||'')}</span></td></tr>`}).join('')+'</tbody></table></div>'}catch(err){box.textContent='\u9519\u8bef: '+err.message; if(showToast) toast('\u5237\u65b0\u4efb\u52a1\u5931\u8d25: '+err.message,'err')}}
initTabs(); initClickFeedback(); togglePathMode(); initSliders(); loadTasks(); setInterval(loadTasks,3000);
</script></body></html>'''
    for k, v in ctx.items():
        html = html.replace(k, v)
    return html


@app.get('/', response_class=HTMLResponse)
async def index():
    authed = await is_authorized()
    cfg = settings.app_config
    dashboard = get_dashboard_stats()
    tasks = list_tasks()
    trend_max = max([i['count'] for i in dashboard['trend']] + [1])
    bars = ''.join(f"<div class='trend-col'><div class='trend-bar-wrap'><div class='trend-bar' style='height:{max(8, int(i['count']/trend_max*120))}px'></div></div><div class='trend-num'>{i['count']}</div><div class='trend-date'>{i['date']}</div></div>" for i in dashboard['trend'])
    storage = settings.get_storage_status()
    enabled = {getattr(x, 'value', x) for x in cfg.filters.enabled_types}
    theme = cfg.theme_mode.value if hasattr(cfg.theme_mode, 'value') else str(cfg.theme_mode)
    dir_browser = '<div id="dirModal" class="dir-modal" onclick="if(event.target===this) closeDirBrowser()"><div id="dirBrowser" class="dir-browser" onclick="event.stopPropagation()"><div class="row"><strong>选择目录</strong><button class="secondary" onclick="closeDirBrowser()">关闭</button></div><div class="dir-path" id="dirCurrent"></div><div class="row" style="margin-top:10px"><button class="secondary" onclick="browseParent()">返回上级</button><button class="success" onclick="createDirFromBrowser()">新建文件夹</button><button onclick="selectCurrentDir()">选择当前目录</button></div><div id="dirList" class="dir-list"></div></div></div>'
    if not authed:
        body = '<div class="login-wrap"><div class="card login-card"><div style="font-size:24px;font-weight:800;">登录 Telegram</div><div class="subtitle">登录后进入控制台。</div><div class="login-grid"><div class="pane"><h3>第一步：发送验证码</h3><form onsubmit="sendCode(event)"><div class="field"><label>手机号（带国家区号）</label><input type="text" id="phone" placeholder="例如 +8613812345678" required /></div><div style="margin-top:14px;"><button type="submit">发送验证码</button></div></form><div class="notice" id="sendCodeResult"></div></div><div class="pane"><h3>第二步：输入验证码</h3><form onsubmit="verifyCode(event)"><div class="field"><label>验证码</label><input type="text" id="code" required /></div><div style="margin-top:14px;"><button type="submit" class="success">完成登录</button></div></form><div class="notice" id="verifyCodeResult"></div></div></div></div></div>'
    else:
        body = f'''<div class="layout"><aside class="card sidebar"><div style="font-weight:800;font-size:18px;">控制台</div><div class="muted">当前监听：<strong style="color:var(--text)">{'开启' if is_listening() else '关闭'}</strong></div><div class="nav"><button class="nav-btn active" data-tab="dashboard">🏠 概览</button><button class="nav-btn secondary" data-tab="channels">📡 群组 / 频道</button><button class="nav-btn secondary" data-tab="filters">⚙️ 过滤与系统</button><button class="nav-btn secondary" data-tab="tasks">⬇️ 下载任务</button></div></aside><main class="content">
<section id="tab-dashboard" class="card section active"><div class="section-head"><h2>概览</h2><div class="row"><button onclick="toggleListening(true)" class="success">开启监听</button><button onclick="toggleListening(false)" class="danger">停止监听</button></div></div><div class="stat-grid"><div class="stat"><div class="k">已监听数量</div><div class="v">{len(get_listened_chats())}</div></div><div class="stat"><div class="k">任务总数</div><div class="v">{len(tasks)}</div></div><div class="stat"><div class="k">已完成数</div><div class="v">{sum(1 for t in tasks.values() if str(t.status).endswith('completed') or str(t.status)=='completed')}</div></div></div><div class="dashboard-grid"><div class="pane"><div class="row" style="justify-content:space-between;margin-bottom:12px;"><div id="chartTitle" style="font-weight:700;">今日下载数量占比</div><select style="width:auto;min-width:96px;" onchange="updateDashboardPeriod(this.value)"><option value="day">按日</option><option value="week">按周</option><option value="year">按年</option></select></div><div class="pie-wrap"><div id="dashboardPie" class="pie"></div><div class="legend"><div class="item"><span class="sw" style="background:#35d39a"></span><span id="legendCompleted">已完成：{dashboard['today_completed']}</span></div><div class="item"><span class="sw" style="background:#6ea8fe"></span><span id="legendDownloading">下载中：{dashboard['today_downloading']}</span></div><div class="item"><span class="sw" style="background:#ffb84d"></span><span id="legendOther">其他：{dashboard['today_other']}</span></div></div></div></div><div class="pane"><div style="font-weight:700;margin-bottom:12px;">存储空间状态</div><div class="muted">路径：{storage['path']}</div><div style="margin-top:10px;font-size:18px;font-weight:700;">剩余 {storage['free_gb']} GB / {storage['free_percent']}%</div></div></div><div class="pane" style="margin-top:14px;"><div style="font-weight:700;margin-bottom:12px;">近7天下载趋势</div><div class="trend">{bars}</div></div><div class="notice" id="listenResult"></div></section>
<section id="tab-channels" class="card section"><div class="section-head"><h2>群组 / 频道</h2><div class="row"><button onclick="loadDialogs()">读取会话列表</button><button class="success" onclick="saveSelectedChats()">保存勾选项</button></div></div><div id="dialogs" style="margin-top:14px;"><div class="muted">点击“读取会话列表”开始。</div></div></section>
<section id="tab-filters" class="card section"><div class="section-head"><h2>过滤与系统设置</h2><div class="hint">推荐命名：<code>{{date}}_{{original}}</code>，方便按下载日期整理且保留原始文件名。</div></div><form onsubmit="saveConfig(event)"><div class="grid"><div class="pane"><div class="setting-title">服务</div><div class="field"><label>监听端口</label><input type="number" id="webPort" min="1" max="65535" value="{cfg.web_port}" /></div></div><div class="pane" style="grid-column:1 / -1;"><div class="setting-title">目录设置</div><div class="grid"><div><label class="switchline"><input type="checkbox" id="unifyPaths" {'checked' if cfg.storage_paths.unify else ''} onchange="togglePathMode()" /> 一键全部保持一致</label><div class="hint">勾选后使用统一目录，分类目录自动保持一致；关闭后可分别设置分类目录。</div></div><div><div class="field"><label>统一目录</label><input type="text" id="baseDir" value="{cfg.storage_paths.base_dir or cfg.download_dir or ''}" /></div><div class="row" style="margin-top:10px;"><button type="button" class="secondary" onclick="openDirBrowser('baseDir')">浏览目录</button><button type="button" class="success" onclick="makeDir('baseDir')">新建目录</button></div></div></div></div><div class="pane" style="grid-column:1 / -1;"><div class="setting-head"><div><div class="setting-title">分类目录</div><div class="hint">勾选某一类型代表下载该类型文件；取消勾选则跳过该类型。</div></div></div><div class="type-row"><div class="checkline"><label><input type="checkbox" class="type-check" value="video" {'checked' if 'video' in enabled else ''}/> 视频</label></div><input type="text" id="videoDir" value="{cfg.storage_paths.video_dir or ''}" /><button type="button" class="secondary" onclick="openDirBrowser('videoDir')">浏览目录</button><button type="button" class="success" onclick="makeDir('videoDir')">新建目录</button></div><div class="type-row"><div class="checkline"><label><input type="checkbox" class="type-check" value="image" {'checked' if 'image' in enabled else ''}/> 图片</label></div><input type="text" id="imageDir" value="{cfg.storage_paths.image_dir or ''}" /><button type="button" class="secondary" onclick="openDirBrowser('imageDir')">浏览目录</button><button type="button" class="success" onclick="makeDir('imageDir')">新建目录</button></div><div class="type-row"><div class="checkline"><label><input type="checkbox" class="type-check" value="document" {'checked' if 'document' in enabled else ''}/> 文档</label></div><input type="text" id="documentDir" value="{cfg.storage_paths.document_dir or ''}" /><button type="button" class="secondary" onclick="openDirBrowser('documentDir')">浏览目录</button><button type="button" class="success" onclick="makeDir('documentDir')">新建目录</button></div><div class="type-row"><div class="checkline"><label><input type="checkbox" class="type-check" value="other" {'checked' if 'other' in enabled else ''}/> 其他文件</label></div><input type="text" id="otherDir" value="{cfg.storage_paths.other_dir or ''}" /><button type="button" class="secondary" onclick="openDirBrowser('otherDir')">浏览目录</button><button type="button" class="success" onclick="makeDir('otherDir')">新建目录</button></div></div><div class="pane" style="grid-column:1 / -1;"><div class="setting-title">文件命名</div><div class="grid"><div class="field"><label>命名预设</label><select id="namingPreset" onchange="applyNamingPreset(this.value)"><option value="{{original}}">原文件名</option><option value="{{date}}_{{original}}">下载日期 + 原文件名</option><option value="{{datetime}}_{{original}}">下载时间 + 原文件名</option><option value="{{chat_id}}_{{message_id}}_{{original}}">群组消息ID + 原文件名</option><option value="{{type}}_{{date}}_{{original}}">类型 + 日期 + 原文件名</option></select></div><div class="field"><label>冲突处理</label><select id="conflictStrategy"><option value="rename" {'selected' if cfg.naming.conflict_strategy == 'rename' else ''}>自动重命名</option><option value="overwrite" {'selected' if cfg.naming.conflict_strategy == 'overwrite' else ''}>覆盖旧文件</option><option value="skip" {'selected' if cfg.naming.conflict_strategy == 'skip' else ''}>已存在则跳过</option></select></div></div><div class="field" style="margin-top:12px;"><label>自定义命名模板</label><input type="text" id="namingPattern" value="{cfg.naming.pattern}" /></div><div class="hint">可用变量：<code>{{date}}</code>、<code>{{datetime}}</code>、<code>{{original}}</code>、<code>{{stem}}</code>、<code>{{ext}}</code>、<code>{{chat_id}}</code>、<code>{{message_id}}</code>、<code>{{type}}</code>。</div><div class="grid" style="margin-top:12px;"><div class="field"><label>日期格式</label><select id="dateFormat"><option value="%Y-%m-%d" {'selected' if cfg.naming.date_format == '%Y-%m-%d' else ''}>2026-06-13</option><option value="%Y%m%d" {'selected' if cfg.naming.date_format == '%Y%m%d' else ''}>20260613</option><option value="%Y_%m_%d" {'selected' if cfg.naming.date_format == '%Y_%m_%d' else ''}>2026_06_13</option><option value="%m-%d" {'selected' if cfg.naming.date_format == '%m-%d' else ''}>06-13</option><option value="%Y-%m" {'selected' if cfg.naming.date_format == '%Y-%m' else ''}>2026-06</option></select></div><div class="hint" style="align-self:end;">该格式影响命名模板里的 <code>{{date}}</code>。</div></div></div><div class="pane" style="grid-column:1 / -1;"><div class="setting-head"><div><div class="setting-title">文件体积范围</div><div class="hint">左侧设置最小体积，右侧设置最大体积；最大值为 0 表示不限制上限。</div></div></div><div class="range-pair"><span id="sizeRangeFill" class="range-fill"></span><input type="range" id="minSizeMbRange" min="0" max="10240" step="1" value="{cfg.filters.min_size_mb}" /><input type="range" id="maxSizeMbRange" min="0" max="10240" step="10" value="{cfg.filters.max_size_mb}" /></div><div class="size-values"><div><label>最小体积（MB）</label><input type="number" id="minSizeMb" step="0.1" min="0" value="{cfg.filters.min_size_mb}" /></div><div><label>最大体积（MB）</label><input type="number" id="maxSizeMb" step="0.1" min="0" value="{cfg.filters.max_size_mb}" /></div></div><div class="metric"><span>最小 0 MB</span><span>最大 10240 MB / 0 为不限</span></div></div><div class="pane"><div class="setting-head"><div><div class="setting-title">剩余空间百分比保护</div><div class="hint">低于该百分比时停止创建新下载，0 表示关闭。</div></div></div><div class="slider-field"><input type="range" id="minFreePercentRange" min="0" max="100" step="1" value="{cfg.storage_guard.min_free_percent}" /><input type="number" id="minFreePercent" step="0.1" min="0" max="100" value="{cfg.storage_guard.min_free_percent}" /></div><div class="metric"><span>关闭</span><span>100%</span></div></div><div class="pane"><div class="setting-head"><div><div class="setting-title">剩余空间容量保护</div><div class="hint">低于该容量时停止创建新下载，0 表示关闭。</div></div></div><div class="slider-field"><input type="range" id="minFreeGbRange" min="0" max="1024" step="1" value="{cfg.storage_guard.min_free_gb}" /><input type="number" id="minFreeGb" step="0.1" min="0" value="{cfg.storage_guard.min_free_gb}" /></div><div class="metric"><span>关闭</span><span>1024 GB</span></div></div></div><div style="margin-top:14px;"><button type="submit">保存配置</button></div></form>{dir_browser}<div class="notice" id="configResult"></div></section>
<section id="tab-tasks" class="card section"><div class="section-head"><h2>下载任务</h2><div class="row"><label class="task-switch"><input type="checkbox" id="resumeEnabled" {'checked' if cfg.naming.resume_enabled else ''} onchange="saveResumeSetting(this.checked)" /> 断点续传</label><button onclick="loadTasks(true)">刷新任务列表</button><button class="secondary" onclick="batchTask('pause')">批量暂停</button><button class="secondary" onclick="batchTask('resume')">批量继续</button><button class="secondary" onclick="batchTask('cancel')">取消并删除部分文件</button><button class="secondary" onclick="cleanupParts()">清理临时文件</button></div></div><div id="tasks"></div></section></main></div>'''
    return render_page({'__THEME__': theme, '__CHART__': dashboard['today_chart'], '__DOT__': 'ok' if authed else 'off', '__AUTH__': '已登录' if authed else '未登录', '__LOGOUT__': '<button class="danger" onclick="doLogout()">退出登录</button>' if authed else '', '__BODY__': body, '__SYSTEM_ACTIVE__': 'active' if theme == 'system' else '', '__LIGHT_ACTIVE__': 'active' if theme == 'light' else '', '__DARK_ACTIVE__': 'active' if theme == 'dark' else ''})


class PhonePayload(BaseModel): phone: str
class CodePayload(BaseModel): code: str
class ChatIdsPayload(BaseModel): chat_ids: list[str]
class ConfigPayload(BaseModel):
    download_dir: str = ''
    web_port: int = 8080
    theme_mode: str = 'system'
    enabled_types: list[str] = []
    min_size_mb: float = 0
    max_size_mb: float = 0
    min_free_percent: float = 0
    min_free_gb: float = 0
    unify: bool = True
    base_dir: str = ''
    video_dir: str = ''
    image_dir: str = ''
    document_dir: str = ''
    other_dir: str = ''
    naming_pattern: str = '{original}'
    date_format: str = '%Y-%m-%d'
    conflict_strategy: str = 'rename'
    resume_enabled: bool = True
class BatchPayload(BaseModel): task_ids: list[str]; action: str
class MkdirPayload(BaseModel): base: str; name: str

@app.post('/api/login/start')
async def api_login_start(payload: PhonePayload):
    try: await start_login(payload.phone)
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
    return {'ok': True}
@app.post('/api/login/verify')
async def api_login_verify(payload: CodePayload):
    try: await complete_login(payload.code)
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
    return {'ok': True}
@app.post('/api/logout')
async def api_logout():
    try: await logout()
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
    return {'ok': True}
@app.post('/api/listen/chats')
async def api_listen_chats(payload: ChatIdsPayload):
    try: set_listened_chats([int(raw) for raw in payload.chat_ids if raw])
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
    return {'ok': True}
@app.post('/api/listen/start')
async def api_listen_start():
    try: await start_listening()
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
    return {'ok': True}
@app.post('/api/listen/stop')
async def api_listen_stop():
    try: await stop_listening()
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
    return {'ok': True}
@app.post('/api/config')
async def api_config(payload: ConfigPayload):
    try:
        cfg = settings.update_app_config(download_dir=ensure_dir(payload.download_dir) if payload.download_dir else '', web_port=payload.web_port, theme_mode=payload.theme_mode, enabled_types=payload.enabled_types, min_size_mb=payload.min_size_mb, max_size_mb=payload.max_size_mb, min_free_percent=payload.min_free_percent, min_free_gb=payload.min_free_gb, unify=payload.unify, base_dir=ensure_dir(payload.base_dir) if payload.base_dir else '', video_dir=ensure_dir(payload.video_dir) if payload.video_dir else '', image_dir=ensure_dir(payload.image_dir) if payload.image_dir else '', document_dir=ensure_dir(payload.document_dir) if payload.document_dir else '', other_dir=ensure_dir(payload.other_dir) if payload.other_dir else '', naming_pattern=payload.naming_pattern, date_format=payload.date_format, conflict_strategy=payload.conflict_strategy, resume_enabled=payload.resume_enabled)
        return cfg.model_dump(mode='json')
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
@app.get('/api/status')
async def api_status():
    return {'authorized': await is_authorized(), 'listening': is_listening(), 'chats': get_listened_chats(), 'config': settings.app_config.model_dump(mode='json'), 'storage': settings.get_storage_status(), 'dashboard': get_dashboard_stats(), 'web_port': settings.port}
@app.get('/api/dashboard')
async def api_dashboard(period: str = 'day'):
    return get_dashboard_stats(period)
@app.get('/api/dialogs')
async def api_dialogs():
    try: return await list_dialogs()
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
@app.get('/api/tasks')
async def api_tasks():
    return [t.model_dump(mode='json') for t in list_tasks().values()]
@app.post('/api/tasks/batch')
async def api_tasks_batch(payload: BatchPayload):
    try: return await batch_action(payload.task_ids, payload.action)
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
@app.post('/api/tasks/cleanup-parts')
async def api_tasks_cleanup_parts():
    try: return cleanup_orphan_partial_files()
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
@app.post('/api/tasks/{task_id}/pause')
async def api_task_pause(task_id: str):
    try: await pause_task(task_id); return {'ok': True}
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
@app.post('/api/tasks/{task_id}/cancel')
async def api_task_cancel(task_id: str):
    try: await cancel_task(task_id); return {'ok': True}
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
@app.post('/api/tasks/{task_id}/retry')
async def api_task_retry(task_id: str):
    try: await retry_task(task_id); return {'ok': True}
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
@app.get('/api/fs/list')
async def api_fs_list(path: str = ''):
    try: return safe_dir_listing(path or None)
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
@app.post('/api/fs/mkdir')
async def api_fs_mkdir(payload: MkdirPayload):
    try:
        base = Path(payload.base).expanduser().resolve()
        target = base / payload.name
        target.mkdir(parents=True, exist_ok=True)
        return {'ok': True, 'path': str(target)}
    except Exception as e: raise HTTPException(status_code=400, detail=str(e))
