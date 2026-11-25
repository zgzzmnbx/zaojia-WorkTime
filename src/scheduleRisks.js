import { orderedWindows, riskLabels, capacityComparison } from './timelineRisk.js';

// Read existing screening results; never infer an alert merely from overlapping dates.
export function scheduleRisks(result) {
  if (!result) return [];
  const windows = orderedWindows(result.windows || []).filter(window => window.rank > 0);
  const items = windows.map(window => ({
    id: `window:${window.start}/${window.end}`,
    kind: 'window', level: 'warning', rank: window.rank,
    label: riskLabels[window.rank], category: '申报总量超过时段参考',
    start: window.start, end: window.end,
    entryIds: [...new Set(window.entry_ids)],
    window, comparison: capacityComparison(window, result.rule_snapshot),
  }));
  const seen = new Set();
  for (const finding of result.findings || []) {
    if (!['跨项目', '实施期'].includes(finding.category)) continue;
    // The full set of windows above replaces the engine's one-line worst-window summary.
    if (!finding.entry_id && windows.length && finding.message.startsWith('最紧时段为')) continue;
    const id = JSON.stringify([finding.category, finding.level, finding.entry_id, finding.message]);
    if (seen.has(id)) continue;
    seen.add(id);
    const entry = result.entries?.find(entry => entry.id === finding.entry_id);
    items.push({
      id: `finding:${id}`, kind: 'finding', level: finding.level,
      label: finding.level === 'pending' ? '待补 / 待核' : '需核查',
      category: finding.category, message: finding.detail || finding.message,
      start: entry?.start, end: entry?.end,
      entryIds: finding.entry_id ? [finding.entry_id] : [],
    });
  }
  return items;
}
