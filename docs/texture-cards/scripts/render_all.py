"""V3 cards, checkpointed and offline. Python 3.13 + numpy + Pillow.

Session run: py -3.13 -B render_all.py --sheets 1
Continue:    py -3.13 -B render_all.py --sheets remaining --background
Estimate:    py -3.13 -B render_all.py --estimate

--workers defaults to 2, the maximum allowed. A parent performs colour matrix
products only after the worker pool has closed. Ctrl+C preserves each completed
block checkpoint. No process outside this directory is written or launched.
"""
from __future__ import annotations
import os
for _key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[_key]='2'
import sys
sys.dont_write_bytecode=True
import argparse
import atexit
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import numpy as np
from PIL import Image, ImageDraw
import make_cards as L
import wave_model as M
from colour_tables import XYZ_TO_SRGB

HERE=M.HERE
OUT=M.OUT
PAGE_W,PAGE_H=3508,4961
PLAIN='颜色由波动光学模型计算（LED 照明、CIE 1931 观察者），待实拍验证 / Colours from a wave-optics model (LED light, CIE 1931 observer), awaiting photos'
PALETTE_PATH=HERE.parent/'data'/'palette_merged.json'
MANIFEST_ROWS=[]
ANNOTATIONS=[]
_LOCK_HANDLE=None


def acquire_render_lock():
    """One renderer per output directory; OS releases the lock on any exit."""
    global _LOCK_HANDLE
    handle=(OUT/'render.lock').open('a+b')
    handle.seek(0,2)
    if handle.tell()==0:
        handle.write(b'0');handle.flush()
    handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('Another renderer is already active in v3; no extra workers started')
    _LOCK_HANDLE=handle
    atexit.register(handle.close)


def worker(spec):
    return M.texture_mass(spec)


def selected_sheets(data):
    two=L.paginate_groups(L.two_groups(data['two_line']))
    return {
        '1':{'name':'sheet_1_singles','zh':'单线 · 260 条','en':'Singles / all spectral orders / human observer',
             'rows':sorted(data['singles'],key=lambda r:(r['periods_um'][0],r['spec']))},
        '2a':{'name':'sheet_2a_two_line','zh':'双线 · 2a','en':'Two-line / all orders / ratio and target-share groups',
              'groups':two[:3],'rows':[r for col in two[:3] for _,rs in col for r in rs]},
        '2b':{'name':'sheet_2b_two_line','zh':'双线 · 2b','en':'Two-line / all orders / ratio and target-share groups',
              'groups':two[3:],'rows':[r for col in two[3:] for _,rs in col for r in rs]},
        '3':{'name':'sheet_3_three_line','zh':'三线 · 28 条 + 图例','en':'Three-line / all orders / optical and colour key',
             'rows':sorted(data['three_line'],key=lambda r:(r['periods_um'][0],r['spec']))},
    }


def estimate(workers=2):
    p=OUT/'validation.json'
    value=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
    timings=[x['seconds'] for x in value.get('new_model_reference_textures',[])]
    seconds=float(np.median(timings)) if timings else 4.
    # Shared two-process memory traffic and different specs merit a generous
    # 1.25--1.9 overhead range, plus integration/page/QA preparation.
    result={'benchmarked_seconds_per_texture_serial':seconds,'workers':workers,
            'sheet_1_minutes_range':[(260*seconds/workers*1.25+70)/60,(260*seconds/workers*1.9+150)/60],
            'all_637_minutes_range':[(637*seconds/workers*1.25+150)/60,(637*seconds/workers*1.9+300)/60],
            'remaining_377_minutes_range':[(377*seconds/workers*1.25+100)/60,(377*seconds/workers*1.9+200)/60],
            'scope':'8 whole ECC blocks per texture, two lamps, full-page PNG+lossless PDF; excludes manual QA',
            'warning':'Estimate, not a completed render; resume reuses completed block checkpoints.'}
    ref=OUT/'timing_reference.json'
    if ref.exists():
        reference=json.loads(ref.read_text(encoding='utf-8'))
        per=reference['encode_wall_seconds']/reference['targets']*2/workers
        for key,n in (('sheet_1',260),('all_637',637),('remaining_377',377)):
            result[key+'_minutes_range']=[n*per/60+1.5,n*per/60*1.5+4.]
        result['reference_measured_seconds_per_texture_two_workers']=per*workers/2
    return result


