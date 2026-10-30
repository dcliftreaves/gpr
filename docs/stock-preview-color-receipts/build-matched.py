from pathlib import Path
import hashlib,json,shlex,shutil,subprocess
root=Path('/mnt/ssd/gpr_work/stock-preview-color-prototype-20261030');main=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime');out=root/'matched-final-benchmark';out.mkdir(exist_ok=True);flags={}
for line in (main/'build-runtime/source/lib/gpr_video/CMakeFiles/gpr_preview.dir/flags.make').read_text().splitlines():
 if line.startswith(('CXX_DEFINES =','CXX_INCLUDES =','CXX_FLAGS =')):
  key,value=line.split('=',1);flags[key.strip()]=shlex.split(value.strip())
common=['/usr/bin/c++']+flags['CXX_DEFINES']+flags['CXX_INCLUDES']+flags['CXX_FLAGS'];commands=[]
def run(command,name):
 commands.append(command);p=subprocess.run(command,capture_output=True,text=True,timeout=120);(out/(name+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
obj=out/'gpr_preview_queue.cpp.o';run(common+['-c',str(root/'previous-queue.cpp'),'-o',str(obj)],'previous-compile');oldlib=out/'libgpr_preview.a';newlib=main/'build-runtime/source/lib/gpr_video/libgpr_preview.a';shutil.copyfile(newlib,oldlib);run(['gcc-ar','r',str(oldlib),str(obj)],'previous-archive');run(['gcc-ranlib',str(oldlib)],'previous-index')
client=root/'tests/preview_color_benchmark.cpp';client_obj=out/'client.o';run(common+['-c',str(client),'-o',str(client_obj)],'client-compile');template=json.loads((root/'final-benchmark/build.json').read_text())['link'];rows=[]
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for mode in ['previous','final']:
 cmd=[]
 for index,arg in enumerate(template):
  if arg.endswith('/benchmark.o'):arg=str(client_obj)
  elif index and template[index-1]=='-o':arg=str(out/mode)
  elif arg==str(newlib) and mode=='previous':arg=str(oldlib)
  cmd.append(arg)
 run(cmd,mode+'-link');rows.append(dict(mode=mode,path=str(out/mode),binary_sha256=h(out/mode),libraries={p:h(Path(p)) for p in cmd if p.endswith('.a')}))
assert h(root/'previous-queue.cpp')=='5924cf424fe7cd2c384f097a59f5e9a6cde92e2ba484c2a2fcb2d8a359313581'
metadata=dict(source_commit='f197f09',previous_queue_sha256=h(root/'previous-queue.cpp'),client_sha256=h(client),flags=flags,commands=commands,builds=rows,scope='same final archives/compiler flags/client object; only queue translation unit replaced with exact 7f9215e source for previous control')
(out/'build.json').write_text(json.dumps(metadata,indent=2)+'\n');print('Built matched clients with only the queue translation unit differing.')
