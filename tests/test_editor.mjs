import assert from 'node:assert/strict';
import fs from 'node:fs';
import {selection,booleanMask,migrate,shapeHit,grid} from '../discprobe/web/home/design/editor-ops.mjs';
const g={...grid(4),left_mm:0,top_mm:0,cell_mm:1};
assert.deepEqual([...selection({tool:'rectangle',a:[0,0],b:[2,2]},g)],[1,1,0,0,1,1,0,0,0,0,0,0,0,0,0,0]);
assert.deepEqual([...booleanMask([1,0,1,0],[1,1,0,0],'intersect')],[1,0,0,0]);
assert.equal(migrate({version:1,layers:[{kind:'image'}]}).layers[0].locked,false);
assert.throws(()=>migrate({version:3,layers:[]}));
assert(shapeHit({type:'ellipse'},0,0));assert(!shapeHit({type:'ellipse'},.5,.5));
for(const v of JSON.parse(fs.readFileSync(new URL('./fixtures/editor-vectors.json',import.meta.url)))){
  const m=selection(v.definition,v.grid,v.rgba);assert.equal(m.length,v.grid.width*v.grid.height);assert([...m].every(x=>x===0||x===1));
}
console.log('editor JS: migration, known masks, shared selection vectors passed');
