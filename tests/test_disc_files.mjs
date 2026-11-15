import assert from 'node:assert/strict';
import {fileArguments,filePictureRange,occupiedRings,localFilesAvailable} from '../discprobe/web/home/design/disc-files.mjs';
const files={folder:'D:/data',where:'outer',layout:{files_margin:.05,writable_sectors:2000,
  occupied_radius_mm:[[24,25],[50,55]],margin_radius_mm:[55,56],picture_radius_mm:[[25,50]]}};
assert.deepEqual(fileArguments(files),{files:'D:/data',files_at:'outer',files_margin:.05,writable_sectors:2000});
assert.deepEqual(filePictureRange(files,[24.5,56]),[25,50]);
assert.deepEqual(filePictureRange(null,[24.5,56]),[24.5,56]);
assert.equal(occupiedRings(files).length,3);
assert(localFilesAvailable('localhost'));
assert(!localFilesAvailable('192.168.1.2'));
assert.throws(()=>fileArguments({folder:'D:/data'}));
console.log('disc-files: 7 assertions passed');
