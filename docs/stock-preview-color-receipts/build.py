from pathlib import Path
import hashlib,json,subprocess
root=Path('/mnt/ssd/gpr_work/stock-preview-color-prototype-20261030');rows=[]
for mode,color,diagnostic in [('diagnostic-dense',0,1),('diagnostic-colored',1,1),('baseline',0,0),('colored',1,0)]:
 build=root/('build-'+mode)
 flags=f'-DGPR_PREVIEW_PLANE_COLOR={color} -DGPR_PREVIEW_LAYOUT_DIAGNOSTIC={diagnostic}'
 commands=[['cmake','-S',str(root),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_CXX_FLAGS='+flags,'-DGPR_BUILD_SDK=OFF','-DGPR_BUILD_STILL_APPS=OFF','-DGPR_ENABLE_VIDEO=ON','-DGPR_BUILD_CAPTURE_APP=ON','-DGPR_BUILD_PREVIEW_TOOLS=ON','-DGPR_BUILD_PREVIEW_TESTS=ON'],['cmake','--build',str(build),'--target','gpr_capture_app','preview_wavelet_queue_test','preview_queue_test','-j','4'],['ctest','--test-dir',str(build),'-R','preview_wavelet_queue|preview_queue$','--output-on-failure']]
 for name,cmd in zip(['configure','build','tests'],commands):
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=300);(root/(mode+'-'+name+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,(mode,name,p.stdout[-2000:],p.stderr[-2000:])
 rows.append(dict(mode=mode,color=color,diagnostic=diagnostic,commands=commands,binary_sha256=hashlib.sha256((build/'gpr_capture_app').read_bytes()).hexdigest()))
 (root/'builds.json').write_text(json.dumps(rows,indent=2)+'\n');print(mode,'built; queue ownership/bounds/pixels checks passed',flush=True)
