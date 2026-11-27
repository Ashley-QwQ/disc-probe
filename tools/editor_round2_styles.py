from pathlib import Path
p=Path('discprobe/web/home/design.css');s=p.read_text(encoding='utf8');s=s[:s.index('/* Editor cards 2–4:')]
s+='''/* Editor round 2: compact lists and canvas-owned tools; existing glass plane. */
.ws .col { background:var(--sheet,var(--paper)); }
.ws .col-r { display:flex; padding:16px 12px; border-radius:8px; overflow:hidden; box-shadow:var(--glass-far,var(--glass-desk)); }
.ws .tools-v,.ws .filebtns { filter:var(--glass-drive-drop); }
.ws .tools-v { top:64px; gap:3px; overflow:visible; }
.ws .tb { position:relative; }
.ws .tb[aria-pressed="true"] { color:var(--copper); background:var(--paper-2); border-color:var(--copper); }
.ws .ed-tip { pointer-events:none; position:absolute; z-index:6; left:46px; padding:5px 8px; border-radius:4px; background:var(--paper); color:var(--ink); box-shadow:var(--glass-near,var(--glass-drive)); white-space:nowrap; font:14px var(--font); opacity:0; }
.ws .tb:hover .ed-tip,.ws .tb:focus-visible .ed-tip { opacity:1; }
.ws .ed-tip kbd { margin-left:8px; color:var(--ink-2); font:12px var(--mono); }
.ws .lay { grid-template-columns:32px minmax(0,1fr) repeat(5,24px); gap:3px; min-height:44px; padding:4px; }
.ws .lay canvas,.ws .lay .fxmark { width:32px;height:32px;filter:grayscale(1); }
.ws .lay .ib { width:24px;height:32px; }
.ws .lay .ib svg { width:16px;height:16px; }
.ws .lay .nm { font-size:14px; }
.ws .lay[aria-selected="true"],.ws .ed-mask[aria-selected="true"] { border-color:var(--copper); background:var(--paper-2); }
.ws .lay .row-action { opacity:0; }
.ws .lay:hover .row-action,.ws .lay:focus-within .row-action,.ws .lay[aria-selected="true"] .row-action { opacity:1; }
.ws .ed-mask-list { list-style:none;margin:0;padding:0;display:grid;gap:2px; }
.ws .ed-mask { display:grid;grid-template-columns:32px minmax(0,1fr) 28px;gap:8px;align-items:center;min-height:44px;padding:4px;border:1px solid transparent;border-radius:4px;cursor:pointer;font-size:14px; }
.ws .ed-mask canvas { width:32px;height:32px;border-radius:2px; }
.ws .ed-mask:hover { background:var(--paper-2); }
.ws .ed-mask .ib { width:28px;height:32px; }
.ws .ed-mask input,.ws .lay input { width:100%;min-width:0;background:var(--paper);color:var(--ink);border:1px solid var(--rule-strong);border-radius:4px;padding:4px;font:inherit; }
.ws .ed-selections h3 .grow { flex:1; }
.ws .ed-options { position:absolute;z-index:3;left:56px;right:0;top:0;min-height:48px;display:flex;align-items:center;gap:8px;padding:4px 8px;border-radius:8px;background:var(--paper);box-shadow:var(--glass-near,var(--glass-drive)); }
.ws .ed-options>label { display:grid;gap:2px;width:72px;font-size:12px;color:var(--ink-2);white-space:nowrap; }
.ws .ed-options input[type=number] { width:64px;min-height:28px;padding:2px 4px;border:1px solid var(--rule-strong);border-radius:4px;background:var(--paper);color:var(--ink);font:14px var(--font);font-variant-numeric:tabular-nums; }
.ws .ed-options select { min-width:100px;min-height:28px;background:var(--paper);color:var(--ink);border:1px solid var(--rule-strong);border-radius:4px;font:14px var(--font); }
.ws .ed-options>label:has(select) { width:130px; }
.ws .ed-options .ed-inline { display:flex;width:auto;align-items:center;gap:4px; }
.ws .ed-options input[type=checkbox] { width:16px;height:16px;accent-color:var(--ink); }
.ws .ed-ops { display:flex;gap:2px;border-left:1px solid var(--rule);padding-left:8px; }
.ws .ed-options .ib { width:28px;height:32px; }
.ws .ed-options .ib svg { width:18px;height:18px; }
.ws .ed-options .ib[aria-pressed=true] { color:var(--copper);border-color:var(--copper); }
.ws .ed-option-hint { font-size:13px;color:var(--ink-2); }
.ws .fbar { border:0;box-shadow:var(--glass-near,var(--glass-drive));max-width:calc(100% - 56px);overflow-x:auto;gap:6px;padding:6px;font-size:12px; }
.ws .fbar input { width:46px;font-size:13px; }
.ws .fbar input.short { width:46px; }
.ws .fbar label { gap:4px; }
.ws .fbar input[type=range].rng { width:64px; }
.ws .viewsw { top:auto;bottom:0; }
.ws .viewsw button { min-height:32px;padding:0 10px;font-size:13px; }
.ws .zoomr { left:56px;right:auto;bottom:0; }
.ws .cv-note { left:112px;right:180px;top:auto;bottom:0;min-height:34px;max-height:44px;transform:none;margin:0;padding:1px 8px;white-space:normal;justify-content:center;text-align:center;font-size:12px;line-height:1.3;background:none;overflow:auto; }
.ws .empty-c { top:62%; }
.ws .empty-c p { color:var(--face-ink);font-size:17px; }
.ws .empty-c .row { gap:6px; }
.ws .empty-c .sbtn { color:var(--face-ink);border-color:var(--face-ink);background:var(--face);font-size:13px;padding:0 8px;min-height:36px; }
.ws .empty-c .sbtn:hover { background:var(--face-2); }
.ws .ed-materials { display:flex;flex:1;flex-direction:column;min-height:0;height:100%;padding:0;border:0;gap:0; }
.ws .ed-material-scroll { flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;display:flex;flex-direction:column;gap:12px;padding-right:4px; }
.ws .ed-material-scroll>* { flex-shrink:0; }
.ws .ed-material-scroll h3 { min-height:28px; }
.ws .ed-model-note { margin:0;font-size:12px;line-height:1.4;color:var(--ink-2);white-space:nowrap; }
.ws .ed-materials label { display:grid;gap:5px;color:var(--ink-2);font-size:14px; }
.ws .ed-materials input,.ws .ed-materials select { width:100%;min-width:0;min-height:34px;padding:5px 8px;border:1px solid var(--rule-strong);border-radius:4px;background:var(--paper);color:var(--ink);font:14px var(--font);font-variant-numeric:tabular-nums; }
.ws .ed-values { display:grid;grid-template-columns:1fr 1fr;gap:8px; }
.ws .ed-pattern-options,.ws .ed-effect-options { display:grid;gap:10px; }
.ws .ed-swatches { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;max-height:224px;overflow-y:auto;scrollbar-width:thin; }
.ws .ed-swatches button { display:grid;place-items:center;min-height:48px;padding:2px;border:1px solid transparent;border-radius:4px;background:none;color:var(--ink);cursor:pointer; }
.ws .ed-swatches svg { width:100%;height:44px; }
.ws .ed-swatches [aria-pressed=true] { border-color:var(--copper);background:var(--paper-2); }
.ws .ed-swatches button:hover { border-color:var(--rule-strong); }
.ws .ed-dark summary,.ws .ed-material-detail summary { color:var(--ink-2);font-size:13px;cursor:pointer; }
.ws .ed-dark summary span { float:right;font-variant-numeric:tabular-nums; }
.ws .ed-colour-name { font-size:16px;color:var(--ink);min-height:22px; }
.ws .ed-material-detail p { overflow-wrap:anywhere;font-size:13px; }
.ws .ed-fill-footer { flex:none;padding-top:12px;margin-top:12px;border-top:1px solid var(--rule);background:var(--paper); }
.ws .ed-apply { width:100%;min-height:44px;color:var(--paper);background:var(--ink); }
.ws .ed-apply:hover:not(:disabled) { color:var(--paper);background:var(--copper); }
.ws [hidden] { display:none!important; }
.ws .lay:focus-visible,.ws .ed-mask:focus-visible,.ws button:focus-visible,.ws input:focus-visible,.ws select:focus-visible { outline:2px solid var(--copper);outline-offset:2px; }
'''
p.write_text(s,encoding='utf8')
