"""Read-only reproduction of the earlier optical calculation, plus V3 checks.

Does not run any of the original jobs or alter their cached/frozen results.
Only standard library, numpy and Pillow are imported.
"""
from __future__ import annotations
import ast
import json
import time
import numpy as np
import wave_model as W
from colour_tables import responses, XYZ_TO_SRGB


def original_functions():
    ns={'np':np,'E':W.E,'RUNS':(3,4,5,6,7,8,9,10,11,14),
        'FRAME':1488,'NF':497,'T_UM':.1333,
        'STARTS':[(0,True),(60,False),(-60,True),(30,False)]}
    ns['texture_bytes']=W.texture_bytes
    src=W.RESEARCH/'spectra.py'
    tree=ast.parse(src.read_text(encoding='utf-8'))
    funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in
           ('block_rows','stream','marks','class_index','spectrum')]
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(src),'exec'),ns)
    return ns


def cross_spectrum(ns,spec):
    nf,nrun,nfr=497,10,416
    acc=np.zeros((nrun,nrun,nf))
    for seed,(dsv,land) in enumerate(ns['STARTS']):
        lv=ns['stream'](spec,seed,dsv,land)
        st,ln=ns['marks'](lv)
        c2=2*st+ln
        cl=ns['class_index'](ln)
        comb=np.zeros((nfr,nrun,2976))
        np.add.at(comb,(c2//2976,cl,c2%2976),1.)
        fft=np.fft.rfft(comb,axis=-1)[...,:nf]
        acc+=np.einsum('nif,njf->ijf',fft,fft.conj(),optimize=True).real
    return (acc/(nfr*4*1488*.1333)).astype(np.float32)


def reproduce():
    ns=original_functions()
    z=np.load(W.RESEARCH/'spectra.npz')
    palette=z['palette'].tolist()
    freq=z['f']
    lengths=np.array(ns['RUNS'])*.1333
    amp=lengths[:,None]*np.sinc(freq[None,:]*lengths[:,None])
    fixed=W.E.SYNC
    old=(fixed[0],(fixed[1][0],fixed[1][1][:6]+(0x90440011,)+fixed[1][1][7:]))
    results=[]
    try:
        W.E.SYNC=old
        for name in ('92','A5','66','B9','8A92BDCB96'):
            t=time.perf_counter()
            actual=cross_spectrum(ns,name)
            ref=z['C'][palette.index(name)]
            error=float(np.max(np.abs(actual-ref))/np.max(np.abs(ref)))
            assert error<1e-6,(name,error)
            power=np.einsum('ijf,if,jf->f',actual,amp,amp,optimize=True)
            power[freq<.15]=0
            i=int(power.argmax())
            results.append({'texture':name,'old_sync_cross_spectrum_relative_max_error':error,
                            'peak_period_um':float(1/freq[i]),'peak_power':float(power[i]),
                            'seconds':time.perf_counter()-t})
            print('REPRODUCE',name,'relative_C_error',error,'period_um',1/freq[i],flush=True)
    finally:
        W.E.SYNC=fixed
    return results


def fft_identity():
    ns=original_functions()
    lv,_,_=W.recorded_block('92',0)
    lv=lv[:8192]
    f=np.fft.rfftfreq(len(lv),W.T_UM)
    ix=np.linspace(1,np.flatnonzero(f<2.8)[-1],80).astype(int)
    ft=f[ix]
    bit=np.fft.rfft(1.-lv)[ix]*W.T_UM*np.sinc(ft*W.T_UM)*np.exp(-1j*np.pi*ft*W.T_UM)
    st,ln=ns['marks'](lv)
    length=ln*W.T_UM
    centre=(st+ln/2)*W.T_UM
    direct=np.sum(length[:,None]*np.sinc(length[:,None]*ft[None,:])*
                  np.exp(-2j*np.pi*centre[:,None]*ft[None,:]),axis=0)
    error=float(np.max(np.abs(bit-direct))/np.max(np.abs(direct)))
    assert error<1e-10,error
    return {'continuous_rectangle_FFT_vs_run_sum_relative_error':error}


def two_d_check():
    ns=original_functions()
    class S:
        stream=staticmethod(ns['stream'])
    glob={'np':np,'S':S,'T_UM':.1333,'PITCH_UM':.745,'R_MM':40.,'SUB_Y':16,'TRACKS':96,'FRAMES':6}
    src=W.RESEARCH/'check_2d.py'
    funcs=[n for n in ast.parse(src.read_text(encoding='utf-8')).body
           if isinstance(n,ast.FunctionDef) and n.name in ('track_shift_bits','patch','far')]
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(src),'exec'),glob)
    z=np.load(W.RESEARCH/'spectra.npz')
    f=z['f']; df=f[1]-f[0]
    length=np.array(ns['RUNS'])*.1333
    along=length[:,None]*np.sinc(f[None,:]*length[:,None])*np.exp(-2*(np.pi*.005*f[None,:])**2)
    sigma=.003/.55/df
    grid=np.arange(-int(4*sigma+.5),int(4*sigma+.5)+1)
    kernel=np.exp(-.5*(grid/sigma)**2);kernel/=kernel.sum()
    out=[]
    for name,p in (('A5',.854),('66',1.065),('B9',1.420),('92',2.131)):
        power,fx,fy=glob['far'](name,7)
        band_y=(np.abs(fy)>.3)&(np.abs(fy)<1.)
        band_x=np.abs(np.abs(fx)-1/p)<.03/p
        numeric=float(power[np.ix_(band_y,band_x)].sum())
        cross=z['C'][z['palette'].tolist().index(name)].astype(float)
        vals=[]
        for fr in (0.,.6):
            a=along*np.sinc(fr*.35)
            q=np.einsum('ijf,if,jf->f',cross,a,a,optimize=True)
            q[0]=0
            pad=len(kernel)//2
            vals.append(np.convolve(np.pad(q,pad,mode='edge'),kernel,mode='valid'))
        analytic=float(np.mean(vals,axis=0)[np.abs(f-1/p)<.03/p].sum()*df)
        out.append({'texture':name,'numeric_2d_line':numeric,'analytic_line':analytic,'ratio':numeric/analytic})
        print('2D',name,'numeric/analytic',numeric/analytic,flush=True)
    ratios=np.array([r['ratio'] for r in out])
    return {'values':out,'relative_ratio_spread':float((ratios.max()-ratios.min())/ratios.mean()),
            'note':'Absolute normalization differs in the original check; compare relative texture ratios.'}


