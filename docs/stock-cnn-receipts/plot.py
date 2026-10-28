#!/usr/bin/env python3
"""Regenerate aggregate figures; no source photographs or weights required."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['svg.hashsalt']='stock-cnn-quality-v1'
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parent
summary=json.loads((root/'summary.json').read_text())
rows=summary['rows']
fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
sizes=[r['mean_gpr_bytes']/1e6 for r in rows]
for name,label,style in [('stock_active_psnr_db','Stock decode','o-'),('restored_active_psnr_db','Optional 1x CNN','s--')]:
    axes[0].plot(sizes,[r[name] for r in rows],style,label=label)
axes[0].set(xlabel='Mean compressed GPR size (decimal MB)',ylabel='Active-area RAW PSNR (dB)',title='Four lossless Nikon 45.7 MP references')
axes[0].legend(); axes[0].grid(alpha=.2)
for frame in ('0001','0067','5323','6693'):
    report=json.loads((root/f'z8-{frame}.json').read_text())
    axes[1].plot(range(6),[r['active_psnr_delta_db'] for r in report['rows']],'o-',label=f'Z8Z_{frame}')
axes[1].axhline(0,color='black',linewidth=.8)
axes[1].set(xlabel='Stock preset',ylabel='CNN minus stock PSNR (dB)',title='Scene-specific gains and regressions',xticks=range(6))
axes[1].legend(fontsize=8); axes[1].grid(alpha=.2)
fig.suptitle('Existing stock-Q3 1x checkpoint — experimental, no quality approval',fontsize=12)
for ext in ('svg','png'):
    destination=root.parent/f'stock-cnn-quality.{ext}'
    fig.savefig(destination,dpi=160,metadata={'Date':None} if ext=='svg' else None)
    if ext=='svg':
        destination.write_text('\n'.join(line.rstrip() for line in destination.read_text().splitlines())+'\n')
