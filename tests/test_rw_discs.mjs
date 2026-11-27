import {test} from 'node:test';
import assert from 'node:assert/strict';
import {shortDiscWords,interruptedBurn,stopWords} from '../discprobe/web/home/burn-stop.js';

test('rewritable and write-once stop risks stay distinct in both languages',()=>{
  assert.equal(stopWords('zh').risk,'停止后这张盘作废：不能再刻，也不能拿来测。');
  assert.equal(stopWords('zh',true).risk,'停止后这次刻录作废，要擦掉才能重新刻。');
  assert.match(stopWords('en',true).risk,/erase the disc before burning again/);
  assert.doesNotMatch(stopWords('en',true).risk,/unusable/);
});
test('rewritable short and interrupted recordings offer erasing, retaining failure cause',()=>{
  for(const lang of ['zh','en']){
    const re=lang==='zh'?/擦除.*重新刻/:/erase.*burning again/i;
    assert.match(interruptedBurn({detected:{rewritable:true},cancelledByUser:{phase:'burn',fraction:.5}},lang),re);
    const failed=interruptedBurn({rewritable:true,burnCheck:{result:'failed',reason:'write error 123'}},lang);
    assert.match(failed,re);assert.match(failed,/write error 123/);
    assert.match(shortDiscWords({rewritable:true,blank:false,closed:true,sectors:576},lang),lang==='zh'?/擦除这张可擦写盘/:/Erase this rewritable disc/);
  }
});
