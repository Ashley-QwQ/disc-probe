import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

// The site ships browser ESM .js files without a Node package declaration.
// Import the source unchanged, with no DOM mocks or third-party packages.
const source = readFileSync(new URL('../discprobe/web/home/photocal.js', import.meta.url), 'utf8');
const {DEFAULT_RINGS, ringHandles, mmToPx, pxToMm, zoomAt, resizeRing, magnifierPlacement, photoKey}
  = await import('data:text/javascript;base64,' + Buffer.from(source.replace(/^import .*;$/gm, '')).toString('base64'));
const close = (a,b) => assert.ok(Math.abs(a-b) < 1e-9, `${a} != ${b}`);

assert.deepEqual(DEFAULT_RINGS, [30,38,47,55]);
assert.ok(Object.isFrozen(DEFAULT_RINGS));
for (const radius of DEFAULT_RINGS) {
  const handles = ringHandles(radius);
  assert.deepEqual(handles.map(h => h.degrees), [45,135,225,315]);
  for (const h of handles) { close(Math.hypot(h.x,h.y),radius); close(Math.abs(h.x),Math.abs(h.y)); }
  close(handles[0].x,-handles[2].x); close(handles[0].y,-handles[2].y);
}
for (const zoom of [0.25,1,2.02,12]) {
  const view = {cx:460,cy:280,pxPerMm:4.55,zoom,panX:137,panY:-82};
  for (const point of [{x:0,y:0},{x:47,y:0},...ringHandles(55)]) {
    const back = pxToMm(mmToPx(point,view),view);
    close(back.x,point.x); close(back.y,point.y);
  }
  for (const pointer of [{x:0,y:0},{x:459,y:299},{x:920,y:668}]) {
    const before = pxToMm(pointer,view);
    for (const factor of [0.001,0.8,1.3,1000]) {
      const next = zoomAt(view,pointer,factor), after = pxToMm(pointer,next);
      assert.ok(next.zoom >= 0.25 && next.zoom <= 12);
      close(after.x,before.x); close(after.y,before.y);
      assert.equal(view.zoom,zoom); // zoomAt never mutates its input.
    }
  }
}
const rings = [...DEFAULT_RINGS];
assert.deepEqual(resizeRing(rings,2,48.25),[30,38,48.25,55]);
assert.deepEqual(rings,DEFAULT_RINGS);
assert.deepEqual(resizeRing(rings,0,-50),[24,38,47,55]);
assert.deepEqual(resizeRing(rings,3,500),[30,38,47,58]);
for (const index of [-1,4,1.5]) assert.deepEqual(resizeRing(rings,index,45),rings);
assert.deepEqual(resizeRing(rings,1,NaN),rings);

// Drag a handle after a zoom and a pan: only that ring changes in mm.
const view = {cx:400,cy:300,pxPerMm:4,zoom:3,panX:-127,panY:91};
const screen = mmToPx(ringHandles(49)[2],view), world = pxToMm(screen,view);
const adjusted = resizeRing(rings,2,Math.hypot(world.x,world.y));
close(adjusted[2],49); assert.deepEqual([adjusted[0],adjusted[1],adjusted[3]],[30,38,55]);

// Exercise viewport edges and corners, where naive clamping covers the hand.
for (const bounds of [{width:920,height:668},{width:1440,height:900},{width:280,height:180},{width:80,height:80}]) {
  for (let x = 0; x <= bounds.width; x += bounds.width/10) {
    for (let y = 0; y <= bounds.height; y += bounds.height/10) {
      const pointer = {x,y}, place = magnifierPlacement(pointer,bounds);
      if (!place) continue;
      assert.ok(place.x >= 8 && place.y >= 8);
      assert.ok(place.x+place.size <= bounds.width-8+1e-9);
      assert.ok(place.y+place.size <= bounds.height-8+1e-9);
      const dx = Math.max(place.x-x,0,x-place.x-place.size);
      const dy = Math.max(place.y-y,0,y-place.y-place.size);
      assert.ok(Math.hypot(dx,dy) >= 18, 'Magnifier covers the hand');
    }
  }
}
const usual = magnifierPlacement({x:400,y:400},{width:920,height:668});
assert.ok(usual.x > 400 && usual.y+usual.size < 400,'Prefer up-right when there is space');
assert.equal(magnifierPlacement({x:15,y:15},{width:30,height:30}),null);

const start = {focus:true,dragging:true};
const firstEsc = photoKey(start,'Escape');
assert.equal(firstEsc.focus,false); assert.equal(firstEsc.dragging,true);
assert.equal(firstEsc.action,undefined,'First Esc must only leave focus');
const secondEsc = photoKey(firstEsc,'Escape');
assert.equal(secondEsc.dragging,false); assert.equal(secondEsc.action,undefined);
assert.equal(photoKey(secondEsc,'Escape').action,'back');
assert.deepEqual(start,{focus:true,dragging:true});
assert.equal(photoKey({focus:false},'f').focus,true);
assert.equal(photoKey({focus:true},'F').focus,false);
assert.deepEqual(photoKey({focus:false},'x'),{focus:false});
console.log('Photo calibration geometry, transforms, magnifier and focus handling passed');
