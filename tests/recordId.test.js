import test from 'node:test';
import assert from 'node:assert/strict';
import { recordId } from '../src/recordId.js';

test('内网HTTP缺少randomUUID仍可创建UUID v4，连续生成不重复', () => {
  const lanCrypto = { getRandomValues: values => globalThis.crypto.getRandomValues(values) };
  const ids = Array.from({ length: 1000 }, () => recordId(lanCrypto));
  assert.equal(new Set(ids).size, ids.length);
  for (const id of ids) assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

test('安全上下文继续使用浏览器原生UUID', () => {
  assert.equal(recordId({ randomUUID: () => 'native-uuid' }), 'native-uuid');
});