def prepare(rows,workers):
    t=time.perf_counter()
    masses={}
    records=[]
    pool=ProcessPoolExecutor(max_workers=workers)
    try:
        jobs={pool.submit(worker,r['spec']):r for r in rows}
        for done,future in enumerate(as_completed(jobs),1):
            row=jobs[future]
            mass,rec=future.result()
            masses[row['id']]=mass
            records.append(rec)
            if done%10==0 or done==len(rows):
                print(f'CHECKPOINT {done}/{len(rows)} wall={time.perf_counter()-t:.1f}s',flush=True)
                M.atomic_json(OUT/'progress.json',{'completed_targets':done,'requested_targets':len(rows),
                              'elapsed_seconds':time.perf_counter()-t,'last_id':row['id'],
                              'updated_utc':datetime.now(timezone.utc).isoformat()})
    except BaseException:
        for job in jobs:
            job.cancel()
        pool.shutdown(wait=True,cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)
    return masses,records,time.perf_counter()-t


def integrate(rows,masses,op):
    matrix=np.array([masses[r['id']] for r in rows])
    xyz=M.xyz_from_mass(matrix,op)
    order2=np.empty_like(matrix)
    for i,r in enumerate(rows):
        band=np.zeros(len(M.F),bool)
        for p in r['periods_um']:
            band |= abs(M.F-2/p)<=.05*(2/p)
        order2[i]=matrix[i]*band
    xyz2=M.xyz_from_mass(order2,op)
    return xyz,xyz2


def output_name(sheet,lamp):
    return sheet['name']+'_'+lamp.lower()


def page_base(key,sheet,lamp,count,exposure):
    L.ACTIVE_SHEET=f'{key}_{lamp}'
    im=Image.new('RGB',(PAGE_W,PAGE_H),L.BG)
    d=ImageDraw.Draw(im)
    x=L.text(d,(142,150),'disc-probe ',66)
    x=L.text(d,(x,150),'纹理色卡',66,'zh')
    L.text(d,(x+16,150),'/ Texture colour card',66)
    L.text(d,(142,258),f'V3 / {sheet["zh"]}',46,'zh',L.ACCENT)
    L.text(d,(3366,270),f'2026-11-11 | {count} textures | {lamp}',30,'mono',anchor='rt')
    L.text(d,(142,330),sheet['en'],38)
    L.text(d,(142,408),PLAIN,27,'zh')
    if lamp=='D65':
        L.text(d,(142,449),'本页改用 D65，非 LED；模型与计算方法相同。 / This alternate page uses D65 instead of LED.',25,'zh',L.ACCENT)
    d.line((142,490,3366,490),fill=L.RULE,width=2)
    lamp_description='LED: Gaussians 450/12 + 0.75×560/55 nm' if lamp=='LED' else 'D65'
    L.text(d,(142,513),f'{lamp_description} | CIE 1931 2° | 380–780 nm | W=0.35 µm, ΔL=0, edge σ=0.03 µm | 8 ECC blocks | exposure={exposure:.5g}',27,'zh',L.MUTED)
    L.text(d,(142,557),'ID = observation_#### | P: µm | q: legacy purity (not a gain) | 1/P: lines/mm | upper strip: ALL orders',25,'mono',L.MUTED)
    return im,d


def rgb_strip(rgb,width,height):
    xs=np.linspace(0,len(M.DELTA)-1,width)
    values=np.stack([np.interp(xs,np.arange(len(M.DELTA)),rgb[:,k]) for k in range(3)],-1)
    return Image.fromarray(np.repeat(np.rint(values).astype(np.uint8)[None],height,axis=0))


