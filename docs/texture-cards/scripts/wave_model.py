"""V3 scalar wave-optics model; offline numpy only, resumable per texture.

No camera, fitted spectral multiplier, rough colour map, or palette purity gain.
Uses real EFMPlus encoder and real ECC construction, read-only from the project.
"""
from __future__ import annotations
import os
for _name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[_name] = '2'
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import hashlib
import ast
import json
import time
import numpy as np
from colour_tables import responses, observer, illuminant, XYZ_TO_SRGB

HERE = Path(__file__).resolve().parent
ROOT = Path('D:/disc-probe')
RESEARCH = ROOT / 'docs/goals/colour-sim'
OUT = HERE / 'v3'
CACHE = OUT / 'checkpoints'
for p in (OUT,CACHE):
    p.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools'))
from discprobe import efmplus as E, dvd
import dsv_block as DB

T_UM = .13333
WIDTH_UM = .35
EDGE_SIGMA_UM = .03
LENGTH_OFFSET_UM = 0.
DF = .0005
F = np.arange(0,2.8+DF/2,DF)
DELTA = np.linspace(.10,.95,1025)
STARTS = [(1,0,True),(2,60,False),(3,-60,True),(4,30,False)]
SAMPLES = 8
LAMP_RADIUS = .05 / (2*1.)
PUPIL_RADIUS = .004 / (2*.30)
VERSION = 'wave-v3-real-row-phase-ecc-random-context-20261112b'
SOURCE_PATHS = [ROOT/'discprobe/efmplus.py',ROOT/'discprobe/efmplus_tables.py',
                ROOT/'discprobe/dvd.py',ROOT/'tools/dsv_block.py',
                ROOT/'discprobe/imagedisc.py',
                RESEARCH/'report.md',RESEARCH/'prereg.md',RESEARCH/'spectra.py',
                RESEARCH/'spectra_iso.py',RESEARCH/'check_2d.py',
                RESEARCH/'model.py',RESEARCH/'common.py',
                HERE/'colour_tables.py',HERE/'wave_model.py']


def load_texture_bytes():
    """Use DP's actual recorded-row phasing, not sector-continuous repetition."""
    path=ROOT/'discprobe/imagedisc.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    nodes=[]
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_COL' for t in node.targets):
            nodes.append(node)
        elif isinstance(node,ast.FunctionDef) and node.name=='texture_bytes':
            nodes.append(node)
    assert len(nodes)==2
    ns={'np':np,'dvd':dvd}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)
    return ns['texture_bytes']


texture_bytes=load_texture_bytes()


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path).resolve()
    assert path.is_relative_to(HERE)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(path)


def signature():
    d={'version':VERSION,'T_um':T_UM,'W_um':WIDTH_UM,'edge_sigma_um':EDGE_SIGMA_UM,
       'dl_um':LENGTH_OFFSET_UM,'samples':SAMPLES,'df':DF,'starts':STARTS,
       'source_hashes':{p.as_posix():sha(p) for p in SOURCE_PATHS}}
    return hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest(), d


def recorded_block(spec, seed, solid=False):
    """Real ID/IED/EDC/scrambling/PI/PO, with selected texture and random context.

    Eight consecutive sectors are the selected texture, the other eight are
    seeded random user payload; parity is calculated from all sixteen sectors.
    The selected interval includes each sector's real interleaved PO row.
    """
    rng=np.random.default_rng(20261111+seed)
    lba=64000+16*seed
    payload=rng.integers(0,256,32768,dtype=np.uint8)
    first=0 if solid else int(rng.integers(0,9))
    count=16 if solid else 8
    q=texture_bytes(spec,np.array([lba]))[0]
    for s in range(first,first+count):
        payload[s*2048:(s+1)*2048]=dvd.recorded(q,lba+s)
    rows=DB.recording_rows(payload,lba)
    state,dsv,land=STARTS[seed%4]
    lv,end=E.encode_rows(rows,E.Boundary(state,dsv,land),0)
    assert rows.shape==(208,182) and len(lv)==619008
    lo,hi=first*26*1488,(first+count)*26*1488
    return lv, (lo,hi), {'seed':seed,'lba':lba,'first_sector':first,'sectors':count,
                          'start':[state,dsv,land],'end':[end.state,end.dsv,end.land],
                          'rows_sha256':hashlib.sha256(rows.tobytes()).hexdigest(),
                          'channel_sha256':hashlib.sha256(lv.tobytes()).hexdigest()}


