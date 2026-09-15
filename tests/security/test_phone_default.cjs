'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../../backend/app/ui/access/app.js'),'utf8');
const helper=source.match(/function phoneForRequest\(value\) \{[\s\S]*?\n  \}/)[0];
const normalize=vm.runInNewContext('('+helper+')');
for(const [input,expected] of [
  ['10000000000','+8610000000000'],['100 0000 0000','+8610000000000'],
  ['+86 100 0000 0000','+8610000000000'],['+1 (202) 555-0123','+12025550123'],
  ['',''],['1000000000',null],['8610000000000',null],['abc10000000000',null],
  ['+0123456789',null],['１００００００００００',null],['10000000000\n',null]
]) assert.equal(normalize(input),expected || null,input);
assert.match(source,/phone=phoneForRequest\(\$\('phone'\)\.value\)/);
assert.match(source,/phone=phoneForRequest\(\$\('invite-phone'\)\.value\)/);
console.log('PASS default-country normalization and auth/invitation wiring');