def xyz_strip(xyz,width,height,exposure):
    # Resample in XYZ before sRGB encoding/quantization, not in gamma RGB.
    xs=np.linspace(0,len(M.DELTA)-1,width)
    values=np.stack([np.interp(xs,np.arange(len(M.DELTA)),xyz[:,k]) for k in range(3)],-1)
    encoded=M.srgb(values,exposure)
    return Image.fromarray(np.repeat(encoded[None],height,axis=0))


def annotate_lane(d,row,line,x,y,width,height):
    """Separate dark explanatory lane: never overwrite any modelled colour.

    Labels refer to the NOMINAL first order, not absence of higher orders.
    Tiny intervals use a connector and the adjacent unused area of this lane.
    """
    p=row['periods_um'][line]
    intervals=[('UV',.1,min(.95,.380/p)),('IR',max(.1,.780/p),.95)]
    occupied=[]
    for zone,lo,hi in intervals:
        if hi<=lo:
            continue
        start=x+(lo-.1)/.85*(width-1)
        end=x+(hi-.1)/.85*(width-1)
        prefix=zone+(str(line+1)+':' if len(row['periods_um'])>1 else ' ')
        label=f'{prefix}{round(lo*p*1000)}–{round(hi*p*1000)} nm'
        tw=d.textlength(label,font=L.font('note',21))
        inside=tw+8<=end-start
        tx=(start+end-tw)/2 if inside else x+5 if zone=='UV' else x+width-tw-5
        box=d.textbbox((tx,y),label,font=L.font('note',21),anchor='lt')
        assert box[0]>=x and box[2]<=x+width and box[3]<=y+height
        for prev in occupied:
            assert box[0]>=prev[2] or box[2]<=prev[0],(label,prev)
        occupied.append(box)
        L.text(d,(tx,y),label,21,'note',L.MUTED,limit=x+width)
        if not inside:
            target=(start+end)/2
            d.line((target,y+height-2,tx+tw/2,y+height-2),fill=L.RULE)
            d.line((target,y+height-5,target,y+height-2),fill=L.MUTED)
        ANNOTATIONS.append({'id':row['id'],'line':line+1,'zone':zone,'label':label,
                            'inside_interval':inside,'delta_range':[lo,hi],
                            'meaning':'nominal first-order wavelength; upper strip still includes every order'})


def draw_row(im,d,row,xyz,xyz2,x,y,width,height,label_width,key,column,exposure):
    n=len(row['periods_um'])
    bx=x+label_width
    bw=width-label_width
    primary_height=15 if n==1 else 13 if n==2 else 14
    im.paste(xyz_strip(xyz,bw,primary_height,exposure),(bx,y+1))
    for li in range(n):
        ly=y+primary_height+2+22*li
        d.rectangle((bx,ly,bx+bw-1,ly+20),fill=L.INK)
        annotate_lane(d,row,li,bx,ly,bw,21)
    im.paste(xyz_strip(xyz2,bw,3,exposure),(bx,y+height-5))
    ident=row['id'].rsplit('_',1)[-1]
    ps='/'.join(f'{p:.3f}' for p in row['periods_um'])
    qs='?' if row['purity'] is None else '/'.join(f'{q:.3f}'.lstrip('0') for q in row['purity'])
    spec=row['spec'][:8]+('…' if len(row['spec'])>8 else '')+('*' if row.get('period_conflict') else '')
    freq='/'.join(str(round(1000/p)) for p in row['periods_um'])
    if n==1:
        L.text(d,(x,y+1),f'{ident} {ps} {qs}',25,'mono',limit=bx-12)
        L.text(d,(x,y+23),f'{spec} {freq}',25,'mono',limit=bx-12)
    elif n==2:
        L.text(d,(x,y+1),f'{ident} {ps}',25,'mono',limit=bx-12)
        L.text(d,(x,y+21),f'{qs} {spec}',25,'mono',limit=bx-12)
        L.text(d,(x,y+41),freq,25,'mono',L.MUTED,limit=bx-12)
    else:
        L.text(d,(x,y+3),f'{ident} {ps}',30,'mono',limit=bx-12)
        L.text(d,(x,y+31),f'{qs} {spec}',30,'mono',limit=bx-12)
        L.text(d,(x,y+61),f'1/P = {freq} /mm',25,'mono',L.MUTED,limit=bx-12)
    d.line((x,y+height-1,x+width-1,y+height-1),fill=L.RULE)
    MANIFEST_ROWS.append({'id':row['id'],'spec':row['spec'],'sheet':key,'column':column,
                          'periods_um':row['periods_um'],'purity':row['purity'],
                          'bbox':[x,y,x+width,y+height],
                          'strip_bbox':[bx,y+1,bx+bw,y+1+primary_height],
                          'second_order_bbox':[bx,y+height-5,bx+bw,y+height-2],
                          'spatial_frequency_per_mm':[1000/p for p in row['periods_um']]})


