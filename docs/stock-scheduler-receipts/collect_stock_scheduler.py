"""Owned, bounded kernel scheduler collector; capture remains under the caller UID."""
from pathlib import Path
import hashlib,json,os,select,signal,stat,subprocess,time

def collect(root,command,environment,seconds=45):
 root=Path(root);root.mkdir(exist_ok=True);assert not (root/'collector.json').exists();assert os.geteuid()!=0
 ctl=root/'control.fifo';ack=root/'ack.fifo'
 for p in [ctl,ack]:assert not p.exists();os.mkfifo(p,0o600)
 ctl_fd=os.open(ctl,os.O_RDWR|os.O_NONBLOCK);ack_fd=os.open(ack,os.O_RDWR|os.O_NONBLOCK)
 perfdata=root/'scheduler.data';perf_command=['sudo','-n','nice','-n','10','taskset','-c','3','perf','record','-a','-e','sched:sched_switch','-e','sched:sched_wakeup','-e','sched:sched_wakeup_new','-k','mono','-m','64','-B','-N','-D','-1','--control','fifo:'+str(ctl)+','+str(ack),'-o',str(perfdata),'--','sleep',str(seconds)]
 result=dict(schema='gpr.owned_scheduler_collector.v1',complete=False,collector_command=perf_command,capture_command=command,caller_uid=os.getuid(),caller_gid=os.getgid(),collector_cpu=3,collector_nice=10,events=['sched_switch','sched_wakeup','sched_wakeup_new'],clock='CLOCK_MONOTONIC',control=[])
 def save(): (root/'collector.json').write_text(json.dumps(result,indent=2)+'\n')
 def control(text,expect_ack=True):
  assert perf.poll() is None,('collector exited',perf.returncode)
  os.write(ctl_fd,(text+'\n').encode());sent=time.monotonic_ns();response=b''
  if expect_ack:
   deadline=time.monotonic()+10
   while b'ack\n' not in response:
    if perf.poll() is not None:raise RuntimeError('collector exited before '+text+' ack')
    if time.monotonic()>deadline:raise TimeoutError('no collector ack for '+text)
    if select.select([ack_fd],[],[],.1)[0]:response+=os.read(ack_fd,4096)
  result['control'].append(dict(command=text,sent_ns=sent,acknowledged=expect_ack,response=response.decode(errors='replace'),completed_ns=time.monotonic_ns()));save()
 child=None;perf=None;error=None
 try:
  with (root/'perf.stdout').open('w') as perf_stdout,(root/'perf.stderr').open('w') as perf_stderr:
   perf=subprocess.Popen(perf_command,stdout=perf_stdout,stderr=perf_stderr);result['collector_wrapper_pid']=perf.pid;save()
   control('enable')
   with (root/'events.jsonl').open('w') as stdout,(root/'events.jsonl.stderr').open('w') as stderr:
    start=time.monotonic_ns();child=subprocess.Popen(command,stdout=stdout,stderr=stderr,env=environment);result['capture_pid']=child.pid;result['capture_start_ns']=start
    status=Path('/proc')/str(child.pid)/'status';uids=next(s.split()[1:] for s in status.read_text().splitlines() if s.startswith('Uid:'));assert all(int(v)==os.getuid() for v in uids);result['observed_capture_uids']=list(map(int,uids));result['capture_scheduler_policy']=os.sched_getscheduler(child.pid);result['capture_nice']=os.getpriority(os.PRIO_PROCESS,child.pid);assert result['capture_scheduler_policy']==os.SCHED_OTHER and result['capture_nice']==0;save()
    result['capture_exit']=child.wait(timeout=90);result['capture_end_ns']=time.monotonic_ns();save()
   control('disable')
   # Let the explicitly bounded collector workload finish naturally (exit 0).
   result['collector_exit']=perf.wait(timeout=seconds+10)
   assert result['capture_exit']==result['collector_exit']==0,result
 except BaseException as e:
  error=e;result['error']=repr(e)
 finally:
  if child is not None and child.poll() is None:
   child.terminate()
   try:child.wait(timeout=5)
   except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
  if perf is not None and perf.poll() is None:
   try:control('stop',expect_ack=False)
   except BaseException as e:result['cleanup_control_error']=repr(e)
   # The only profiler workload is bounded sleep. Never signal unrelated root processes.
   result['collector_exit']=perf.wait(timeout=seconds+10)
  os.close(ctl_fd);os.close(ack_fd)
  for p in [ctl,ack]:
   if p.exists() and stat.S_ISFIFO(p.stat().st_mode):p.unlink()
  result['collector_terminal']=perf is not None and perf.poll() is not None;result['capture_terminal']=child is not None and child.poll() is not None
  if perfdata.exists():
   assert perfdata.is_file() and not perfdata.is_symlink();subprocess.run(['sudo','-n','chown',str(os.getuid())+':'+str(os.getgid()),str(perfdata)],check=True,timeout=10);result['perf_bytes']=perfdata.stat().st_size;result['perf_sha256']=hashlib.sha256(perfdata.read_bytes()).hexdigest()
  result['complete']=error is None and result['collector_terminal'] and result['capture_terminal'];save()
 if error:raise error
 return result

if __name__=='__main__':
 import sys
 root=Path('/mnt/ssd/gpr_work/stock-scheduler-trace-prototype-20261030/control-proof-natural');result=collect(root,['/usr/bin/sleep','1'],os.environ.copy(),seconds=5);assert result['complete'] and [x['command'] for x in result['control']]==['enable','disable'];print(json.dumps(result,indent=2))
