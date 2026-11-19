"""Independent numerical/physical checks and declared parameter sensitivity.

Run after the rendering worker pool has ended (one CPU process here).
No fitting to photographs. Sensitivity ranges are scenarios, not confidence bounds.
"""
from __future__ import annotations
import json
import time
import numpy as np
import wave_model as M
from colour_tables import observer, illuminant


def grating():
    # A rectangular 50%-duty grating has |c_n|^2 = sin^2(pi*n/2)/(pi*n)^2.
    t=.125
    lv=np.tile(np.r_[np.zeros(8,np.uint8),np.ones(8,np.uint8)],10000)
    mass=M.rebin_power(lv,t_um=t,edge_um=0)
    records=[]
    for n in (1,2,3,4,5):
        f=n/2.
        actual=float(mass[abs(M.F-f)<M.DF*.75].sum())
        expected=M.WIDTH_UM**2*(np.sin(np.pi*n/2)/(np.pi*n))**2
        assert abs(actual-expected)<1e-10,(n,actual,expected)
        records.append({'order':n,'computed_line_area':actual,'analytic_line_area':expected})
    return records


def flat_power(op):
    # If P(f)=1, angular averaging must leave its value at one, apart from the
    # explicitly included radial envelope and the cos(theta)^2 obliquity.
    xyz=(np.full(len(M.F),M.DF) @ op.reshape(len(M.F),-1)).reshape(len(M.DELTA),2,3)
    nm=np.arange(380,780.001,.1)
    lam=nm/1000
    cmf=observer(nm)
    mu2=(M.LAMP_RADIUS**2+M.PUPIL_RADIUS**2)/4
    # Disk moments: E[y^4]=r^4/8; independent symmetric disks add 6 E[a²]E[b²].
    mu4=(M.LAMP_RADIUS**4+M.PUPIL_RADIUS**4)/8+6*M.LAMP_RADIUS**2*M.PUPIL_RADIUS**2/16
    radial=1-(np.pi*M.WIDTH_UM/lam)**2*mu2/3+2*(np.pi*M.WIDTH_UM/lam)**4*mu4/45
    out=[]
    for li,lamp in enumerate(('LED','D65')):
        spd=illuminant(nm,lamp)
        norm=1/np.trapezoid(spd*cmf[:,1],nm)
        base=np.trapezoid(norm*spd[:,None]*cmf*(.55/lam[:,None])**2*radial[:,None],nm,axis=0)
        expected=(1-(M.DELTA/2)**2)[:,None]*base
        error=float(np.max(abs(xyz[:,li]-expected))/np.max(expected))
        assert error<.002,(lamp,error)
        out.append({'lamp':lamp,'flat_P_operator_vs_direct_wavelength_integral_relative_max_error':error})
    return out


def rectangle_variant_mass(lv,dl=0.,edge=.03,width_scale=None):
    """Boundary-comb identity permits exact common length offsets without NUFFT."""
    lv=np.asarray(lv)
    n=len(lv);t=M.T_UM
    diff=np.diff(lv.astype(np.int8))
    st=np.flatnonzero(diff==-1)+1
    en=np.flatnonzero(diff==1)+1
    if lv[0]==0: st=np.r_[0,st]
    if lv[-1]==0: en=np.r_[en,n]
    length=en-st
    weights=np.ones(len(st))
    if width_scale:
        for run,w in width_scale.items():
            weights[length==run]=w
    weighted=np.zeros(n)
    delta=np.zeros(n+1)
    np.add.at(delta,st,weights);np.add.at(delta,en,-weights)
    weighted=np.cumsum(delta[:-1])
    boundary=np.zeros(n)
    np.add.at(boundary,st%n,weights*.5)
    np.add.at(boundary,en%n,weights*.5)
    f=np.fft.rfftfreq(n,t)
    keep=f<=M.F[-1]+M.DF/2
    f=f[keep]
    a0=np.fft.rfft(weighted)[keep]*t*np.sinc(f*t)*np.exp(-1j*np.pi*f*t)
    b=np.fft.rfft(boundary)[keep]
    a=a0*np.cos(np.pi*f*dl)+b*dl*np.sinc(f*dl)
    a*=M.WIDTH_UM*np.exp(-2*(np.pi*edge*f)**2)
    power=abs(a)**2/(n*t)
    power[0]=0
    return np.bincount(np.floor(f/M.DF+.5).astype(int),weights=power/(n*t),minlength=len(M.F))[:len(M.F)]