def rebin_power(lv,t_um=T_UM,width_um=WIDTH_UM,edge_um=EDGE_SIGMA_UM):
    """Exact rectangular-run Fourier amplitude, positive-order power per length.

    For the nominal equal-width, zero-offset marks, the channel-cell FFT times
    T sinc(fT) is algebraically the continuous sum over complete rectangular
    runs; this is not an FFT point-mark approximation. The sector interval is a
    rectangular aperture; angular integration suppresses its edge sidelobes.
    """
    n=len(lv)
    mask=1.-lv.astype(np.float64)
    fft=np.fft.rfft(mask)
    freq=np.fft.rfftfreq(n,t_um)
    keep=freq<=F[-1]+DF/2
    freq=freq[keep]
    amp=width_um*t_um*np.sinc(freq*t_um)*np.exp(-2*(np.pi*edge_um*freq)**2)
    power=(fft[keep].real**2+fft[keep].imag**2)*amp**2/(n*t_um)
    power[0]=0.
    # Cache bin-integrated power, preserving line area during coarsening.
    native_df=1/(n*t_um)
    bins=np.floor(freq/DF+.5).astype(np.int64)
    mass=np.bincount(bins,weights=power*native_df,minlength=len(F))[:len(F)]
    return mass


def texture_mass(spec, progress=None):
    key=hashlib.sha256(spec.encode()).hexdigest()[:24]
    path=CACHE/f'{key}.npz'
    sig,_=signature()
    masses=[]
    records=[]
    elapsed=0.
    if path.exists():
        with np.load(path,allow_pickle=False) as z:
            if str(z['signature'])!=sig or str(z['spec'])!=spec:
                raise RuntimeError(f'Checkpoint has a different model: {path.name}')
            masses=list(z['samples'])
            records=json.loads(str(z['records_json']))
            elapsed=float(z['seconds'])
    for seed in range(len(masses),SAMPLES):
        t=time.perf_counter()
        lv,(lo,hi),rec=recorded_block(spec,seed)
        m=rebin_power(lv[lo:hi])
        masses.append(m)
        records.append(rec)
        elapsed+=time.perf_counter()-t
        tmp=path.with_suffix('.tmp')
        with tmp.open('wb') as f:
            np.savez_compressed(f,signature=sig,spec=spec,samples=np.array(masses),
                                records_json=json.dumps(records),seconds=elapsed)
        tmp.replace(path)
        if progress:
            progress(seed+1,elapsed)
    return np.mean(masses,axis=0), {'spec':spec,'samples':len(masses),'seconds':elapsed,
                                   'checkpoint':path.relative_to(HERE).as_posix(),
                                   'power_sample_CV':float(np.std(np.sum(masses,axis=1))/np.mean(np.sum(masses,axis=1)))}


def angular_quadrature(n=64):
    """Uniform circular lamp and pupil, including radial width to fourth order.

    K(x) is the convolution of two semicircular x marginals. Conditional radial
    second/fourth moments give sinc^2(W delta_r/lambda) to <1e-8 truncation error
    at the stated apertures. Both along-track projections scale by cos(theta),
    theta=asin(delta/2), a stated symmetric incidence/observation geometry.
    """
    a,b=LAMP_RADIUS,PUPIL_RADIUS
    radius=a+b
    x=np.linspace(-radius,radius,8193)
    dx=x[1]-x[0]
    def disk(r):
        q=np.maximum(r*r-x*x,0)
        p=2*np.sqrt(q)/(np.pi*r*r)
        p/=np.sum(p)*dx
        return p,p*q/3,p*q*q/5
    aa,bb=disk(a),disk(b)
    nfft=32768
    def conv(p,q):
        return np.fft.irfft(np.fft.rfft(p,nfft)*np.fft.rfft(q,nfft),nfft)[:2*len(x)-1]*dx
    xx=np.arange(2*len(x)-1)*dx-2*radius
    k=conv(aa[0],bb[0])
    m2=conv(aa[1],bb[0])+conv(aa[0],bb[1])
    m4=conv(aa[2],bb[0])+6*conv(aa[1],bb[1])+conv(aa[0],bb[2])
    u,w=np.polynomial.legendre.leggauss(n)
    u*=radius
    w*=radius
    kd=np.maximum(np.interp(u,xx,k),0)
    weights=w*kd
    weights/=weights.sum()
    mu2=np.maximum(np.interp(u,xx,m2),0)/np.maximum(kd,1e-30)
    mu4=np.maximum(np.interp(u,xx,m4),0)/np.maximum(kd,1e-30)
    return u,weights,mu2,mu4