def footer(d,key,lamp):
    L.text(d,(142,4700),'δ 为沿轨道的方向差，不是角度。上色带含全部可见谱；暗标注带仅解释名义一阶 UV / IR（380 / 780 nm）。',27,'zh',L.MUTED)
    L.text(d,(142,4743),'细彩轨 = 2/P 附近 ±5% 频带的计算颜色与强度；q 不再乘作增益。所有行共用一个曝光；无逐行归一化。',27,'zh',L.MUTED)
    L.text(d,(142,4786),'灯：5 cm / 1 m；瞳孔：4 mm / 30 cm。标记尺寸、染料反差与灯谱仍是假设；不保证实拍或印刷吻合。',27,'zh',L.MUTED)
    L.text(d,(3366,4817),f'V3 {key} / {lamp} / A3 300 dpi sRGB / print at 100%',25,'mono',anchor='rt')


def compose(key,sheet,lamp,xyz,xyz2,exposure,validate_only=False):
    L.TEXT_BOXES.clear()
    MANIFEST_ROWS.clear()
    ANNOTATIONS.clear()
    rows=sheet['rows']
    index={r['id']:i for i,r in enumerate(rows)}
    im,d=page_base(key,sheet,lamp,len(rows),exposure)
    if key=='3':
        cw=3224; lw=1020
        L.text(d,(142,608),'ID / P × 3 / q × 3 / spec / 1/P',25,'mono',L.MUTED)
        L.axis(d,142+lw,3365,666,True)
        for ri,row in enumerate(rows):
            draw_row(im,d,row,xyz[ri],xyz2[ri],142,670+ri*85,cw,85,lw,key,1,exposure)
        L.axis(d,142+lw,3365,670+28*85+6,False)
        legend=[
            '模型：实际 EFMPlus 通道位；每纹理 8 个真实 ECC 块，4 组编码初态；随机邻域的 PI / PO 真实计算。',
            '矩形标记 W=0.35 µm、长度偏移 0、边缘 σ=0.03 µm；这些尺寸未测量。邻轨按功率相加。',
            'LED：450 nm 蓝峰（σ=12）+ 0.75 × 560 nm 荧光峰（σ=55）；不是一盏已测量的实灯。',
            '观察者：CIE 1931 2°（离线 5 nm 表）；积分 380–780 nm；XYZ 转 D65 sRGB，不做相机白平衡。',
            '有限灯面与瞳孔按均匀圆孔积分；中央 δr=0，采用对称入射／观察几何 θ=asin(δ/2)。',
            '上色带包含谱中全部阶次与连续背景；下面的 UV / IR 文本只是各目标周期的一阶位置。',
            '薄彩轨从实算功率谱提取 2/P ±5% 频带，同一曝光；偶次谱缺失时它自然很暗。',
            '一个固定曝光覆盖全页；负 sRGB 分量裁剪。人眼可见的部分颜色超出 sRGB 和纸张色域。',
            '旧照片检验未通过；B9、低 NA 明暗与染料色散仍未解决。数值复现不等于实物验证。',
            '完整模型、哈希、采样误差、数值收敛和运行记录见 REPORT.md 与 v3/validation.json。',
        ]
        for i,line in enumerate(legend):
            L.text(d,(142,3290+i*88),line,29,'zh',L.FG)
    else:
        cw=(3224-120)//3
        lw=310 if key=='1' else 330
        for ci in range(3):
            x=142+ci*(cw+60)
            L.text(d,(x,594),'ID   P      q' if key=='1' else 'ID / P long-short',25,'mono',L.MUTED)
            L.text(d,(x,628),'spec   1/P (/mm)' if key=='1' else 'q / spec / 1/P',25,'mono',L.MUTED)
            L.axis(d,x+lw,x+cw-1,666,True)
            y=670
            if key=='1':
                group=[('',rows[ci*87:(ci+1)*87])]
            else:
                group=sheet['groups'][ci]
            for label,members in group:
                if label:
                    L.text(d,(x,y+3),label,25,'mono',L.ACCENT)
                    y+=34
                for row in members:
                    ri=index[row['id']]
                    height=44 if key=='1' else 62
                    draw_row(im,d,row,xyz[ri],xyz2[ri],x,y,cw,height,lw,key,ci+1,exposure)
                    y+=height
            assert y<=4570,(key,y)
            L.axis(d,x+lw,x+cw-1,4576,False)
    footer(d,key,lamp)
    assert Counter(r['id'] for r in MANIFEST_ROWS)==Counter(r['id'] for r in rows)
    collisions=[]
    boxes=L.TEXT_BOXES
    for i,a in enumerate(boxes):
        for b in boxes[i+1:]:
            aa,bb=a['bbox'],b['bbox']
            if aa[0]<bb[2] and aa[2]>bb[0] and aa[1]<bb[3] and aa[3]>bb[1]:
                collisions.append([a['text'],b['text']])
    assert not collisions,collisions[:5]
    if validate_only:
        return {'rows':len(MANIFEST_ROWS),'text_boxes':len(boxes),'text_overlap_count':0}
    name=output_name(sheet,lamp)
    im.save(OUT/(name+'.png'),dpi=(300,300),icc_profile=L.ICC)
    (OUT/(name+'.pdf')).write_bytes(L.pdf_bytes([im]))
    pdf_check=L.verify_pdf(OUT/(name+'.pdf'),[im])
    (OUT/'qa').mkdir(exist_ok=True)
    # L's reviewed image helpers now write only inside v3/.
    prior=L.HERE
    L.HERE=OUT
    try:
        im.resize((877,1240),Image.Resampling.LANCZOS).save(OUT/'qa'/(name+'_overview.png'))
        L.qa_crops(name,im,MANIFEST_ROWS)
        im.crop((142,140,3366,585)).save(OUT/'qa'/(name+'_title.png'))
    finally:
        L.HERE=prior
    manifest={'version':3,'sheet':key,'lamp':lamp,'rows':MANIFEST_ROWS.copy(),
              'annotations':ANNOTATIONS.copy(),'count':len(rows),'every_selected_target_once':True,
              'annotation_minimum_pt':5.04,'label_minimum_pt':6.,'text_overlap_count':0,
              'exposure':exposure,'PDF':pdf_check,'model_signature':M.signature()[0],
              'renderer_sha256':M.sha(HERE/'render_all.py'),
              'font_sha256':{k:M.sha(p) for k,p in L.FONT_LOG.items()},
              'PNG_sha256':M.sha(OUT/(name+'.png')),'PDF_sha256':M.sha(OUT/(name+'.pdf')),
              'text_boxes':boxes.copy()}
    M.atomic_json(OUT/(name+'_manifest.json'),manifest)
    return manifest


