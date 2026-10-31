from pathlib import Path
import hashlib,json,os,re,subprocess
root=Path('/mnt/ssd/gpr_work/stock-affinity-offset-prototype-20261030');out=root/'placement';out.mkdir(exist_ok=True);h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();rows=[]
for value,cpus,expected_offset in [('0',[0,1,2,3],0),('1',[0,1,2,3],1),('2',[0,1,2,3],2),('3',[0,1,2,3],3),('-1',[0,1,2,3],0),('4',[0,1,2,3],0),('bad',[0,1,2,3],0),('999999999999999999999999',[0,1,2,3],0),('1',[1,3],1)]:
 name=value+'-cores'+''.join(map(str,cpus));command=['taskset','-c',','.join(map(str,cpus)),'ctest','--test-dir',str(root/'build'),'-V','-R','^encoder_preview_probe_fast$'];env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')};env.update(GPR_CHANNEL_CPU_OFFSET=value,GPR_AFFINITY_TRACE='1');p=subprocess.run(command,capture_output=True,text=True,env=env,timeout=120);log=p.stdout+p.stderr;(out/(name+'.log')).write_text(log);assert p.returncode==0,log
 placements=[dict(channel=int(a),processor=int(b),pinned=int(c)) for a,b,c in re.findall(r'affinity channel=(\d+) processor=(\d+) pinned=(\d+)',log)];assert len(placements)==72
 assert all(x['pinned']==1 and x['processor']==cpus[(x['channel']+expected_offset)%len(cpus)] for x in placements),placements
 rows.append(dict(value=value,allowed_cpus=cpus,expected_offset=expected_offset,placements_checked=len(placements),all_placements_exact=True,command=command,environment={k:v for k,v in env.items() if k.startswith('GPR_')}));print(name,'72 exact placements and byte/preview checks PASS',flush=True)
(out/'receipt.json').write_text(json.dumps(dict(complete=True,source_sha256=h(root/'source/lib/vc5_encoder/encoder.c'),probe_sha256=h(root/'build/encoder_preview_probe'),rows=rows),indent=2)+'\n')
