from pathlib import Path
import hashlib,json,subprocess
root=Path('/mnt/ssd/gpr_work/stock-zero-scan-prototype-20261030');h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();rows=[]
for mode,value in [('baseline',0),('word',1),('neon',2)]:
 build=root/('build-'+mode);commands=[['cmake','-S',str(root),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_FLAGS=-DGPR_ZERO_SCAN='+str(value),'-DGPR_BUILD_SDK=OFF','-DGPR_BUILD_STILL_APPS=OFF','-DGPR_ENABLE_VIDEO=ON','-DGPR_BUILD_CAPTURE_APP=ON','-DGPR_BUILD_PREVIEW_TOOLS=ON','-DGPR_BUILD_PREVIEW_TESTS=ON','-DGPR_BUILD_CODEC_TESTS=ON'],['cmake','--build',str(build),'-j4'],['ctest','--test-dir',str(build),'--output-on-failure']]
 for stage,command in zip(['configure','build','tests'],commands):
  p=subprocess.run(command,capture_output=True,text=True,timeout=300);(root/(mode+'-'+stage+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,(mode,stage,p.stdout[-2000:],p.stderr[-2000:])
 p=subprocess.run([str(build/'zero_scan_test')],capture_output=True,text=True,timeout=120);(root/(mode+'-proof.json')).write_text(p.stdout);assert p.returncode==0,p.stderr;proof=json.loads(p.stdout);assert proof['variant']==value and proof['cases']==674298 and proof['guard_pages'] and proof['all_prefixes_exact']
 symbols=subprocess.check_output(['nm','-S','--defined-only',str(build/'zero_scan_benchmark')],text=True);names=[s.split()[-1] for s in symbols.splitlines() if 'EncodeHighpassIncremental' in s];assert names
 for name in names:(root/(mode+'-'+name+'.asm')).write_text(subprocess.check_output(['objdump','-d','--disassemble='+name,str(build/'zero_scan_benchmark')],text=True))
 rows.append(dict(mode=mode,macro=value,commands=commands,proof=proof,benchmark_sha256=h(build/'zero_scan_benchmark'),capture_sha256=h(build/'gpr_capture_app'),source_sha256={n:h(root/n) for n in ['source/lib/vc5_encoder/encoder.c','source/lib/vc5_encoder/zero_scan.h','tests/zero_scan_test.c','tests/zero_scan_benchmark.c']},entropy_symbols=names));(root/'builds.json').write_text(json.dumps(rows,indent=2)+'\n');print(mode,'14 tests and 674298 prefix/guard cases PASS',flush=True)