def build_operator(n=64,delta=DELTA,save=True):
    """Exact change of integration variable lambda -> spatial frequency.

    H(delta,f)=1000 * integral K(u) E(lambda) CMF(lambda) lambda/f du,
    lambda=(delta+cos(theta)*u)/f in um. Multiplication by bin-integrated
    measured power then integrates every spectral line/order, without assigning
    a target period or sampling narrow lines on a coarse wavelength grid.
    Scalar Fraunhofer lambda^-2 and Kirchhoff cos(theta)^2 are explicit factors.
    """
    sig,_=signature()
    op_path=OUT/f'operator_{n}.npy'
    meta_path=OUT/f'operator_{n}.json'
    if save and op_path.exists() and meta_path.exists():
        meta=json.loads(meta_path.read_text(encoding='utf-8'))
        if meta.get('signature')==sig and meta.get('delta')==delta.tolist():
            return np.load(op_path,mmap_mode='r'),meta
    t=time.perf_counter()
    u,weights,m2,m4=angular_quadrature(n)
    _,_,whites=responses(.5)
    nm_ref=np.arange(380,780.01,.5)
    cmf_ref=observer(nm_ref)
    norm={lamp:1/np.trapezoid(illuminant(nm_ref,lamp)*cmf_ref[:,1],nm_ref) for lamp in ('LED','D65')}
    shape=(len(F),len(delta),6)
    if save:
        tmp=op_path.with_suffix('.tmp.npy')
        op=np.lib.format.open_memmap(tmp,mode='w+',dtype=np.float64,shape=shape)
    else:
        op=np.empty(shape,np.float64)
    safe_f=np.maximum(F,.0001)
    for lo in range(0,len(delta),8):
        dt=delta[lo:lo+8]
        cosine=np.sqrt(1-(dt/2)**2)
        lam=(dt[:,None,None]+cosine[:,None,None]*u[None,None,:])/safe_f[None,:,None]
        nm=lam*1000
        visible=(nm>=380)&(nm<=780)
        cmf=observer(np.clip(nm,380,780))
        # Variable transform Jacobian, reference-wavelength Fraunhofer factor,
        # scalar reflection obliquity, and finite radial aperture.
        radial=1-(np.pi*WIDTH_UM/lam)**2*m2[None,None,:]/3 + 2*(np.pi*WIDTH_UM/lam)**4*m4[None,None,:]/45
        factor=1000*lam/safe_f[None,:,None]*(.55/lam)**2
        factor*=cosine[:,None,None]**2*radial*weights[None,None,:]*visible
        channels=[]
        for lamp in ('LED','D65'):
            spd=illuminant(nm,lamp)*norm[lamp]
            channels.append(np.einsum('dfq,dfqk->dfk',factor*spd,cmf,optimize=True))
        block=np.concatenate(channels,axis=-1)
        block[:,0,:]=0
        op[:,lo:lo+len(dt),:]=np.moveaxis(block,0,1)
    meta={'signature':sig,'quadrature_nodes':n,'delta':delta.tolist(),'seconds':time.perf_counter()-t,
          'shape':list(shape),'illuminant_whites':whites,'lamp_radius_rad':LAMP_RADIUS,
          'pupil_radius_rad':PUPIL_RADIUS,'angular_sigma_normal':float(np.sqrt((LAMP_RADIUS**2+PUPIL_RADIUS**2)/4)),
          'geometry':'symmetric theta_i=theta_o=asin(delta/2), central delta_r=0',
          'observer_table':'offline 5 nm CIE 1931 2-degree transcription, linear interpolation',
          'exposure':'not part of operator; one scalar per complete sheet and illuminant',
          'chromatic_adaptation':'none; direct XYZ to D65 sRGB, no per-channel white balance'}
    if save:
        op.flush()
        del op
        tmp.replace(op_path)
        atomic_json(meta_path,meta)
        op=np.load(op_path,mmap_mode='r')
    return op,meta


def xyz_from_mass(mass,op):
    a=np.asarray(mass)
    result=a @ op.reshape(len(F),-1)
    return result.reshape(a.shape[:-1]+(len(DELTA),2,3))


def srgb(xyz,exposure):
    rgb=np.asarray(xyz) @ XYZ_TO_SRGB.T * exposure
    rgb=np.clip(rgb,0,1)
    enc=np.where(rgb<=.0031308,12.92*rgb,1.055*rgb**(1/2.4)-.055)
    return np.rint(np.clip(enc,0,1)*255).astype(np.uint8)


def provenance():
    sig,d=signature()
    d.update({'signature':sig,'context':'8 contiguous texture sectors + 8 random-fill sectors; all real ECC parity',
              'power':'coherent across the selected full 8-sector interval; independent blocks/tracks averaged in power',
              'mark_model':'uniform rectangular W=.35 um, length LT+dl, dl=0; Gaussian edge sigma=.03 um',
              'amplitude_correction':'T*sinc(fT)*W*exp(-2*pi^2*sigma_e^2*f^2)',
              'unknowns':['actual mark dimensions and write strategy','complex dye/land contrast versus wavelength',
                          'polarization and multilayer vector diffraction','actual lamp SPD','actual neighbouring image content'],
              'no_camera_or_purity_scaling':True,'spectral_range_nm':[380,780]})
    return d
