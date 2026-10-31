from pathlib import Path
import json,re,sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(sys.argv[1]);out=Path(sys.argv[2]);frames=json.loads((root/'traces.json').read_text());phase=next(f for f in frames if f['frame']==158);w=phase['workers'][0];tid=int(w['tid']);cpu=int(w['processor']);begin=round(w['absolute_start']*1e9);end=round(w['absolute_end']*1e9)
head=re.compile(r'^\s*(.*?)\s+(-?\d+)/(-?\d+)\s+\[(\d+)\]\s+(\d+)\.(\d{9}):\s+sched:sched_switch:\s+(.*)$');prev=re.compile(r'^prev_comm=(.*?) prev_pid=(\d+) ');last=None;ranges={'Encoder thread':[],'Kernel worker':[],'Other tasks':[]};states=[]
for line in (root/'scheduler.txt').open():
 m=head.match(line)
 if not m or int(m[4])!=cpu:continue
 now=int(m[5])*1000000000+int(m[6]);p=prev.match(m[7]);assert p
 if last is not None:
  lo=max(last,begin);hi=min(now,end)
  if hi>lo:
   key='Encoder thread' if int(p[2])==tid else 'Kernel worker' if p[1].startswith('kworker/0:0') else 'Other tasks';ranges[key].append(((lo-begin)/1e6,(hi-lo)/1e6))
 last=now
 if now>end:break
assert abs(sum(width for rs in ranges.values() for _,width in rs)-(end-begin)/1e6)<.001
fig,ax=plt.subplots(figsize=(11,3.2),layout='constrained');colors={'Encoder thread':'#2463a5','Kernel worker':'#d47725','Other tasks':'#777777'}
for key,rs in ranges.items():
 total=sum(width for _,width in rs);ax.broken_barh(rs,(0,.6),facecolors=colors[key],label=f'{key}: {total:.2f} ms')
ax.set_xlim(0,(end-begin)/1e6);ax.set_ylim(-.4,.8);ax.set_yticks([.3],[f'CPU {cpu}']);ax.set_xlabel('Milliseconds from channel-0 worker start');ax.set_title('Instrumented frame 158: MMC maintenance occupies CPU 0 while encoding waits\nKernel worker intervals are attributed to mmc_rescan by workqueue events',fontsize=11);ax.legend(loc='lower center',bbox_to_anchor=(.5,.01),ncol=3,fontsize=9);ax.spines[['top','right']].set_visible(False);fig.savefig(out,dpi=160)
