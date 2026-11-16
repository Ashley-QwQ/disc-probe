import {spawnSync} from 'node:child_process';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {tmpdir} from 'node:os';
// Run the same visible local-only fixture used for task evidence; all artifacts stay on D:.
const result=spawnSync(process.execPath,['tools/editor_w245_check.mjs','after'],{
  cwd:resolve(fileURLToPath(new URL('..',import.meta.url))),
  env:{...process.env,W245_SKIP_PERF:'1',W245_OUT:join(process.env.W245_TEST_ROOT??join(tmpdir(),'discprobe-editor'),'browser-test-'+Date.now())},
  encoding:'utf8',timeout:90000,windowsHide:true,maxBuffer:2e6});
assert.ifError(result.error);assert.equal(result.status,0,result.stdout+'\n'+result.stderr);
console.log(result.stdout.trim());
