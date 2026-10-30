from pathlib import Path
import subprocess,os,json
root=Path('/mnt/ssd/gpr_work/stock-entropy-handoff-prototype-20261030');out=root/'extra-tests';out.mkdir(exist_ok=True);rows=[]
for name,extra in [('zero',{'GPR_PROBE_PATTERN':'0'}),('maximum',{'GPR_PROBE_PATTERN':'1'}),('sparse',{'GPR_PROBE_PATTERN':'2'}),('no-created-threads',{'GPR_HANDOFF_NO_THREADS':'1'})]:
 cmd=['ctest','--test-dir',str(root/'build'),'--output-on-failure','-R','encoder_preview_(probe|matrix)_fast'];p=subprocess.run(cmd,capture_output=True,text=True,env={**os.environ,**extra},timeout=120);(out/(name+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,(name,p.stdout,p.stderr);rows.append(dict(name=name,environment=extra,command=cmd,returncode=p.returncode));print(name,'PASS',flush=True)
(out/'receipt.json').write_text(json.dumps(rows,indent=2)+'\n')
