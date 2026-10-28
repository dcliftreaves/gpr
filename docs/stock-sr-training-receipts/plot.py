#!/usr/bin/env python3
"""Regenerate training/evaluation figures from numeric receipts only."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['svg.hashsalt']='stock-sr-training-v1'
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parent
training=json.loads((root/'training.json').read_text())
summary=json.loads((root/'summary.json').read_text())
fig,axes=plt.subplots(1,3,figsize=(13,4),layout='constrained')
history=training['history']
axes[0].plot([0]+[r['step'] for r in history],[0]+[r['delta_vs_bicubic_db'] for r in history],'o-',markersize=3)
axes[0].axvline(training['best_step'],color='gray',linestyle='--',label='Selected step')
axes[0].set(xlabel='Training step',ylabel='Δ PSNR versus bicubic (dB)',title='Validation patches only')
axes[0].legend(fontsize=8)
rows=summary['rows']
axes[1].bar([r['frame'] for r in rows],[r['delta_db'] for r in rows],color='#237b9e')
axes[1].set(xlabel='Final reference frame',ylabel='Δ PSNR versus bicubic (dB)',title='Frozen candidate, full frames')
keys=('active','detail_top_decile','shadow_bottom_decile','highlight_top_decile')
values=[summary['sections'][key]['delta_db'] for key in keys]
axes[2].bar(['Active','Detail','Shadow','Highlight'],values,color=['#a33c35' if x<0 else '#237b9e' for x in values])
axes[2].set(ylabel='ΔdB from scene-mean MSE',title='Overall gain hides shadow regression')
axes[2].tick_params(axis='x',rotation=20)
for axis in axes:
    axis.axhline(0,color='black',linewidth=.7)
    axis.grid(axis='y',alpha=.2);axis.set_axisbelow(True)
fig.suptitle('Fresh stock-Q3 2x candidate — research only, no quality approval',fontsize=12)
for extension in ('svg','png'):
    destination=root.parent/f'stock-sr-training.{extension}'
    fig.savefig(destination,dpi=160,metadata={'Date':None} if extension=='svg' else None)
    if extension=='svg':destination.write_text('\n'.join(line.rstrip() for line in destination.read_text().splitlines())+'\n')
