#!/usr/bin/env python3
"""Regenerate aggregate figures; requires matplotlib, no source photos."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parent
def read(name): return json.loads((root/(name+'.json')).read_text())
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
colors=('#0072B2','#E69F00','#009E73','#CC79A7')
fig,axes=plt.subplots(1,3,figsize=(14,4.5),layout='constrained')
groups=[[(f'mac-z8-{name}',f'Scene {name}') for name in ('0001','0067','5323','6693')],
        [('mac-x2d-3265','X2D scene 3265')],
        [('pi5-GP011728','GP011728'),('pi5-GPAB1094','GPAB1094')]]
titles=('45.7 MP lossless Z8 references','102.1 MP lossless X2D reference','12 MP camera-compressed replays')
for ax,group,title in zip(axes,groups,titles):
    for i,(name,label) in enumerate(group):
        report=read(name); rows=report['rows']
        x=[r['bits_per_pixel'] for r in rows]; y=[r['metrics']['active']['psnr_db'] for r in rows]
        ax.plot(x,y,'o--' if name.startswith('pi5') else 'o-',color=colors[i],label=label,markersize=4)
        for q in (0,3,5): ax.annotate('Q'+str(q),(x[q],y[q]),xytext=(4,4),textcoords='offset points',fontsize=7)
    ax.set_title(title,fontsize=11); ax.set_xlabel('File bits / stored Bayer sample')
    ax.set_ylabel('Active-area PSNR (dB)'); ax.grid(alpha=.2); ax.legend(fontsize=8)
fig.suptitle('Stock VC-5 still presets Q0–Q5 · no CNN',fontsize=14)
for suffix in ('svg','png'): fig.savefig(root.parent/f'stock-still-rate-distortion.{suffix}',dpi=160)
plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
for i,name in enumerate(('GP011728','GPAB1094')):
    rows=read('pi5-'+name)['rows']
    for ax,key in zip(axes,('encode_process_median_s','encode_workflow_median_s')):
        ax.plot(range(6),[r[key]*1000 for r in rows],'o-',color=colors[i],label=name,markersize=4)
for ax,title in zip(axes,('Fresh SDK process: input + encode + GPR write','Validated/hashed workflow: before publication')):
    ax.set_title(title,fontsize=10); ax.set_xlabel('Stock preset'); ax.set_ylabel('Milliseconds')
    ax.set_xticks(range(6),['Q'+str(q) for q in range(6)]); ax.grid(alpha=.2); ax.legend(fontsize=8)
fig.suptitle('Pi 5 · 4096×3072 · medians of 3 fresh processes · no final fsync',fontsize=12)
for suffix in ('svg','png'): fig.savefig(root.parent/f'stock-still-pi5-presets.{suffix}',dpi=160)
