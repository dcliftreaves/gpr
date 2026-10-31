"""Research-only historical SR tiler and deterministic count-domain correction."""
import time
import numpy as np
import torch

PEAK=16383

def coordinates(x,y,h,w,full_h,full_w):
    xx=(np.arange(w,dtype=np.float32)+float(x))/max(1,full_w-1)*2-1
    yy=(np.arange(h,dtype=np.float32)+float(y))/max(1,full_h-1)*2-1
    return np.stack([np.broadcast_to(xx[None,:],(h,w)),np.broadcast_to(yy[:,None],(h,w))])

def tiled(model,planes,device,tile=512,overlap=32,reflect=False,halo=32):
    """Keep original tile origins/crops; extend only actual frame-edge tiles."""
    assert planes.ndim==3 and planes.shape[0]==4
    _,h,w=planes.shape
    assert 0<=overlap<tile<=min(h,w) and halo<min(h,w)
    def starts(n):
        result=list(range(0,max(1,n-tile+1),tile-overlap))
        if result[-1]!=n-tile:result.append(n-tile)
        return result
    ys=starts(h);xs=starts(w);out=np.empty((4,h*2,w*2),dtype='<u2');covered=np.zeros((h*2,w*2),dtype=bool)
    started=time.perf_counter();count=0
    with torch.inference_mode():
        for yi,y in enumerate(ys):
            for xi,x in enumerate(xs):
                top=halo if reflect and y==0 else 0;bottom=halo if reflect and y+tile==h else 0
                left=halo if reflect and x==0 else 0;right=halo if reflect and x+tile==w else 0
                raw=planes[:,y:y+tile,x:x+tile].astype(np.float32)*(1./PEAK)
                if top or bottom or left or right:raw=np.pad(raw,((0,0),(top,bottom),(left,right)),mode='reflect')
                coords=coordinates(x-left,y-top,raw.shape[1],raw.shape[2],h,w)
                inputs=torch.from_numpy(np.concatenate([raw,coords],axis=0)[None]).to(device)
                pred=model(inputs)[0].cpu().numpy()[:,top*2:(top+tile)*2,left*2:(left+tile)*2]
                counts=np.clip(pred*PEAK+.5,0,PEAK).astype('<u2')
                y0=0 if yi==0 else overlap//2;x0=0 if xi==0 else overlap//2
                y1=tile if yi==len(ys)-1 else tile-overlap//2;x1=tile if xi==len(xs)-1 else tile-overlap//2
                dest=(slice((y+y0)*2,(y+y1)*2),slice((x+x0)*2,(x+x1)*2))
                out[(slice(None),)+dest]=counts[:,y0*2:y1*2,x0*2:x1*2]
                covered[dest]=True;count+=1
    assert covered.all()
    return out,dict(tile=tile,overlap=overlap,reflect_frame_edges=reflect,halo=halo,tile_count=count,covered_all=True,inference_plus_copy_s=time.perf_counter()-started)

def correction(base,pred,alpha,ramps):
    """Reference-free, float64 postblend of independently rounded RAW counts."""
    b=base.astype(np.float64);gain=float(alpha)
    if ramps is not None:
        a,c,d,e=ramps;x=b/PEAK
        gain=gain*np.clip((x-a)/(c-a),0,1)*np.clip((e-x)/(e-d),0,1)
    return np.clip(np.floor(b+gain*(pred.astype(np.float64)-b)+.5),0,PEAK).astype('<u2')

def interleave(planes):
    _,h,w=planes.shape;out=np.empty((h*2,w*2),dtype='<u2')
    for c in range(4):out[c//2::2,c%2::2]=planes[c]
    return out
