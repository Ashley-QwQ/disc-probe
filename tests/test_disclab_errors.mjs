import {test} from 'node:test';
import assert from 'node:assert/strict';
import {commandError} from '../disclab/web/errors.mjs';
test('disk-full diagnostics survive a generic exit summary in both languages', () => {
  for(const lang of ['zh','en']) {
    const message=commandError({errors:[{message:'exit code 1'}]},'writing...\nOSError: [Errno 28] No space left on device\n',lang);
    assert.match(message,/--lab/);assert.doesNotMatch(message,/exit code 1/);
    assert.match(message,lang==='zh'?/磁盘空间不足/:/Disk space/);
  }
});
test('last real diagnostic is shown with recovery advice, safely as plain text', () => {
  const message=commandError({errors:[{message:'exit code 1'}]},'working\nValueError: bad geometry <sample>\nexit code 1','zh');
  assert.match(message,/ValueError: bad geometry <sample>/);assert.match(message,/重试/);
});