def uncertainty(op):
    configs={'nominal':{},'dl_minus_30nm':{'dl':-.03},'dl_plus_30nm':{'dl':.03},
             'edge_5nm':{'edge':.005},'edge_60nm':{'edge':.060},
             'D4_effective_run_widths':{'width_scale':{3:.64,4:.81,5:.55}}}
    result=[]
    for spec in ('92','A5','66','B9'):
        masses={k:[] for k in configs}
        for seed in (0,1):
            lv,(lo,hi),_=M.recorded_block(spec,seed)
            lv=lv[lo:hi]
            nominal=M.rebin_power(lv)
            for name,params in configs.items():
                value=rectangle_variant_mass(lv,**params)
                if name=='nominal':
                    assert np.allclose(value,nominal,rtol=1e-8,atol=1e-12)
                masses[name].append(value)
        base=M.xyz_from_mass(np.mean(masses['nominal'],axis=0),op)[:,0,:]
        base_xy=base[:,:2]/np.maximum(base.sum(-1,keepdims=True),1e-30)
        use=base[:,1]>.01*base[:,1].max()
        for name in configs:
            xyz=M.xyz_from_mass(np.mean(masses[name],axis=0),op)[:,0,:]
            xy=xyz[:,:2]/np.maximum(xyz.sum(-1,keepdims=True),1e-30)
            delta=np.linalg.norm(xy-base_xy,axis=-1)
            result.append({'texture':spec,'scenario':name,'samples':2,
                           'xy_distance_median_on_visible_cells':float(np.median(delta[use])),
                           'xy_distance_max_on_visible_cells':float(np.max(delta[use])),
                           'integrated_Y_ratio_to_nominal':float(xyz[:,1].sum()/base[:,1].sum())})
    return {'scenario_results':result,'width_025_045_relative_intensity_factors':[float((.25/.35)**2),float((.45/.35)**2)],
            'interpretation':'Sensitivity scenarios, not confidence intervals or fitted physical dimensions. D4 run weights were fitted effective strengths, not measured widths.'}


def sampling(op):
    result=[]
    for spec in ('92','A5','66','B9'):
        key=M.CACHE/(M.hashlib.sha256(spec.encode()).hexdigest()[:24]+'.npz')
        with np.load(key) as z: mass=z['samples']
        a=M.xyz_from_mass(np.mean(mass[::2],axis=0),op)[:,0,:]
        b=M.xyz_from_mass(np.mean(mass[1::2],axis=0),op)[:,0,:]
        relative=float(np.max(abs(a-b))/np.max((a+b)/2))
        use=(a[:,1]+b[:,1])>.02*np.max((a[:,1]+b[:,1]))
        xya=a[:,:2]/np.maximum(a.sum(-1,keepdims=True),1e-30)
        xyb=b[:,:2]/np.maximum(b.sum(-1,keepdims=True),1e-30)
        result.append({'texture':spec,'even_vs_odd_blocks_relative_max_XYZ_difference':relative,
                       'median_xy_distance_on_visible_cells':float(np.median(np.linalg.norm(xya-xyb,axis=-1)[use]))})
    return result


def checkpoint_resume():
    prior=M.CACHE
    temp=M.OUT/'resume_test'
    temp.mkdir(exist_ok=True)
    spec='A5'
    key=M.hashlib.sha256(spec.encode()).hexdigest()[:24]+'.npz'
    with np.load(prior/key) as z:
        payload={k:z[k] for k in z.files}
    expected=payload['samples'].mean(0)
    records=json.loads(str(payload['records_json']))
    payload['samples']=payload['samples'][:6]
    payload['records_json']=json.dumps(records[:6])
    payload['seconds']=float(payload['seconds'])*.75
    with (temp/key).open('wb') as f: np.savez_compressed(f,**payload)
    M.CACHE=temp
    try:
        actual,rec=M.texture_mass(spec)
    finally:
        M.CACHE=prior
    assert np.array_equal(expected,actual)
    return {'started_from_samples':6,'finished_samples':rec['samples'],'byte_exact_mean_power_match':True}


def frequency_and_aperture_convergence(op):
    old_f,old_df=M.F,M.DF
    ix=np.linspace(0,len(M.DELTA)-1,25).astype(int)
    low_op=np.array(op[:,ix,:])
    streams={}
    low={}
    aperture=[]
    for spec in ('92','A5','66','B9'):
        lv,(lo,hi),_=M.recorded_block(spec,0)
        lv=lv[lo:hi]
        streams[spec]=lv
        whole=M.rebin_power(lv)
        split=(M.rebin_power(lv[:len(lv)//2])+M.rebin_power(lv[len(lv)//2:]))/2
        low[spec]=whole @ low_op.reshape(len(old_f),-1)
        other=split @ low_op.reshape(len(old_f),-1)
        aperture.append({'texture':spec,'8_sector_coherent_vs_two_4_sector_powers_relative_max_XYZ_error':
                         float(np.max(abs(low[spec]-other))/np.max(abs(low[spec])))})
    try:
        M.DF=old_df/2
        M.F=np.arange(0,2.8+M.DF/2,M.DF)
        fine_op,_=M.build_operator(64,delta=M.DELTA[ix],save=False)
        fine=[]
        for spec,lv in streams.items():
            mass=M.rebin_power(lv)
            value=mass @ fine_op.reshape(len(M.F),-1)
            error=float(np.max(abs(value-low[spec]))/np.max(abs(value)))
            fine.append({'texture':spec,'df_0005_vs_00025_relative_max_XYZ_error':error})
    finally:
        M.F,M.DF=old_f,old_df
    return {'spatial_frequency_bins':fine,'coherent_window_length':aperture}


def main():
    started=time.perf_counter()
    op,_=M.build_operator()
    result={'analytic_rectangular_grating':grating(),'flat_spectrum_change_of_variables':flat_power(op),
            'parameter_sensitivity':uncertainty(op),'Monte_Carlo_sampling':sampling(op),
            'checkpoint_resume':checkpoint_resume(),
            'frequency_and_aperture_convergence':frequency_and_aperture_convergence(op),
            'model_signature':M.signature()[0]}
    result['seconds']=time.perf_counter()-started
    M.atomic_json(M.OUT/'physics_checks.json',result)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
