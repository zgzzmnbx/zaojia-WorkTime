import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { calendarDay, calendarRange } from '../src/workCalendar.js';

const { calendars } = JSON.parse(readFileSync(new URL('../public/work-calendars.json', import.meta.url)));
test('月历和期间工作日口径一致，放假与补班优先于星期', () => {
  assert.equal(calendarDay(new Date('2026-02-14T00:00:00Z'), calendars).kind, '补班');
  assert.equal(calendarDay(new Date('2026-02-16T00:00:00Z'), calendars).kind, '放假');
  assert.deepEqual(calendarRange('2026-02-14', '2026-02-23', calendars),
    { days: 10, work: 1, holiday: 9, weekend: 0, makeup: 1, missing: [] });
  assert.equal(calendarRange('2026-12-31', '2027-01-03', calendars).work, 1);
});
test('未知年度仍可看星期，核查明确缺失日历，倒置日期无结果', () => {
  assert.deepEqual(calendarRange('2028-01-01', '2028-01-03', calendars).missing, [2028]);
  assert.equal(calendarRange('2026-02-23', '2026-02-14', calendars), null);
  assert.equal(calendarRange('', '2026-02-14', calendars), null);
});