def validate_colours():
    _,_,white=responses(.5)
    xy=np.array(white['D65']['xy'])
    assert np.max(np.abs(xy-[.3127,.3290]))<.0003,xy
    assert abs(white['LED']['XYZ'][1]-1)<1e-10
    return {'illuminant_white_points':white,'D65_xy_reference':[.3127,.3290],
            'D65_xy_max_error':float(np.max(np.abs(xy-[.3127,.3290]))),
            'table_provenance':'Offline 5 nm standard transcription, not independently compared to the official electronic file.'}


def bench_new(op):
    out=[]
    for spec in ('92','A5','66','B9'):
        t=time.perf_counter()
        mass,record=W.texture_mass(spec)
        xyz=W.xyz_from_mass(mass,op)
        p=np.argmax(mass)
        out.append({**record,'wall_seconds':time.perf_counter()-t,'peak_period_um':float(1/W.F[p]),
                    'XYZ_at_delta_0_25':xyz[np.argmin(abs(W.DELTA-.25))].tolist(),
                    'XYZ_at_delta_0_5':xyz[np.argmin(abs(W.DELTA-.5))].tolist()})
        print('NEW MODEL',spec,'seconds',out[-1]['wall_seconds'],flush=True)
    return out


def main():
    started=time.perf_counter()
    result={'reproduction':reproduce(),'continuous_FFT_identity':fft_identity(),
            'two_dimensional_check':two_d_check(),'colour_table_checks':validate_colours(),
            'source_provenance':W.provenance()}
    W.atomic_json(W.OUT/'validation.json',result)
    op,meta=W.build_operator()
    result['operator']=meta
    result['new_model_reference_textures']=bench_new(op)
    # Higher quadrature for a sparse full-delta check, independent of cached H.
    ix=np.linspace(0,len(W.DELTA)-1,25).astype(int)
    hi,hm=W.build_operator(128,delta=W.DELTA[ix],save=False)
    checks=[]
    for spec in ('92','A5','66','B9'):
        mass,_=W.texture_mass(spec)
        lo=mass @ np.asarray(op[:,ix,:]).reshape(len(W.F),-1)
        high=mass @ hi.reshape(len(W.F),-1)
        err=float(np.max(np.abs(lo-high))/np.max(np.abs(high)))
        checks.append({'texture':spec,'64_vs_128_nodes_relative_max_XYZ_error':err})
        print('QUADRATURE',spec,err,flush=True)
    result['angular_quadrature_convergence']=checks
    result['total_seconds']=time.perf_counter()-started
    W.atomic_json(W.OUT/'validation.json',result)
    print('VALIDATION COMPLETE',result['total_seconds'],'s',flush=True)


if __name__=='__main__':
    main()