def compare_v2(sheet,xyz,exposure):
    old=json.loads((HERE/'manifest.json').read_text(encoding='utf-8'))
    old_im=Image.open(HERE/'sheet_1_singles.png')
    rows=sheet['rows']
    candidates=[0,1,40,80,120,160,200,259]
    im=Image.new('RGB',(2200,850),L.BG)
    d=ImageDraw.Draw(im)
    # This is an inspectable comparison crop at original label size.
    prior=L.ACTIVE_SHEET
    L.ACTIVE_SHEET='comparison'
    L.text(d,(142,130),'V2 / rough first order',30)
    L.text(d,(1200,130),'V3 / wave optics / LED',30)
    for j,i in enumerate(candidates):
        r=rows[i]
        src=next(q for q in old['row_manifest'] if q['id']==r['id'])
        x0,y0,x1,y1=src['strip_bbox']
        old_bar=old_im.crop((x0,y0,x1,y0+min(20,y1-y0)))
        old_bar=old_bar.resize((800,35),Image.Resampling.NEAREST)
        yy=210+j*70
        L.text(d,(142,yy),f'{r["periods_um"][0]:.3f}',25,'mono')
        L.text(d,(1200,yy),f'{r["periods_um"][0]:.3f}',25,'mono')
        im.paste(old_bar,(280,yy))
        im.paste(xyz_strip(xyz[i],800,35,exposure),(1340,yy))
    L.ACTIVE_SHEET=prior
    im.save(OUT/'before_after_v2_v3.png',icc_profile=L.ICC)


