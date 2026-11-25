export const dateKey = date => date.toISOString().slice(0, 10);

export function calendarDay(date, calendars) {
  const key = dateKey(date);
  const calendar = calendars.find(item => item.year === date.getUTCFullYear());
  const makeup = calendar?.makeup_days.includes(key);
  const holiday = calendar?.holidays.includes(key);
  const weekend = date.getUTCDay() === 0 || date.getUTCDay() === 6;
  return { key, work: makeup || (!holiday && !weekend), kind: makeup ? '补班' : holiday ? '放假' : weekend ? '周末' : '工作日', maintained: !!calendar };
}

export function calendarRange(start, end, calendars) {
  const first = Date.parse(start + 'T00:00:00Z');
  const last = Date.parse(end + 'T00:00:00Z');
  if (!Number.isFinite(first) || !Number.isFinite(last) || first > last || start < '2000-01-01' || end > '2100-12-31') return null;
  const result = { days: 0, work: 0, holiday: 0, weekend: 0, makeup: 0, missing: [] };
  const missing = new Set();
  for (let value = first; value <= last; value += 86400000) {
    const date = new Date(value);
    const day = calendarDay(date, calendars);
    result.days++;
    if (day.work) result.work++;
    if (day.kind === '放假') result.holiday++;
    if (day.kind === '周末') result.weekend++;
    if (day.kind === '补班') result.makeup++;
    if (!day.maintained) missing.add(date.getUTCFullYear());
  }
  result.missing = [...missing];
  return result;
}
