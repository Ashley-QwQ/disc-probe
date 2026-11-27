"""Independent full-image renders vs the reusable uniform-patch colour API."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest

import numpy as np

from discprobe import simulate

ROOT = Path(__file__).resolve().parents[1]


def test_texture_colour_smoke():
    """For the existing selftest's zero-argument runner; full checks use unittest/pytest."""
    rgb = simulate.texture_colour('A5',.3)
    assert isinstance(rgb,tuple) and len(rgb)==3 and all(type(v) is int and 0<=v<=255 for v in rgb)


class TextureColourTests(unittest.TestCase):
    def test_real_uniform_patch_renders_for_36_textures_at_three_poses(self):
        palette=json.loads((ROOT/'discprobe/template_palette.json').read_text(encoding='utf-8'))
        multi=[row['spec'] for row in palette['swatches'].values() if row['kind']=='single']
        single=['00','10','33','55','57','63','64','66','7F','80','87','92','A5','AA','B1','B9','CC','E4','FD','FF']
        specs=single+multi
        self.assertEqual(len(set(specs)),36)
        poses=[(simulate.CAMERA,simulate.FLASH),((0,135,540),(-43.66,154.79,540)),
               ((100,100,200),(60,120,240))]
        design=np.broadcast_to(np.array(False),(6000,6000))
        patch=[164,95,168,99]
        size=200
        comparisons=[]
        for spec in specs:
            for camera,flash in poses:
                with self.subTest(spec=spec,camera=camera):
                    # REAL render(): its normal 2000-square fine grid, all 40000 output pixels.
                    image=np.asarray(simulate.render(design,size,dark=spec,light=spec,camera=camera,flash=flash))
                    x0,y0,x1,y1=patch
                    expected=image[y0:y1,x0:x1].mean((0,1))
                    delta=float(simulate.along_track((x0+x1)/2*120/size-60,60-(y0+y1)/2*120/size,camera,flash))
                    actual=simulate.texture_colour(spec,delta,pose=dict(camera=camera,flash=flash,size=size,patch=patch))
                    np.testing.assert_allclose(actual,expected,atol=1,rtol=0)
                    comparisons.append(dict(spec=spec,camera=list(camera),flash=list(flash),size=size,patch=patch,
                                            delta=delta,render_mean=expected.tolist(),texture_colour=list(actual),
                                            max_error=float(np.max(np.abs(np.asarray(actual)-expected)))))
        if os.environ.get('DISCPROBE_COLOUR_EVIDENCE'):
            target=Path(os.environ['DISCPROBE_COLOUR_EVIDENCE']).resolve()
            if not target.is_relative_to((ROOT/'evidence').resolve()):
                raise ValueError('colour test evidence must stay in the workspace evidence directory')
            target.write_text(json.dumps(dict(textures=len(specs),poses=len(poses),
                comparisons=len(comparisons),max_error=max(row['max_error'] for row in comparisons),
                cases=comparisons),indent=2)+'\n',encoding='utf-8')

    def test_original_release_render_is_byte_identical(self):
        source=subprocess.run(['git','show','v0.1.2.1:discprobe/simulate.py'],cwd=ROOT,check=True,capture_output=True).stdout
        module=types.ModuleType('release_simulate'); module.__file__=simulate.__file__
        exec(compile(source,simulate.__file__,'exec'),module.__dict__)
        design=np.zeros((6000,6000),bool);design[800:2700,3200:5000]=True
        expected=module.render(design,320,rotate=17)
        actual=simulate.render(design,320,rotate=17)
        self.assertEqual(actual.tobytes(),expected.tobytes())
        a,b=io.BytesIO(),io.BytesIO(); actual.save(a,'PNG'); expected.save(b,'PNG')
        self.assertEqual(a.getvalue(),b.getvalue())

    def test_local_field_uses_linear_average_and_release_response(self):
        # Independent formula using original LUT; do not call the shared private helpers.
        delta=np.array([.275,.30,.325]); radial=np.array([.60,.65,.70])
        with np.load(Path(simulate.__file__).with_name('simulate_lut.npz')) as z:
            row=(z['single'][0x92]/255.)**2-.02
            linear=(row[np.rint(delta/.005).astype(int)]+.15*z['groove'][np.rint(radial/.005).astype(int)]+.05*.177)*4
        rgb=linear.mean(0)
        grey=rgb @ np.array([.2126,.7152,.0722])
        rgb=np.clip(grey+.6*(rgb-grey),0,1)
        expected=np.uint8(np.clip(255*np.where(rgb<=.0031308,12.92*rgb,1.055*rgb**(1/2.4)-.055),0,255))
        self.assertEqual(simulate.texture_colour('92',delta,pose={'radial_delta':radial}),tuple(expected))
        self.assertEqual(simulate.texture_colour('92',1.7,pose={'radial_delta':1.8}),
                         simulate.texture_colour('92',1.3,pose={'radial_delta':1.3}))
        # At a low viewing height the physical tangent difference exceeds the LUT range.
        # Follow the release renderer's existing clamp instead of extrapolating a spectrum.
        camera,flash=(0,500,10),(0,450,10)
        patch=[164,95,168,99];size=200
        centre=simulate.along_track(39.6,1.8,camera,flash)
        self.assertGreater(centre,1.3)
        image=np.asarray(simulate.render(np.broadcast_to(np.array(False),(6000,6000)),size,
                                        dark='92',light='92',camera=camera,flash=flash))
        actual=simulate.texture_colour('92',float(centre),pose=dict(camera=camera,flash=flash,size=size,patch=patch))
        np.testing.assert_allclose(actual,image[95:99,164:168].mean((0,1)),atol=1,rtol=0)

    def test_grey_recipes_and_bands_use_the_same_model(self):
        data=json.loads((ROOT/'discprobe/template_palette.json').read_text(encoding='utf-8'))
        design=np.broadcast_to(np.array(False),(6000,6000))
        for row in (s for s in data['swatches'].values() if s['kind']=='grey-recipe'):
            spec=row['computed']['descriptor']; p=row['computed']['pose']
            image=np.asarray(simulate.render(design,p['size'],dark=spec,light=spec))
            x0,y0,x1,y1=p['patch']; expected=image[y0:y1,x0:x1].mean((0,1))
            np.testing.assert_allclose(row['srgb'],expected,atol=1,rtol=0)
        bright=next(row for row in data['swatches'].values() if row.get('recipe',{}).get('bright_fraction')==1)
        p=bright['computed']['pose'];x0,y0,x1,y1=p['patch']
        image=np.asarray(simulate.render(design,p['size'],light='bands'))
        np.testing.assert_allclose(bright['srgb'],image[y0:y1,x0:x1].mean((0,1)),atol=1,rtol=0)

    def test_recording_spectrum_reproduces_release_single_byte_table(self):
        from discprobe.simulate_spectrum import texture_table
        with np.load(Path(simulate.__file__).with_name('simulate_lut.npz')) as z:
            for spec in ('A5','92','B9'):
                np.testing.assert_array_equal(texture_table(spec),z['single'][int(spec,16)])

    def test_unsupported_and_inconsistent_inputs_do_not_invent_colours(self):
        for spec,delta,options in [('A5',float('nan'),{}),('A5',-.1,{}),('A5',2.01,{}),('A5',[],{}),
                                   ([1.2],.3,{}),('',.3,{}),('QZ',.3,{}),('A5',.3,{'media':'cd'}),
                                   ('A5',.9,{'pose':{'camera':simulate.CAMERA,'patch':[164,95,168,99],'size':200}}),
                                   ('A5',.3,{'pose':{'radial_delta':float('inf')}}),
                                   ({'components':[{'spec':'A5','weight':.2}]},.3,{})]:
            with self.subTest(spec=spec),self.assertRaises(ValueError):
                simulate.texture_colour(spec,delta,**options)


if __name__=='__main__':
    unittest.main()
