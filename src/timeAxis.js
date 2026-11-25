const DAY=86400000;
const day=s=>Date.parse(s+'T00:00:00Z')/DAY;
const iso=n=>new Date(n*DAY).toISOString().slice(0,10);

// A broken time axis only compresses empty gaps, never an entry or a calculation.
export function timeAxis(entries, compress=true) {
  const intervals=entries.filter(e=>e.start&&e.end&&day(e.end)>=day(e.start))
    .map(e=>[day(e.start),day(e.end)+1]).sort((a,b)=>a[0]-b[0]);
  const merged=[];
  for(const [a,b] of intervals){const last=merged.at(-1);if(last&&a<=last[1])last[1]=Math.max(last[1],b);else merged.push([a,b]);}
  const start=(merged[0]?.[0]??0)-3,end=Math.max(start+28,(merged.at(-1)?.[1]??25)+4);
  const gaps=merged.slice(1).flatMap((v,i)=>v[0]-merged[i][1]>60?[{start:merged[i][1],end:v[0],days:v[0]-merged[i][1]}]:[]);
  const active=compress?gaps:[];
  const reduced=n=>n-start-active.reduce((sum,g)=>sum+Math.max(0,Math.min(n,g.end)-g.start)*(1-14/g.days),0);
  const length=reduced(end);
  const fraction=n=>reduced(n)/length;
  const segments=[];let cursor=start;
  for(const gap of active){segments.push([cursor,gap.start]);cursor=gap.end;}segments.push([cursor,end]);
  const ticks=active.length?segments.flatMap(([a,b])=>[a,b-1]):Array.from({length:6},(_,i)=>Math.round(start+(end-start-1)*i/5));
  return {start,end,fraction,gaps:gaps.map(g=>({...g,from:iso(g.start),to:iso(g.end-1)})),compressed:active.length>0,
    ticks:[...new Set(ticks)].map(n=>({day:n,label:iso(n)}))};
}
