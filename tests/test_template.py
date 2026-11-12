"""Template geometry, material exchange, and real HTTP/CLI equivalence; no drives."""
import hashlib
import http.client
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from PIL import Image

from discprobe import template, webui

NS = {'s': 'http://www.w3.org/2000/svg'}
ROOT = Path(__file__).resolve().parents[1]


def test_template_exchange_smoke():
    """Also callable by DP's existing zero-argument selftest file runner."""
    files = template.swatch_files()
    mapping = json.loads(files['swatches.json'])['swatches']
    assert template.read_ase(files['swatches.ase']) == {name:row['srgb'] for name,row in mapping.items()}


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='template 测试 ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.save('geo.json', {'fit': {'u': 24.2/.0001333, 'v': .000744/.0001333,
                                                 'bit_nm_assumed': 133.3, 'media': 'dvd'},
                                           'setup': {'last_lba': 2_000_000-1}})

    def save(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    def test_svg_radii_independently_match_geo_and_written_sector_boundary(self):
        files = template.export_files(self.path, sectors=1_800_000, size=256)
        svg = ET.fromstring(files['template.svg'])
        self.assertEqual(svg.attrib['viewBox'], '-80 -80 160 160')
        self.assertEqual(svg.attrib['width'], '160mm')
        expected_end = math.sqrt(24.2**2 + .000744 * 1_800_000 * 38688*.0001333/math.pi)
        expected = {'disc-outer-edge':[60], 'centre-hole':[7.5], 'clamping-ring':[17],
                    'writable-start':[24.2], 'written-end':[expected_end],
                    'safe-margin':[24.7, expected_end-.5]}
        for layer, radii in expected.items():
            group = svg.find(f's:g[@id="{layer}"]', NS)
            self.assertIsNotNone(group)
            self.assertIn('/', group.find('s:title', NS).text)
            actual = [float(c.attrib['r']) for c in group.findall('s:circle', NS)]
            np.testing.assert_allclose(actual, radii, atol=.01, rtol=0)
        self.assertIsNone(svg.find('s:g[@id="approximate-pose-dark-zones"]', NS))

    def test_png_and_svg_agree_at_actual_radial_boundaries(self):
        files = template.export_files(self.path, size=4096)
        svg = ET.fromstring(files['template.svg'])
        png = np.asarray(Image.open(io.BytesIO(files['template.png'])))
        # On the upper vertical radius there is no ruler/label. Inspect pixels at each
        # independently parsed circle position, and clear space half a mm either side.
        # Vertical slices near the axis avoid hatch strokes at the chosen circle centres.
        for ident in ('clamping-ring', 'writable-start', 'written-end', 'safe-margin'):
            for circle in svg.findall(f's:g[@id="{ident}"]/s:circle', NS):
                r = float(circle.attrib['r'])
                y = round((80-r)/160*4096)
                block = png[y-4:y+5, 2046:2051]
                self.assertGreater(block[...,3].max(), 200, ident)
                # Verify a dark outline lies within 2 pixels of the predicted location.
                hits = (block[...,:3].min(axis=-1)<150) & (block[...,3]>180)
                self.assertTrue(hits[2:7].any(), ident)
        self.assertEqual(png.shape, (4096,4096,4))
        self.assertEqual(int(png[0,0,3]),0)
        self.assertEqual(int(png[2048,2048,3]),0)
        self.assertTrue(np.any(png[...,3]==0))

    def test_all_info_text_is_outside_disc_in_both_formats(self):
        files = template.export_files(self.path, size=2048, pose='default')
        svg = ET.fromstring(files['template.svg'])
        info = svg.find('s:g[@id="info"]', NS)
        self.assertNotIn('clip-path',info.attrib)
        png = np.asarray(Image.open(io.BytesIO(files['template.png'])))
        for text in info.findall('s:text',NS):
            x,y = float(text.attrib['x']),float(text.attrib['y'])
            size = float(text.attrib['font-size'])
            # Actual font bounds, including glyph ascent, must clear the entire disc.
            box = template._font(round(size*100)).getbbox(text.text,anchor='ls')
            left,top,right,bottom = x+box[0]/100,y+box[1]/100,x+box[2]/100,y+box[3]/100
            near_x = max(left,0,-right)
            near_y = max(top,0,-bottom)
            self.assertGreater(math.hypot(near_x,near_y),60,text.text)
            x0,x1 = max(0,int((left+80)*12.8)-2),min(2048,math.ceil((right+80)*12.8)+2)
            y0,y1 = max(0,int((top+80)*12.8)-2),min(2048,math.ceil((bottom+80)*12.8)+2)
            self.assertGreater(png[y0:y1,x0:x1,3].max(),0,text.text)
        for group in svg.findall('s:g',NS):
            if group.attrib['id'] not in ('info','radius-ruler'):
                self.assertEqual(group.findall('s:text',NS),[])
        ruler = svg.find('s:g[@id="radius-ruler"]',NS)
        self.assertTrue(all(abs(float(line.attrib[k])) <= .7
                            for line in ruler.findall('s:line',NS) for k in ('y1','y2')))
        meta = json.loads(svg.find('s:metadata',NS).text)
        self.assertEqual(meta['canvas']['disc_crop_px'],[256,256,1792,1792])
        dpi = Image.open(io.BytesIO(files['template.png'])).info['dpi'][0]
        self.assertAlmostEqual(dpi,2048/160*25.4,places=2)

    def test_pose_layer_is_opposite_quiet_and_off_in_svg_and_png(self):
        plain = template.export_files(self.path,size=512)
        posed = template.export_files(self.path,size=512,pose='default')
        svg = ET.fromstring(posed['template.svg'])
        layer = svg.find(f's:g[@id="{template.DARK_LAYER}"]',NS)
        self.assertEqual(layer.attrib['display'],'none')
        self.assertLessEqual(float(layer.attrib['opacity']),.25)
        self.assertIn('dark-at-pose (approximate, off)',layer.find('s:title',NS).text)
        lines = layer.findall('s:line',NS)
        self.assertTrue(lines)
        from discprobe import simulate
        periods = [row['periods_um'][0] for row in template.palette()['swatches'].values() if row['kind']=='single']
        for line in lines:
            x1,y1,x2,y2 = (float(line.attrib[k]) for k in ('x1','y1','x2','y2'))
            self.assertAlmostEqual(x2-x1,y2-y1,places=6)
            delta=simulate.along_track((x1+x2)/2,-(y1+y2)/2,simulate.CAMERA,simulate.FLASH)
            self.assertFalse(any(400 <= 1000*period*delta <= 700 for period in periods))
        a = np.asarray(Image.open(io.BytesIO(plain['template.png'])))
        b = np.asarray(Image.open(io.BytesIO(posed['template.png'])))
        np.testing.assert_array_equal(a[64:448,64:448],b[64:448,64:448])
        hidden = next(row for row in template.scene(template.geometry(self.path),template.parse_pose('default'))
                      if row[0] == template.DARK_LAYER)
        im = np.asarray(Image.open(io.BytesIO(template.png_bytes([hidden],512))))
        self.assertEqual(im[...,3].max(),0)

    def test_hatching_is_45_degrees_in_non_writable_annuli(self):
        g = template.geometry(self.path)
        svg = ET.fromstring(template.svg_bytes(template.scene(g), {}))
        hatch = svg.find('s:g[@id="non-writable-hatching"]', NS)
        self.assertIsNone(hatch.find('s:rect',NS))
        for line in hatch.findall('s:line',NS):
            x1,y1,x2,y2 = (float(line.attrib[k]) for k in ('x1','y1','x2','y2'))
            self.assertAlmostEqual(x2-x1, -(y2-y1), places=6)
            radius = math.hypot((x1+x2)/2,(y1+y2)/2)
            self.assertTrue(7.5 <= radius <= g['start_mm']+.0001 or g['end_mm']-.0001 <= radius <=60)

    def test_swatches_round_trip_json_gpl_and_ase(self):
        files = template.swatch_files()
        data = json.loads(files['swatches.json'])
        entries = data['swatches']
        self.assertEqual(len(entries),21)
        parsed = {}
        for line in files['swatches.gpl'].decode().splitlines():
            if '\t' in line:
                rgb, name = line.split('\t')
                parsed[name] = [int(v) for v in rgb.split()]
        self.assertEqual(parsed, {name:row['srgb'] for name,row in entries.items()})
        self.assertEqual(template.read_ase(files['swatches.ase']), parsed)
        singles = [s for s in entries.values() if s['kind']=='single']
        self.assertEqual(len({s['hex'] for s in singles}),16)
        from discprobe import simulate
        self.assertEqual(data['model']['name'],simulate.TEXTURE_COLOUR_MODEL)
        self.assertEqual(data['model']['version'],simulate.TEXTURE_COLOUR_VERSION)
        self.assertEqual(data['model']['lut_sha256'],hashlib.sha256(Path(simulate.__file__).with_name('simulate_lut.npz').read_bytes()).hexdigest())
        for entry in singles:
            self.assertEqual(len(bytes.fromhex(entry['spec']))*2,len(entry['spec']))
            self.assertEqual(len(entry['periods_um']),1)
            self.assertFalse(entry['period_conflict'])
            rgb = list(simulate.texture_colour(entry['spec'],entry['computed']['delta'],pose=entry['computed']['pose']))
            self.assertEqual(rgb,entry['srgb'])
        grey = [s for s in entries.values() if s['kind']=='grey-recipe']
        self.assertEqual([s['recipe']['bright_fraction'] for s in grey],[0,.25,.5,.75,1])
        for entry in grey:
            self.assertEqual(list(simulate.texture_colour(entry['computed']['descriptor'],entry['computed']['delta'],
                                                         pose=entry['computed']['pose'])),entry['srgb'])
        self.assertIn('not photo validated',data['comment'])
        self.assertEqual(template.swatch_files(),files)

    def test_ase_rejects_truncated_or_extra_bytes(self):
        raw = template.swatch_files()['swatches.ase']
        for damaged in (raw[:7], raw[:-1], raw+b'0', b'wrong'+raw[5:]):
            with self.assertRaises(ValueError):
                template.read_ase(damaged)

    def test_preset_pitch_integral_not_linear_radius(self):
        preset = self.save('preset.json', {'innerRadiusMm':24, 'outerRadiusMm':58,
                                         'totalSectors':2_000_000, 'pitchLinear':.5,
                                         'pitchQuadratic':-.1, 'pitchCubic':.04})
        g = template.geometry(preset, sectors=1_000_000)
        r = np.linspace(24,58,500001)
        x = (r-24)/34
        density = r/(1+.5*x-.1*x*x+.04*x*x*x)
        area = np.r_[0,np.cumsum((density[1:]+density[:-1])*.5*np.diff(r))]
        expected = float(np.interp(.5,area/area[-1],r))
        self.assertAlmostEqual(g['end_mm'],expected,places=6)
        self.assertGreater(abs(g['end_mm']-41),1)
        self.assertEqual(template.geometry(preset)['end_mm'],58)

    def test_cd_and_bd_geometry_use_their_sector_lengths(self):
        from discprobe import cd, bdexport
        cdgeo=self.save('cd.json', {'fit':{'u':25/(cd.BIT_NM*1e-6),'v':.0015/(cd.BIT_NM*1e-6),
                                             'bit_nm_assumed':cd.BIT_NM,'media':'cd'},'setup':{'last_lba':300000-1}})
        got=template.geometry(cdgeo,media='cd')
        self.assertAlmostEqual(got['end_mm'],math.sqrt(25**2+.0015*300000*16/math.pi),places=8)
        bdgeo=self.save('bd.json',{'fit':{'model':'clv','media':'bd','r0_mm':24.02,'pitch_um':.3185},
                                     'setup':{'last_lba':12_000_000-1}})
        got=template.geometry(bdgeo)
        self.assertAlmostEqual(got['end_mm'],bdexport.outer_radius_mm(24.02,.3185,12000000),places=8)
        with self.assertRaisesRegex(ValueError,'DVD'):
            template.export_files(bdgeo,size=256,pose='default')

    def test_multiple_presets_need_explicit_id(self):
        presets = [{'id':key,'innerRadiusMm':24,'outerRadiusMm':58,'totalSectors':2000000} for key in ('one','two')]
        path=self.save('presets.json',{'dvdPresets':presets})
        with self.assertRaisesRegex(ValueError,'select one'):
            template.geometry(path)
        self.assertEqual(template.geometry(path,preset_id='two')['end_mm'],58)

    def test_bad_inputs_fail_before_any_output(self):
        for options in ({'sectors':0},{'sectors':2000001},{'sectors':True},{'sectors':10},
                        {'size':8193},{'size':True},{'media':'cd'}, {'pose':'0,0,0,1,2,3'},
                        {'pose':'NaN,0,330,1,2,330'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                template.export_files(self.path,**options)
        for bad in (float('nan'),float('inf'),-1):
            path=self.save('bad.json',{'fit':{'u':bad,'v':5,'bit_nm_assumed':133.3}})
            with self.assertRaises(ValueError):
                template.geometry(path,sectors=2000000)

    def test_pose_changes_only_optional_layer_and_metadata(self):
        g=template.geometry(self.path)
        base=template.scene(g)
        pose=template.scene(g,template.parse_pose('default'))
        self.assertEqual([row for row in pose if row[0]!='approximate-pose-dark-zones'][:-1],base[:-1])
        zones=next(row for row in pose if row[0]=='approximate-pose-dark-zones')
        self.assertIn('approximate, off',zones[1])
        self.assertGreater(len(zones[2]),0)

    def test_http_cli_identical_bytes_with_pose_and_selected_count(self):
        out=self.root/'cli output 模板'
        opts=['--geo',str(self.path),'--media','dvd','--sectors','1800000','--size','512','--pose','default','--out',str(out)]
        run=subprocess.run([sys.executable,'-B','-m','discprobe','template',*opts],cwd=ROOT,capture_output=True)
        self.assertEqual(run.returncode,0,run.stderr.decode(errors='replace'))
        backend=webui.Backend(self.root,drive_provider=lambda:[])
        server=webui.Server(backend,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
            payload=dict(geo='geo.json',media='dvd',sectors=1800000,size=512,pose='default')
            def request(body):
                conn.request('POST','/api/template',json.dumps(body),{'Content-Type':'application/json'})
                response=conn.getresponse()
                return response,response.read()
            response,raw=request(payload)
            self.assertEqual(response.status,200,raw[:100])
            self.assertEqual(response.getheader('Content-Type'),'application/zip')
            self.assertIn('attachment',response.getheader('Content-Disposition'))
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                self.assertEqual(set(z.namelist()),{p.name for p in out.iterdir()})
                cli_files = {name:(out/name).read_bytes() for name in z.namelist()}
                for name in z.namelist():
                    self.assertEqual(z.read(name),cli_files[name],name)
            self.assertEqual(raw,template.zip_bytes(cli_files))
            _,again=request(payload)
            self.assertEqual(raw,again)
            for bad in ({**payload,'geo':'../outside.json'},{**payload,'size':100000},
                        {**payload,'media':'cd'},{**payload,'out':'somewhere'}):
                response,raw=request(bad)
                self.assertEqual(response.status,400,raw[:100])
            conn.close()
            self.assertEqual(backend.jobs,{})
        finally:
            server.shutdown();thread.join();server.server_close()


if __name__=='__main__':
    unittest.main()
