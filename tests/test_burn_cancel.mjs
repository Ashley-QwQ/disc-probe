import {test} from 'node:test';
import assert from 'node:assert/strict';
import {shortDiscWords,interruptedBurn,stopWords} from '../discprobe/web/home/burn-stop.js';
import {keyboardReducer,initialHold} from '../discprobe/web/home/kit/slideconfirm.js';

test('a finalized 576-sector disc is rejected, with a blank-disc recovery in both languages',()=>{
  for(const lang of ['zh','en']){
    const disc={closed:true,blank:false,sectors:576};
    assert.match(shortDiscWords(disc,lang),/576.*1 MB/);
    assert.match(shortDiscWords(disc,lang),lang==='zh'?/不能用来测.*空白盘/:/cannot be used for measurement.*blank disc/);
    assert.equal(shortDiscWords({...disc,closed:false},lang),null);
    assert.equal(shortDiscWords({...disc,sectors:2295104},lang),null);
  }
});
test('burn cancellation names the user and percentage; failures retain the actual cause',()=>{
  for(const lang of ['zh','en']){
    assert.match(interruptedBurn({cancelledByUser:{phase:'burn',fraction:.16}},lang),/16%/);
    assert.match(interruptedBurn({burnCheck:{result:'failed',reason:'IMAPI WRITE ERROR'}},lang),/IMAPI WRITE ERROR/);
    assert.equal(interruptedBurn({cancelledByUser:{phase:'timing'}},lang),null);
    assert.equal(interruptedBurn({burnCheck:{result:'completed'}},lang),null);
    assert.ok(stopWords(lang).risk);
  }
});
test('Space and Enter use a held second when opted in; disabled states ignore both',()=>{
  // ime-enter-exempt: Pure reducer inputs, no text or form handling.
  for(const key of ['Enter',' ']){
    let state=keyboardReducer(initialHold(),{type:'down',key,holdPress:true,now:0});
    assert.equal(keyboardReducer(state,{type:'tick',now:999}).phase,'holding');
    assert.equal(keyboardReducer(state,{type:'tick',now:1000}).phase,'confirmed');
    state=keyboardReducer(state,{type:'disable'});
    assert.equal(keyboardReducer(state,{type:'down',key,holdPress:true,now:5000}).phase,'disabled');
  }
});
