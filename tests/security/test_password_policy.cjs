'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../../backend/app/ui/access/app.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../../backend/app/ui/access/index.html'),'utf8');
const guard=source.match(/if\(state\.mode==='register'&&\(Array\.from\(password\)\.length<\d+\|\|Array\.from\(password\)\.length>\d+\)\)\{status\('invalidPassword'\);return;\}/)[0];
for(const [password,rejected] of [['a'.repeat(7),true],['a'.repeat(8),false],['a'.repeat(128),false],['a'.repeat(129),true],['       a',false],['家'.repeat(8),false]]) {
  let denied=false;
  vm.runInNewContext('(function(){'+guard+'})()', {state:{mode:'register'},password,status:()=>{denied=true;}});
  assert.equal(denied,rejected);
}
assert.match(source,/minLength=mode==='register'\?8:1/);
assert.match(source,/Choose a passphrase of 8–128 characters/);
assert.match(source,/请设置 8–128 个字符/);
assert.match(html,/Choose a passphrase of 8–128 characters/);
console.log('PASS registration boundaries and bilingual password guidance');
