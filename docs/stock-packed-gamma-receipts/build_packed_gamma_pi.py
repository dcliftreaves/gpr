from pathlib import Path
import subprocess,json,hashlib
root=Path('/mnt/ssd/gpr_work/stock-packed-gamma-prototype-20261030');rows=[]
for mode,value in [('dense',0),('packed',1)]:
 build=root/('build-'+mode);commands=[['cmake','-S',str(root),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_CXX_FLAGS=-DGPR_PACKED_GAMMA='+str(value),'-DGPR_BUILD_SDK=OFF','-DGPR_BUILD_STILL_APPS=OFF','-DGPR_ENABLE_VIDEO=ON','-DGPR_BUILD_CAPTURE_APP=ON','-DGPR_BUILD_PREVIEW_TOOLS=ON','-DGPR_BUILD_PREVIEW_TESTS=ON'],['cmake','--build',str(build),'-j','4'],['ctest','--test-dir',str(build),'--output-on-failure']]
 for stage,cmd in zip(['configure','build','tests'],commands):
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=300);(root/(mode+'-'+stage+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,(mode,stage,p.stdout[-3000:],p.stderr[-3000:])
 table=root/(mode+'-table.bin');p=subprocess.run([str(build/'preview_srgb_test'),str(table)],capture_output=True,text=True,timeout=60);assert p.returncode==0,p.stderr
 h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();symbols=subprocess.check_output(['nm','-S','--defined-only',str(build/'gpr_capture_app')],text=True);(root/(mode+'-symbols.txt')).write_text(symbols)
 rows.append(dict(mode=mode,macro=value,commands=commands,proof=json.loads(p.stdout),packed_table_sha256=h(table),benchmark_sha256=h(build/'preview_color_benchmark'),capture_sha256=h(build/'gpr_capture_app'),gamma_symbols=[s for s in symbols.splitlines() if 'srgb_table' in s and 'table' in s]));(root/'builds.json').write_text(json.dumps(rows,indent=2)+'\n');print(mode,'six tests and exhaustive gamma proof pass',rows[-1]['gamma_symbols'],flush=True)
