from pathlib import Path
import hashlib,json,subprocess
root=Path('/mnt/ssd/gpr_work/stock-entropy64-prototype-20261030');rows=[]
for mode,variant in [('baseline',0),('full64',1),('hybrid',2)]:
 build=root/('build-'+mode)
 configure=['cmake','-S',str(root),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_FLAGS=-DGPR_ENTROPY64_VARIANT='+str(variant),'-DGPR_BUILD_SDK=OFF','-DGPR_BUILD_STILL_APPS=OFF','-DGPR_ENABLE_PARALLEL_CHANNELS=ON','-DGPR_ENABLE_VIDEO=ON','-DGPR_BUILD_PREVIEW_TOOLS=ON','-DGPR_BUILD_CAPTURE_APP=ON','-DGPR_BUILD_CODEC_TESTS=ON']
 commands=[configure,['cmake','--build',str(build),'--target','vc5_encoder_app','gpr_capture_app','encoder_preview_probe','-j','4'],['ctest','--test-dir',str(build),'-R','encoder_preview_','--output-on-failure']]
 for name,cmd in zip(['configure','build','tests'],commands):
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=300);(root/(mode+'-v2-'+name+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,(mode,name,p.stdout[-4000:],p.stderr[-4000:])
 rows.append(dict(mode=mode,commands=commands,encoder_sha256=hashlib.sha256((build/'source/app/vc5_encoder_app/vc5_encoder_app').read_bytes()).hexdigest(),capture_sha256=hashlib.sha256((build/'gpr_capture_app').read_bytes()).hexdigest()))
 (root/'builds-v2.json').write_text(json.dumps(rows,indent=2)+'\n');print(mode,'built and four probe/matrix tests passed',flush=True)
