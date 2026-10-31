from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent
rows=json.loads((root/"trace-file/correlation.json").read_text())
traces=json.loads((root/"trace-file/traces.json").read_text())
frames=[r["index"] for r in rows]
fig,axes=plt.subplots(2,1,figsize=(11,6),sharex=True,layout="constrained")
axes[0].plot(frames,[r["encode_ms"] for r in rows],label="Encode wall",color="#2463a5",lw=.9)
axes[0].plot(frames,[r["main_cpu_ms"] for r in rows],label="Calling thread CPU",color="#c26820",lw=.8,alpha=.8)
axes[0].axhline(50,color="#a43737",ls="--",lw=.9,label="50 ms frame period")
axes[0].set_ylabel("Full encoder call (ms)")
axes[0].set_ylim(15,72)
axes[0].legend(loc="upper left",ncol=3,fontsize=8)
axes[0].set_title("File-logged diagnostic: 600 exact frames and previews\nInstrumentation overhead included; sustained timing gate fails",fontsize=11)
a=[(r["workers"][0]["wall"]-r["workers"][0]["cpu"])*1000 for r in traces]
b=[max((w["wall"]-w["cpu"])*1000 for w in r["workers"][1:]) for r in traces]
axes[1].plot(frames,b,color="#777777",lw=.7,alpha=.7,label="Largest other-worker gap")
axes[1].plot(frames,a,color="#2463a5",lw=.9,label="Channel 0 / CPU 0")
for i in [141,470]:
 j=frames.index(i)
 axes[1].annotate(str(i),xy=(i,a[j]),xytext=(8,2),textcoords="offset points",fontsize=8)
axes[1].set_ylabel("Worker wall minus CPU (ms)")
axes[1].set_xlabel("Recorded frame index")
axes[1].set_ylim(-.5,35)
axes[1].legend(loc="upper left",fontsize=8)
for ax in axes:ax.grid(alpha=.2);ax.spines[["top","right"]].set_visible(False)
fig.savefig(root/"file-trace.png",dpi=160)
