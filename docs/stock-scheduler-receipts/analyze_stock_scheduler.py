"""Attribute worker wall intervals using monotonic sched_switch tracepoints."""
from pathlib import Path
from bisect import bisect_right
from collections import defaultdict,Counter
import hashlib,json,re,subprocess,sys
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/mnt/ssd/gpr_work/stock-scheduler-trace-prototype-20261030/kernel-trace')
command=['perf','script','--ns','--show-lost-events','-i',str(root/'scheduler.data'),'-F','trace:comm,pid,tid,cpu,time,event,trace']
with (root/'scheduler.txt').open('w') as out,(root/'decode.stderr').open('w') as err:subprocess.run(command,stdout=out,stderr=err,check=True,timeout=120)
collector=json.loads((root/'collector.json').read_text());receipt=json.loads((root/'receipt.json').read_text());traces=json.loads((root/'traces.json').read_text());assert collector['complete'] and receipt['complete']
header=re.compile(r'^\s*(.*?)\s+(-?\d+)/(-?\d+)\s+\[(\d+)\]\s+(\d+)\.(\d{9}):\s+((?:sched|workqueue):\w+):\s+(.*)$')
switch=re.compile(r'^prev_comm=(.*?) prev_pid=(\d+) prev_prio=(\d+) prev_state=(\S+) ==> next_comm=(.*?) next_pid=(\d+) next_prio=(\d+)$')
intervals={c:[] for c in range(4)};last={};continuity=[];lost=[];event_counts=Counter();switches={c:[] for c in range(4)};times=[];unparsed=[]
for number,line in enumerate((root/'scheduler.txt').open(),1):
 if 'PERF_RECORD_LOST' in line:lost.append(dict(line=number,text=line.strip()));continue
 if not line.strip():continue
 m=header.match(line)
 if not m:unparsed.append(dict(line=number,text=line.strip()));continue
 comm,pid,tid,cpu,seconds,nanos,event,payload=m.groups();cpu=int(cpu);time_ns=int(seconds)*1000000000+int(nanos);event_counts[event]+=1;times.append(time_ns)
 if event!='sched:sched_switch':continue
 s=switch.match(payload);assert s,(number,payload)
 prev,pid0,prio0,state,nxt,pid1,prio1=s.groups();pid0=int(pid0);pid1=int(pid1);prio0=int(prio0);prio1=int(prio1)
 if cpu in last:
  before=last[cpu];assert time_ns>=before['time_ns']
  if before['next_tid']!=pid0:continuity.append(dict(cpu=cpu,previous=before,event=dict(time_ns=time_ns,prev_tid=pid0)))
  intervals[cpu].append(dict(start_ns=before['time_ns'],end_ns=time_ns,tid=pid0,comm=prev,priority=prio0))
 last[cpu]=dict(time_ns=time_ns,next_tid=pid1,next_comm=nxt)
 switches[cpu].append(dict(time_ns=time_ns,prev_tid=pid0,prev_state=state,next_tid=pid1,next_comm=nxt,next_priority=prio1))
assert times and not unparsed,unparsed[:3]
trace_first=min(times);trace_last=max(times)
ends={c:[x['end_ns'] for x in intervals[c]] for c in intervals};phase_rows=[]
for frame in traces:
 for w in frame['workers']:
  cpu=int(w['processor']);tid=int(w['tid']);begin=round(w['absolute_start']*1e9);end=round(w['absolute_end']*1e9);assert begin<end and begin>=trace_first and end<=trace_last
  i=bisect_right(ends[cpu],begin);segments=[];covered=running=0;others=defaultdict(int)
  while i<len(intervals[cpu]) and intervals[cpu][i]['start_ns']<end:
   x=intervals[cpu][i];lo=max(begin,x['start_ns']);hi=min(end,x['end_ns']);elapsed=max(0,hi-lo);covered+=elapsed
   if x['tid']==tid:running+=elapsed
   else:
    others[(x['comm'],x['tid'],x['priority'])]+=elapsed
    if elapsed:segments.append(dict(start_ns=lo,end_ns=hi,duration_ms=elapsed/1e6,comm=x['comm'],tid=x['tid'],priority=x['priority']))
   i+=1
  assert abs(covered-(end-begin))<=1000,('incomplete worker coverage',frame['frame'],w,covered,end-begin)
  phase_rows.append(dict(frame=frame['frame'],channel=int(w['channel']),tid=tid,cpu=cpu,start_ns=begin,end_ns=end,wall_ms=(end-begin)/1e6,thread_cpu_ms=w['cpu']*1000,scheduled_ms=running/1e6,scheduled_out_ms=(covered-running)/1e6,scheduled_minus_thread_cpu_ms=running/1e6-w['cpu']*1000,involuntary=int(w['involuntary']),voluntary=int(w['voluntary']),other_tasks=[dict(comm=k[0],tid=k[1],priority=k[2],scheduled_ms=v/1e6) for k,v in sorted(others.items(),key=lambda x:x[1],reverse=True)],other_intervals=sorted(segments,key=lambda x:x['duration_ms'],reverse=True)[:20]))
assert len(phase_rows)==4*receipt['verified']['frames_verified']
(root/'worker-scheduler.json').write_text(json.dumps(phase_rows,indent=2)+'\n')
frames={r['frame']:r for r in traces};critical=[]
for f in traces:
 w=max(f['workers'],key=lambda x:x['finish']);p=next(p for p in phase_rows if p['frame']==f['frame'] and p['channel']==int(w['channel']));critical.append(dict(encode_ms=f['wall_ns']/1e6,**p))
slow=sorted(critical,key=lambda x:x['encode_ms'],reverse=True)[:16]
collector_activity=defaultdict(int)
for cpu,rows in intervals.items():
 for x in rows:
  if x['comm']=='perf':collector_activity[cpu]+=max(0,min(x['end_ns'],collector['capture_end_ns'])-max(x['start_ns'],collector['capture_start_ns']))
summary=dict(schema='gpr.scheduler_attribution.v1',complete=True,collector_sha256=hashlib.sha256((root/'collector.json').read_bytes()).hexdigest(),capture_receipt_sha256=hashlib.sha256((root/'receipt.json').read_bytes()).hexdigest(),raw_perf_sha256=collector['perf_sha256'],decode_command=command,event_counts=dict(event_counts),lost_records=lost,continuity_mismatches=continuity,all_worker_windows_covered=True,worker_phases=len(phase_rows),collector_named_perf_scheduled_ms_by_cpu={str(k):v/1e6 for k,v in collector_activity.items()},slowest_encodes=slow,largest_scheduled_out=sorted(phase_rows,key=lambda x:x['scheduled_out_ms'],reverse=True)[:16],largest_scheduled_minus_thread_cpu=sorted(phase_rows,key=lambda x:x['scheduled_minus_thread_cpu_ms'],reverse=True)[:16])
(root/'attribution.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(dict(events=summary['event_counts'],lost_records=len(lost),continuity_mismatches=len(continuity),phases=len(phase_rows),collector_ms=summary['collector_named_perf_scheduled_ms_by_cpu'],slowest=[{k:x[k] for k in ['frame','channel','cpu','encode_ms','wall_ms','thread_cpu_ms','scheduled_ms','scheduled_out_ms','scheduled_minus_thread_cpu_ms','other_tasks']} for x in slow[:4]]),indent=2))
assert not lost and not continuity,'trace has loss/discontinuity; do not promote attribution'
