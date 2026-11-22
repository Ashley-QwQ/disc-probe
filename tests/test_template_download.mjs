import {test} from 'node:test';
import assert from 'node:assert/strict';
import {gridArtworkPitch, templateDetails, templateRequest} from '../discprobe/web/home/design/template-download.mjs';

test('template uses selected batch geometry and sector count, never another batch', () => {
  assert.deepEqual(templateRequest({media:'dvd', geo:'old.json', item:{geo:'mine.json',sectors:1234567}}),
    {geo:'mine.json',media:'dvd',sectors:1234567});
  assert.deepEqual(templateRequest({media:'bd', item:{preset:'presets/discs.json',id:'preset:my-disc'}}),
    {geo:'presets/discs.json',media:'bd',preset_id:'my-disc'});
  assert.throws(() => templateRequest({media:'dvd',item:{kind:'unset'}}), /geometry/);
});

test('grid request uses the current pose and labels a large canvas', () => {
  const work = {media:'dvd',item:{geo:'mine.json',mid:'RITEKF1',sectors:2297888},lookY:75,
    scene:{cam:[0,-70,330],follows:true,flashOffset:[-40,20]},lampLook:{rotate:30,z:350}};
  assert.deepEqual(templateRequest(work,5), {geo:'mine.json',media:'dvd',sectors:2297888,grid:5,
    batch:'RITEKF1',pose:'0,75,350,-40,95,350',rotate:30});
  assert.match(templateDetails(5,'zh'), /24,000 × 24,000.*2\.15 GiB/);
  assert.match(templateDetails(10,'en'), /12,000 × 12,000.*separate guide/);
});

test('full-size artwork uses DPI or an explicit import, preserving ordinary image fitting', async () => {
  for (const [side, pitch] of [[24000,5],[12000,10],[6000,20]]) {
    const png = Buffer.alloc(54);
    png.set([137,80,78,71,13,10,26,10]);
    png.writeUInt32BE(13,8); png.write('IHDR',12);
    png.writeUInt32BE(side,16); png.writeUInt32BE(side,20);
    png.writeUInt32BE(9,33); png.write('pHYs',37);
    png.writeUInt32BE(1e6/pitch,41); png.writeUInt32BE(1e6/pitch,45); png[49]=1;
    assert.equal(await gridArtworkPitch(new File([png],'artwork.png')),pitch);
    assert.equal(await gridArtworkPitch(new File([png.subarray(0,33)],'artwork.png')),null);
    assert.equal(await gridArtworkPitch(new File([png.subarray(0,33)],'artwork.png'),true),pitch);
    assert.equal(await gridArtworkPitch(new File([png.subarray(0,33)],`dp_template_${pitch}um_artwork.png`)),pitch);
  }
});
