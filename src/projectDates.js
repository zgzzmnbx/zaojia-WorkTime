export const projectDateHint = '实施开始和实施结束都须在建设期内，可以与建设期边界同日。';

export function projectDateError({build_start, build_end, impl_start, impl_end}) {
  if (build_start && build_end && build_end < build_start) {
    return {field:'build_end', message:'建设结束日期不能早于建设开始日期'};
  }
  if (impl_start && impl_end && impl_end < impl_start) {
    return {field:'impl_end', message:'实施结束日期不能早于实施开始日期'};
  }

  for (const [field, date] of [['impl_start', impl_start], ['impl_end', impl_end]]) {
    if (date && build_start && date < build_start) {
      return {field, message:'实施日期不能早于建设开始日期'};
    }
    if (date && build_end && date > build_end) {
      return {field, message:'实施日期不能晚于建设结束日期'};
    }
  }
  return null;
}
