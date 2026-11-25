import test from 'node:test';
import assert from 'node:assert/strict';
import {timeAxis} from '../src/timeAxis.js';
const day=s=>Date.parse(s+'T00:00:00Z')/86400000;
test('跨年空档可逆折叠，日期映射保持顺序、含首尾日且不改变原记录',()=>{
  const entries=[{start:'2024-03-01',end:'2024-03-28'},{start:'2026-03-01',end:'2026-03-28'}];
  const before=structuredClone(entries),fold=timeAxis(entries),full=timeAxis(entries,false);
  assert.equal(fold.gaps.length,1);assert.ok(fold.compressed);assert.ok(!full.compressed);
  const width=axis=>axis.fraction(day(entries[0].end)+1)-axis.fraction(day(entries[0].start));
  assert.ok(width(fold)>width(full)*5);
  assert.deepEqual(entries,before);
  assert.ok(fold.ticks.some(t=>t.label.startsWith('2024'))&&fold.ticks.some(t=>t.label.startsWith('2026')));
  assert.equal(fold.fraction(fold.start),0);assert.equal(fold.fraction(fold.end),1);
  assert.ok(fold.fraction(day('2025-03-01'))<fold.fraction(day('2026-03-01')));
});
test('连续长期申报覆盖的时段与短空档不折叠，不虚构分段',()=>{
  const axis=timeAxis([{start:'2024-01-01',end:'2026-12-31'},{start:'2026-03-01',end:'2026-03-20'}]);
  assert.equal(axis.gaps.length,0);assert.equal(axis.compressed,false);
  assert.equal(timeAxis([{start:'2026-03-01',end:'2026-03-20'},{start:'2026-04-01',end:'2026-04-20'}]).compressed,false);
});