def write_status(status):
    path=OUT/'run_status.json'
    old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'pages':{}}
    old['pages'].update(status['pages'])
    old.update({k:v for k,v in status.items() if k!='pages'})
    M.atomic_json(path,old)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sheets',default='all',help='1, 2a, 2b, 3, remaining, all, or comma-separated IDs')
    ap.add_argument('--lamps',default='LED,D65')
    ap.add_argument('--workers',type=int,choices=(1,2),default=2)
    ap.add_argument('--background',action='store_true')
    ap.add_argument('--estimate',action='store_true')
    ap.add_argument('--layout-check',action='store_true',help='Check all text/layout bounds without generating any cards')
    args=ap.parse_args()
    if not (args.estimate or args.layout_check or args.background):
        acquire_render_lock()
    est=estimate(args.workers)
    M.atomic_json(OUT/'time_estimate.json',est)
    if args.estimate:
        print(json.dumps(est,indent=2));return
    if args.layout_check:
        sheets=selected_sheets(json.loads(PALETTE_PATH.read_text(encoding='utf-8')))
        for key,sheet in sheets.items():
            dummy=np.zeros((len(sheet['rows']),len(M.DELTA),3))
            print('LAYOUT',key,compose(key,sheet,'LED',dummy,dummy,1.,validate_only=True),flush=True)
        return
    if args.background:
        log=(OUT/'render.log').open('ab',buffering=0)
        command=[sys.executable,'-B',str(HERE/'render_all.py'),'--sheets',args.sheets,
                 '--lamps',args.lamps,'--workers',str(args.workers)]
        flags=0x08000000|0x00000008 if os.name=='nt' else 0
        proc=subprocess.Popen(command,cwd=str(HERE),stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                              creationflags=flags,start_new_session=os.name!='nt')
        M.atomic_json(OUT/'background.json',{'pid':proc.pid,'command':command,'log':'build/render.log'})
        print('Started background renderer PID',proc.pid,'log: build/render.log');return
    validation=OUT/'validation.json'
    if not validation.exists() or 'angular_quadrature_convergence' not in json.loads(validation.read_text(encoding='utf-8')):
        raise RuntimeError('Run verify_v3.py before a complete render')
    if json.loads(validation.read_text(encoding='utf-8'))['source_provenance']['signature']!=M.signature()[0]:
        raise RuntimeError('The validation belongs to a different model or source revision')
    data=json.loads(PALETTE_PATH.read_text(encoding='utf-8'))
    sheets=selected_sheets(data)
    all_ids=[r['id'] for s in sheets.values() for r in s['rows']]
    assert len(all_ids)==len(set(all_ids))==637
    keys=['1','2a','2b','3'] if args.sheets=='all' else ['2a','2b','3'] if args.sheets=='remaining' else args.sheets.split(',')
    assert all(k in sheets for k in keys)
    if est['all_637_minutes_range'][1]>360 and keys!=['1']:
        print('Estimated full job exceeds 6 hours; rendering sheet 1 only.',flush=True)
        keys=['1']
    lamps=args.lamps.split(',')
    assert set(lamps)<=set(('LED','D65'))
    requested=[r for k in keys for r in sheets[k]['rows']]
    start=time.perf_counter()
    masses,records,encode_seconds=prepare(requested,args.workers)
    op,op_meta=M.build_operator()
    page_status={}
    for key in keys:
        sheet=sheets[key]
        t=time.perf_counter()
        xyz,xyz2=integrate(sheet['rows'],masses,op)
        temp=OUT/(sheet['name']+'_XYZ.tmp')
        with temp.open('wb') as f:
            np.savez_compressed(f,XYZ=xyz,XYZ_order2=xyz2,delta=M.DELTA,
                                ids=np.array([r['id'] for r in sheet['rows']]),signature=M.signature()[0])
        temp.replace(OUT/(sheet['name']+'_XYZ.npz'))
        for lamp in lamps:
            li=('LED','D65').index(lamp)
            linear=xyz[:,:,li,:] @ XYZ_TO_SRGB.T
            exposure=.98/np.max(linear)
            manifest=compose(key,sheet,lamp,xyz[:,:,li,:],xyz2[:,:,li,:],exposure)
            manifest_info={'count':len(sheet['rows']),'exposure':exposure,
                           'negative_channel_fraction_before_gamut_clip':float(np.mean(linear<0)),
                           'peak_linear_channel_after_exposure':float(np.max(linear)*exposure),
                           'PNG':output_name(sheet,lamp)+'.png','PDF':output_name(sheet,lamp)+'.pdf',
                           'model_signature':manifest['model_signature'],'render_seconds_including_other_lamp':time.perf_counter()-t}
            page_status[key+'_'+lamp]=manifest_info
            print('PAGE',key,lamp,'count',len(sheet['rows']),'exposure',exposure,flush=True)
            # The v2 sheet and manifest are not published; skip the before/after crop without them.
            if key=='1' and lamp=='LED' and (HERE/'manifest.json').exists() and (HERE/'sheet_1_singles.png').exists():
                compare_v2(sheet,xyz[:,:,li,:],exposure)
        write_status({'pages':page_status,'last_requested_sheets':keys,
                      'elapsed_wall_seconds':time.perf_counter()-start,'encode_wall_seconds':encode_seconds,
                      'per_texture_sampling':records,'estimate':est,'model':M.provenance(),
                      'operator':op_meta,'palette_sha256':M.sha(PALETTE_PATH),
                      'completed_utc':datetime.now(timezone.utc).isoformat()})
    for lamp in lamps:
        paths=[OUT/(output_name(sheets[k],lamp)+'.png') for k in sheets]
        manifests=[OUT/(output_name(sheets[k],lamp)+'_manifest.json') for k in sheets]
        same_model=all(p.exists() and json.loads(p.read_text(encoding='utf-8'))['model_signature']==M.signature()[0] for p in manifests)
        if all(p.exists() for p in paths) and same_model:
            merged=[r['id'] for p in manifests for r in json.loads(p.read_text(encoding='utf-8'))['rows']]
            assert len(merged)==len(set(merged))==637
            ims=[Image.open(p).convert('RGB') for p in paths]
            pdf=OUT/('texture_cards_all_'+lamp.lower()+'.pdf')
            pdf.write_bytes(L.pdf_bytes(ims))
            L.verify_pdf(pdf,ims)
    try:
        from update_v3_report import update   # our internal report writer; not published
        update()
    except ModuleNotFoundError:
        pass
    except Exception as exc:
        print('Cards completed; report update needs attention:',repr(exc),flush=True)
    print('COMPLETE',keys,'wall_seconds',time.perf_counter()-start,flush=True)


if __name__=='__main__':
    main()
