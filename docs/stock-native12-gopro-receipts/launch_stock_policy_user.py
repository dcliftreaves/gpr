"""Executed after setpriv; records the actual inherited process settings, then execs capture."""
from pathlib import Path
import json,os,sys,time
assert os.getuid()==os.geteuid()==1000
report=Path(sys.argv[1]);assert not report.exists()
status=Path('/proc/self/status').read_text();caps=next(s.split()[1] for s in status.splitlines() if s.startswith('CapEff:'));assert int(caps,16)==0
values=dict(pid=os.getpid(),uid=os.getuid(),euid=os.geteuid(),gid=os.getgid(),groups=os.getgroups(),nice=os.getpriority(os.PRIO_PROCESS,0),scheduler_policy=os.sched_getscheduler(0),effective_capabilities=caps,allowed_cpus=sorted(os.sched_getaffinity(0)),monotonic_ns=time.monotonic_ns(),start_ticks=int(Path('/proc/self/stat').read_text().split(') ',1)[1].split()[19]),gpr_environment={k:v for k,v in os.environ.items() if k.startswith('GPR_')},command=sys.argv[3:],realtime_priority=os.sched_getparam(0).sched_priority)
assert values['scheduler_policy']==int(sys.argv[2]) and not values['gpr_environment']
assert values['nice']==0 and values['realtime_priority']==(1 if int(sys.argv[2])==os.SCHED_FIFO else 0)
report.write_text(json.dumps(values,indent=2)+'\n');os.execv(sys.argv[3],sys.argv[3:])
