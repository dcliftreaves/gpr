from pathlib import Path
from collections import defaultdict,Counter,deque
from bisect import bisect_right
import hashlib,json,re,subprocess,time,platform
root=Path('/mnt/ssd/gpr_work/stock-scheduler-trace-prototype-20261030/kernel-workqueue')
symbols={}
for line in subprocess.check_output(['sudo','-n','cat','/proc/kallsyms'],text=True).splitlines():
 parts=line.split()
 if len(parts)>=3 and int(parts[0],16):symbols.setdefault(parts[0].lower().lstrip('0') or '0',parts[2])
def resolve(address):return symbols.get(address.lower().removeprefix('0x').lstrip('0') or '0','UNRESOLVED') if address.startswith('0x') else address
header=re.compile(r'^\s*(.*?)\s+(-?\d+)/(-?\d+)\s+\[(\d+)\]\s+(\d+)\.(\d{9}):\s+((?:sched|workqueue):\w+):\s+(.*)$')
sw=re.compile(r'^prev_comm=(.*?) prev_pid=(\d+) prev_prio=(\d+) prev_state=(\S+) ==> next_comm=(.*?) next_pid=(\d+) next_prio=(\d+)$')
work=re.compile(r'^work struct (0x[0-9a-f]+): function (\S+)$')
queue=re.compile(r'^work struct=(0x[0-9a-f]+) function=(\S+) workqueue=(.*?) req_cpu=(-?\d+) cpu=(-?\d+)$')
active=defaultdict(list);pending=defaultdict(deque);executions=[];unmatched_ends=[];nested=[];functions={};intervals=defaultdict(list);last={}
for line in (root/'scheduler.txt').open():
 m=header.match(line)
 if not m:continue
 comm,pid,tid,cpu,sec,ns,event,payload=m.groups();tid=int(tid);cpu=int(cpu);now=int(sec)*1000000000+int(ns)
 if event=='sched:sched_switch':
  s=sw.match(payload);assert s;prev,pid0,prio0,state,nxt,pid1,prio1=s.groups()
  if cpu in last:intervals[cpu].append(dict(start_ns=last[cpu],end_ns=now,tid=int(pid0),comm=prev))
  last[cpu]=now
 elif event=='workqueue:workqueue_queue_work':
  q=queue.match(payload);assert q,payload
  ptr,fn,name,requested,target=q.groups();pending[ptr].append(dict(queued_ns=now,queue=name,queueing_context_comm=comm,queueing_context_tid=tid,requested_cpu=int(requested),target_cpu=int(target)))
  functions[fn]=resolve(fn)
 elif event in ['workqueue:workqueue_execute_start','workqueue:workqueue_execute_end']:
  q=work.match(payload);assert q,payload
  ptr,fn=q.groups();functions[fn]=resolve(fn)
  if event.endswith('start'):
   if active[tid]:nested.append(dict(tid=tid,time_ns=now))
   queued=pending[ptr].popleft() if pending[ptr] else None
   active[tid].append(dict(start_ns=now,work=ptr,function=functions[fn],function_token=hashlib.sha256(fn.encode()).hexdigest()[:16],tid=tid,cpu_start=cpu,queued=queued,comm=comm))
  elif not active[tid]:unmatched_ends.append(dict(tid=tid,time_ns=now))
  else:
   e=active[tid].pop();assert e['work']==ptr and e['function']==functions[fn],(e,payload)
   e['end_ns']=now;e['wall_ms']=(now-e['start_ns'])/1e6;e['cpu_end']=cpu;e['work_token']=hashlib.sha256(e.pop('work').encode()).hexdigest()[:16];executions.append(e)
assert not nested,'nested callbacks require overlap-aware attribution'
bytid=defaultdict(list)
for e in sorted(executions,key=lambda e:e['start_ns']):bytid[e['tid']].append(e)
ends={tid:[e['end_ns'] for e in es] for tid,es in bytid.items()};iend={cpu:[s['end_ns'] for s in ss] for cpu,ss in intervals.items()}
attribution=json.loads((root/'attribution.json').read_text());assert not attribution['lost_records'] and not attribution['continuity_mismatches']
results=[]
for phase in attribution['largest_scheduled_out'][:16]:
 begin=phase['start_ns'];end=phase['end_ns'];cpu=phase['cpu'];i=bisect_right(iend[cpu],begin);totals=defaultdict(int);matches=[];unmatched=0
 while i<len(intervals[cpu]) and intervals[cpu][i]['start_ns']<end:
  s=intervals[cpu][i];lo=max(begin,s['start_ns']);hi=min(end,s['end_ns']);i+=1
  if s['tid']==phase['tid']:continue
  windows=bytid[s['tid']];j=bisect_right(ends.get(s['tid'],[]),lo);matched=0
  while j<len(windows) and windows[j]['start_ns']<hi:
   w=windows[j];a=max(lo,w['start_ns']);b=min(hi,w['end_ns']);j+=1
   if b>a:
    matched+=b-a;totals[(s['comm'],s['tid'],w['function'])]+=b-a;matches.append(dict(scheduled_start_ns=a,scheduled_end_ns=b,scheduled_ms=(b-a)/1e6,function=w['function'],tid=s['tid'],comm=s['comm'],work_token=w['work_token'],execution_start_ns=w['start_ns'],execution_end_ns=w['end_ns'],execution_wall_ms=w['wall_ms'],queued=w['queued']))
  assert matched<=hi-lo+1000;unmatched+=hi-lo-matched
 results.append(dict(frame=phase['frame'],channel=phase['channel'],cpu=cpu,worker_tid=phase['tid'],worker_wall_ms=phase['wall_ms'],worker_cpu_ms=phase['thread_cpu_ms'],scheduled_out_ms=phase['scheduled_out_ms'],unmatched_other_ms=unmatched/1e6,functions=[dict(comm=k[0],tid=k[1],function=k[2],scheduled_ms=v/1e6) for k,v in sorted(totals.items(),key=lambda x:x[1],reverse=True)],matches=sorted(matches,key=lambda x:x['scheduled_ms'],reverse=True)))
resolved=[dict(token=hashlib.sha256(a.encode()).hexdigest()[:16],symbol=s) for a,s in functions.items()];summary=dict(schema='gpr.stock_workqueue_attribution.v1',complete=True,kernel=platform.release(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),resolved_at_monotonic_ns=time.monotonic_ns(),work_functions=resolved,executions=len(executions),nested_callbacks=len(nested),unmatched_ends_at_trace_boundary=unmatched_ends,unfinished_starts_at_trace_boundary=sum(len(v) for v in active.values()),largest_scheduled_out=results)
(root/'workqueue-attribution.json').write_text(json.dumps(summary,indent=2)+'\n');(root/'workqueue-executions.json').write_text(json.dumps(executions,indent=2)+'\n')
print(json.dumps(dict(functions=resolved,slowest=results[:4]),indent=2))
