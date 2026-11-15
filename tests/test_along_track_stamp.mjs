import assert from 'node:assert/strict';
import {photoSaveWords} from '../discprobe/web/home/guidance.mjs';

for (const frames of [-105, 206, 0]) {
  const words = photoSaveWords({written:true,frames});
  assert.match(words.zh, new RegExp(`L = ${frames} frames`));
  assert.match(words.zh, /来自照片，盘批次无关，换光驱要重拍/);
  assert.match(words.en, /From photos, independent of disc batch; rephotograph after changing drives/);
  for (const lang of ['zh','en']) assert.doesNotMatch(words[lang], /guess|猜测/);
}
assert.equal(photoSaveWords({written:false,reason:'different_run'}).zh,
  '沿轨常数没写进去：照片对应的是另一次测量。');
// A DVD photo result (not_cd) is not a refusal: the DIS preset just has no CD frames field (7e1fd20)
const dvd = photoSaveWords({written:false,reason:'not_cd',frames:0});
assert.match(dvd.zh, /DIS 的预设只记 CD 的帧数/);
assert.match(dvd.en, /DIS presets only record CD frames/);
for (const lang of ['zh','en']) assert.doesNotMatch(dvd[lang], /没写进去|not written|L = 0|0 frames/);
for (const reason of ['different_run','different_drive','unknown_drive','verdict_not_ok','missing_L','no_photo','invalid_photo','invalid_preset',undefined]) {
  const words = photoSaveWords({written:false,reason,frames:0});
  assert.match(words.zh, /沿轨常数没写进去：/);
  assert.match(words.en, /Along-track constant not written:/);
  for (const lang of ['zh','en']) assert.doesNotMatch(words[lang], /L = 0|0 frames|已写入|constant written:/);
}
assert.match(photoSaveWords({written:true,frames:NaN}).en, /not written/);
console.log('Saved photo L and refusal stamps passed in zh and en');
