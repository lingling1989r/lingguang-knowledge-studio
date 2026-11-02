import test from 'node:test';
import assert from 'node:assert/strict';
import {canonical} from './shared.js';
import fs from 'node:fs';
test('canonicalizes only Bilibili first-part video URLs',()=>{
 assert.equal(canonical('BV1vXJkz1E8U'),'https://www.bilibili.com/video/BV1vXJkz1E8U/');
 assert.equal(canonical('https://www.bilibili.com/video/BV1vXJkz1E8U/?spm=test'),'https://www.bilibili.com/video/BV1vXJkz1E8U/');
 for(const url of ['https://www.bilibili.com.evil.test/video/BV1vXJkz1E8U/','https://www.bilibili.com/video/BV1vXJkz1E8U/?p=2','http://127.0.0.1/private','javascript:alert(1)'])assert.throws(()=>canonical(url));
});
test('extension has no cookie, history or all-sites permissions',()=>{
 const manifest=JSON.parse(fs.readFileSync(new URL('./manifest.json',import.meta.url)));
 assert.deepEqual(manifest.permissions.sort(),['activeTab','downloads','nativeMessaging']);
 assert.equal(manifest.host_permissions,undefined);
 assert.equal(manifest.externally_connectable,undefined);
});
