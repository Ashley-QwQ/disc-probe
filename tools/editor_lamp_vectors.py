"""Live reference vectors: simulate.along_track + first-order editor display policy."""
import json
from pathlib import Path
import numpy as np
from discprobe import simulate


def main():
    root = Path(__file__).resolve().parents[1]
    palette = json.loads((root/'discprobe/web/home/design/swatches.json').read_text(encoding='utf8'))
    lut = palette['preview_lut']
    materials = [dict(id='A5', spec='A5', period_um=lut['reference_period_um']),
                 next(dict(m, period_um=m['periods_um'][0]) for m in palette['swatches'].values()
                      if 1.5 < m['periods_um'][0] < 1.7),
                 dict(id='background', spec='B9')]
    vectors = []
    for camera, flash in [(simulate.CAMERA, simulate.FLASH), ((35., 105., 310.), (-8., 124., 310.))]:
        size = 81
        c = (np.arange(size)+.5)*120/size-60
        x, y = np.meshgrid(c, -c)
        dt = simulate.along_track(x, y, camera, flash)
        cx, cy = simulate.unit(camera, x, y)
        lx, ly = simulate.unit(flash, x, y)
        dr = np.abs((cx+lx)*x+(cy+ly)*y)/np.maximum(np.hypot(x,y),1e-9)
        for j, i in [(40, 40), (12, 40), (40, 68), (68, 40), (40, 12), (20, 60), (60, 20), (20, 20), (60, 60)]:
            for material in materials:
                period = material.get('period_um', 0)
                wavelength = period*dt[j,i]*1000
                linear = np.full(3, .05*.177*4)
                if period and 400 <= wavelength <= 700:
                    exact = lut['single'].get(material['spec'])
                    curve = np.array(exact if exact is not None else lut['single']['A5']).reshape(-1,3)
                    it = int(np.clip(np.rint((dt[j,i] if exact is not None else dt[j,i]*period/lut['reference_period_um'])/.005),0,260))
                    ir = int(np.clip(np.rint(dr[j,i]/.005),0,260))
                    linear = (curve[it]+.15*np.array(lut['groove']).reshape(-1,3)[ir]+.05*.177)*4
                grey = linear@np.array([.2126,.7152,.0722])
                linear = np.clip(grey+simulate.PHOTO_SATURATION*(linear-grey),0,1)
                encoded = np.where(linear<=.0031308,12.92*linear,1.055*linear**(1/2.4)-.055)
                vectors.append(dict(size=size, pose=dict(camera=camera,flash=flash), i=i,j=j,
                                    material=material,dt=float(dt[j,i]),dr=float(dr[j,i]),
                                    rgb=np.uint8(np.clip(encoded*255,0,255)).tolist()))
    print(json.dumps(vectors))


if __name__ == '__main__':
    main()
