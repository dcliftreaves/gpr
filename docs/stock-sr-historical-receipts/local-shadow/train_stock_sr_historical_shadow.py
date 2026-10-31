"""Frozen full-width historical architecture comparison on matched stock pairs."""
from pathlib import Path
import hashlib,importlib.util,json,sys,time,datetime,shutil
import numpy as np
import torch
import torch.nn.functional as F
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
sys.path.insert(0,str(REPO/'tools'))
import train_stock_sr as metrics
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_shadow_20261030')
PARENT_RUN=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_recipe_20261030')
OLD=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_old_selected_transfer_20261030')
PARENT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030')
CHECKPOINT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_cnn_hardtile_gate_aligned_20260624/interp_step1_to_balanced_step200/q4t2_coord_detail_balanced_step001_to_step200_alpha0p5.pt')
HISTORICAL=Path('/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_cnn_hardtile_gate_aligned_20260624/hardtile_coord_detail_gw4_lap005_phase01_s400/q4t2_coord_detail_hardtile_gw4_lap005_phase01_s400.pt.json')
TRAINER=Path('/Volumes/OWC_8TB/gpr_work/worktrees/gpr_clean_sanitized_20260604/tools/cnn/train_mission1_sr.py')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):p.write_text(json.dumps(value,indent=2)+'\n')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def run():
    ROOT.mkdir(exist_ok=False)
    for path in (OLD/'mission1_sr_models.py',OLD/'mission1_sr_runtime.py',TRAINER):shutil.copy2(path,ROOT/path.name)
    shutil.copy2(Path(__file__),ROOT/Path(__file__).name)
    sys.path.insert(0,str(ROOT))
    models=module('historical_models',ROOT/'mission1_sr_models.py');runtime=module('historical_runtime',ROOT/'mission1_sr_runtime.py');losses=module('historical_losses',ROOT/TRAINER.name)
    checkpoint=torch.load(CHECKPOINT,map_location='cpu',weights_only=True)
    assert sha(CHECKPOINT)=='791628778f74b13542677edeb5de7934b88d274531a8ec1755d8cf3d6388fb07'
    assert checkpoint['config']==dict(architecture='coord_detail_preclean_adapter_pixelshuffle',width=96,depth=6,residual_scale=.3,coordinate_channels=True)
    endpoints=[torch.load(Path(checkpoint['interpolation'][key]),map_location='cpu',weights_only=True)['model'] for key in ('from','to')]
    assert all(torch.equal((endpoints[0][key]+endpoints[1][key])*.5,value) for key,value in checkpoint['model'].items())
    historical=json.loads(HISTORICAL.read_text());loss_keys=('gradient_weight','laplacian_weight','detail_phase_weight','detail_phase_threshold','low_clean_aux_weight','low_clean_detail_aux_weight','low_clean_detail_threshold','loss')
    settings={k:historical[k] for k in loss_keys}
    assert settings==dict(gradient_weight=4.,laplacian_weight=.05,detail_phase_weight=.1,detail_phase_threshold=2.,low_clean_aux_weight=.02,low_clean_detail_aux_weight=.03,low_clean_detail_threshold=2.,loss='charbonnier')
    parent=json.loads((PARENT/'protocol.json').read_text());dataset=Path(parent['dataset']);info=json.loads((dataset/'dataset.json').read_text())
    assert info['complete'] and sha(dataset/'inputs.npy')==parent['dataset_input_sha256'] and sha(dataset/'targets.npy')==parent['dataset_target_sha256']
    inputs=np.load(dataset/'inputs.npy',mmap_mode='r');targets=np.load(dataset/'targets.npy',mmap_mode='r')
    coordinates=np.zeros((len(inputs),2,128,128),np.float32);train=[];val=[];groups={}
    coordinate_checks=[]
    for source in info['sources']:
        if source['split']=='test':assert source['patch_count']==0 and source['patch_start'] is None;continue
        indices=list(range(source['patch_start'],source['patch_start']+source['patch_count']))
        if source['split']=='train':train.append(indices)
        else:val.extend(indices);groups.update({i:source['group'] for i in indices})
        for index,(y,x) in zip(indices,source['low_plane_yx']):
            coords=runtime.coord_channels(x0=x,y0=y,tile=128,low_plane_w=source['width']//4,low_plane_h=source['height']//4)
            # Independent scalar endpoints confirm global, not patch-local coordinates.
            expected=np.array([2*x/(source['width']//4-1)-1,2*(x+127)/(source['width']//4-1)-1,2*y/(source['height']//4-1)-1,2*(y+127)/(source['height']//4-1)-1])
            actual=np.array([coords[0,0,0],coords[0,0,-1],coords[1,0,0],coords[1,-1,0]])
            assert np.max(abs(expected-actual))<3e-7
            coordinates[index]=coords
        coordinate_checks.append(dict(group=source['group'],split=source['split'],patches=len(indices),full_low_plane_wh=[source['width']//4,source['height']//4]))
    assert len(train)==8 and sum(map(len,train))==512 and len(val)==128
    protocol=dict(schema='gpr.stock_sr_historical_shadow_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        driver_sha256=sha(Path(__file__)),old_model_source_sha256=sha(ROOT/'mission1_sr_models.py'),old_runtime_source_sha256=sha(ROOT/'mission1_sr_runtime.py'),located_trainer_sha256=sha(ROOT/TRAINER.name),
        historical_receipt_sha256=sha(HISTORICAL),historical_receipt_settings=settings,registry_gradient_weight=.4,training_receipt_gradient_weight=4.,
        discrepancy='Registry and actual selected-endpoint training receipt differ; use receipt 4.0, not registry 0.4. Historical receipt does not bind trainer source hash, so this is a frozen reconstruction, not bit-identical original training.',
        initial_checkpoint_sha256=sha(CHECKPOINT),initial_interpolation_reconstructed_exactly=True,initial_endpoint_sha256={key:sha(Path(checkpoint['interpolation'][key])) for key in ('from','to')},
        config=checkpoint['config'],parameters=633444,initializations=['control','shadow_hinge'],seed=20261105,batch=8,steps=400,checkpoint_steps=[1,200,400],learning_rate=.00003,weight_decay=.0001,shadow_hinge_weight=.02,shadow_ratio_margin=.98,parent_training_sha256=sha(PARENT_RUN/'training.json'),continuation_checkpoint_sha256=sha(PARENT_RUN/'pretrained/step-400.pt'),
        losses=settings,norm=16383,training_core_high=[64,192],auxiliary_core_low=[32,96],
        auxiliary_target='Exact stock task same-site 2x2 mean of clean high target with integer half-up rounding; differs from original Gaussian-area task',
        dataset_sha256=sha(dataset/'dataset.json'),input_sha256=parent['dataset_input_sha256'],target_sha256=parent['dataset_target_sha256'],coordinate_checks=coordinate_checks,
        sampling='One patch per eight training sources each step; same RNG sequence for both initializations',
        candidates='Per initialization: step200, step400, weight interpolation step1-to200 alpha0.5, step1-to400 alpha0.5; no output-strength sweep',
        patch_guard='Unchanged every pooled/source-group overall/shadow/highlight/detail MSE nonincrease versus current bicubic and strict pooled improvement',
        full_guard='Every patch-qualified candidate on all four complete validation images; per-image RAW active/shadow/highlight/detail nonregression and strict pooled active improvement; freeze before historical final evaluation',
        final_reference_pixels_used=False,quality_approval=False,
        limitations=['Small reused Nikon stock training corpus, not full old camera+Nikon recipe','Validation held out from current updates only; overlap with historical pretraining not excluded','Historical final references reused, not newly blind','One seed and new explicitly chosen learning rate; old receipt omits learning rate','Old bilinear-base architecture preserved; current comparison baseline remains bicubic','No native/backend/temporal/visual promotion from patch metrics'])
    protocol['sampling']='One patch per eight training sources per step; identical sequence in control and hinge continuation'
    protocol['continuation']='Both cases start at original pretrained-case step400; fresh AdamW at3e-5; only hinge case adds0.02*mean(relu(training-shadow-MSE/max(1,bicubic-shadow-MSE)-0.98))'
    protocol['training_masks']='Per-training-patch reference shadow decile only; nontraining masks zero; no reference pixels or masks needed for inference'
    protocol['limitations'].append('Validation shadow failures motivate this separate follow-up; no historical final pixels select or tune the penalty')
    save(ROOT/'protocol.json',protocol)
    save(ROOT/'historical-receipt-extract.json',dict(settings=settings,source_sha256=sha(HISTORICAL),source_file=HISTORICAL.name,selected_endpoints=checkpoint['interpolation']))
    torch.set_num_threads(4);core=slice(64,192);lowcore=slice(32,96);device=torch.device('mps')
    def tensors(indices):
        counts=torch.from_numpy(np.asarray(targets[indices],dtype=np.float32)).to(device)
        raw=torch.from_numpy(np.asarray(inputs[indices],dtype=np.float32)/16383).to(device)
        coords=torch.from_numpy(coordinates[indices]).to(device)
        clean=(F.avg_pool2d(counts,2)+.5).floor()/16383
        return torch.cat([raw,coords],1),counts/16383,clean
    def evaluate(model):
        model.eval();totals={}
        with torch.inference_mode():
            for start in range(0,len(val),8):
                indices=val[start:start+8];x,y,_=tensors(indices)
                if model is None:prediction=F.interpolate(x[:,:4],scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1)
                else:prediction=model(x)
                prediction=np.clip(prediction[:,:,core,core].cpu().numpy()*16383+.5,0,16383).astype('<u2')
                for index,pred in zip(indices,prediction):
                    ref=np.asarray(targets[index,:,core,core],dtype=np.float64);regions=metrics.region_totals(ref,pred.astype(np.float64)-ref)
                    for group in ('pooled','group:'+groups[index]):
                        dest=totals.setdefault(group,{})
                        for key,(s,n) in regions.items():a,b=dest.get(key,(0.,0));dest[key]=(a+s,b+n)
        return {g:{r:s/n for r,(s,n) in regions.items()} for g,regions in totals.items()}
    shadow_masks=np.zeros((len(inputs),4,128,128),np.uint8)
    shadow_norm=np.ones(len(inputs),np.float64)
    with torch.inference_mode():
        for indices in train:
            for start in range(0,len(indices),8):
                idx=indices[start:start+8];x,y,_=tensors(idx)
                base=F.interpolate(x[:,:4],scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1)
                base=np.clip(base[:,:,core,core].cpu().numpy()*16383+.5,0,16383).astype('<u2')
                for i,b in zip(idx,base):
                    reference=np.asarray(targets[i,:,core,core],dtype=np.float64)
                    mask=reference<=np.percentile(reference,10);shadow_masks[i]=mask
                    shadow_norm[i]=max(1.,float(np.mean((b.astype(np.float64)[mask]-reference[mask])**2)))
    nontraining=[i for i in range(len(inputs)) if all(i not in indices for indices in train)]
    assert not np.any(shadow_masks[nontraining]) and np.all(shadow_norm[nontraining]==1)
    np.save(ROOT/'training-shadow-masks.npy',shadow_masks);np.save(ROOT/'training-shadow-norm.npy',shadow_norm)
    save(ROOT/'shadow-weight-audit.json',dict(complete=True,masks_sha256=sha(ROOT/'training-shadow-masks.npy'),norm_sha256=sha(ROOT/'training-shadow-norm.npy'),training_patches=512,nontraining_patches=len(nontraining),nontraining_masks_zero=True,nontraining_norm_unset=True,denominator_floor_counts_squared=1.,mse_min=float(shadow_norm.min()),mse_max=float(shadow_norm.max())))

    baseline=None
    report=dict(schema='gpr.stock_sr_historical_shadow.v1',complete=False,quality_approval=False,protocol_sha256=sha(ROOT/'protocol.json'),cases=[],torch=torch.__version__)
    started=time.perf_counter()
    for initialization in protocol['initializations']:
        torch.manual_seed(protocol['seed']);rng=np.random.default_rng(protocol['seed']);model=models.make_model_from_config(protocol['config'])
        assert sum(p.numel() for p in model.parameters())==633444
        model.load_state_dict(torch.load(PARENT_RUN/'pretrained/step-400.pt',map_location='cpu',weights_only=True)['model'],strict=True)
        model.to(device);optimizer=torch.optim.AdamW(model.parameters(),lr=.00003,weight_decay=.0001)
        if baseline is None:
            # Use a plain callable wrapper to keep baseline handling separate.
            class Bicubic(torch.nn.Module):
                def forward(self,x):return F.interpolate(x[:,:4],scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1)
            baseline=evaluate(Bicubic())
            assert baseline==json.loads((PARENT/'selection.json').read_text())['baseline_regions']
            report['baseline']=baseline
        row=dict(initialization=initialization,initial_metrics=evaluate(model),checkpoints=[],candidates=[]);report['cases'].append(row)
        directory=ROOT/initialization;directory.mkdir();states={}
        for step in range(1,401):
            model.train();indices=[int(rng.choice(source)) for source in train];x,y,clean=tensors(indices);optimizer.zero_grad(set_to_none=True)
            pred=model(x)[:,:,core,core];target=y[:,:,core,core]
            base_loss=losses.robust_l1(pred,target,'charbonnier')
            grad=losses.robust_l1(pred[:,:,:,1:]-pred[:,:,:,:-1],target[:,:,:,1:]-target[:,:,:,:-1],'charbonnier')+losses.robust_l1(pred[:,:,1:,:]-pred[:,:,:-1,:],target[:,:,1:,:]-target[:,:,:-1,:],'charbonnier')
            lap=losses.robust_l1(losses.laplacian(pred),losses.laplacian(target),'charbonnier')
            phase=losses.detail_phase_loss(pred,target,'charbonnier',threshold_counts=2.)
            low=model.clean_low(x)[:,:,lowcore,lowcore];lowtarget=clean[:,:,lowcore,lowcore]
            aux=losses.robust_l1(low,lowtarget,'charbonnier');auxdetail=losses.detail_phase_loss(low,lowtarget,'charbonnier',threshold_counts=2.)
            loss=base_loss+4*grad+.05*lap+.1*phase+.02*aux+.03*auxdetail
            if initialization=='shadow_hinge':
                mask=torch.from_numpy(shadow_masks[indices].astype(np.float32)).to(device)
                mse=((pred-target).square()*16383**2*mask).sum((1,2,3))/mask.sum((1,2,3))
                norm=torch.from_numpy(shadow_norm[indices].astype(np.float32)).to(device)
                loss=loss+.02*torch.relu(mse/norm-.98).mean()
            assert torch.isfinite(loss).item();loss.backward();optimizer.step()
            if step in protocol['checkpoint_steps']:
                states[step]={k:v.detach().cpu().clone() for k,v in model.state_dict().items()};path=directory/f'step-{step}.pt'
                torch.save(dict(model=states[step],config=protocol['config'],step=step,protocol_sha256=sha(ROOT/'protocol.json'),quality_approval=False),path)
                row['checkpoints'].append(dict(step=step,sha256=sha(path),loss=float(loss.item()),elapsed_s=time.perf_counter()-started));save(ROOT/'training.json',report)
                print(json.dumps(dict(initialization=initialization,step=step,loss=float(loss.item()),elapsed_s=time.perf_counter()-started)),flush=True)
        for step in (200,400):
            for interpolation in (False,True):
                state=states[step] if not interpolation else {k:(states[1][k]+v)*.5 for k,v in states[step].items()}
                name=f'step-{step}'+('-weight-interp-half' if interpolation else '')
                path=directory/(name+'.pt');torch.save(dict(model=state,config=protocol['config'],quality_approval=False),path)
                model.load_state_dict(state,strict=True);scores=evaluate(model)
                regressions=[g+':'+r for g,regions in baseline.items() for r,value in regions.items() if scores[g][r]>value]
                eligible=not regressions and scores['pooled']['overall']<baseline['pooled']['overall']
                candidate=dict(name=initialization+'-'+name,path=str(path),checkpoint_sha256=sha(path),step=step,weight_interpolation=interpolation,metrics=scores,regressions=regressions,eligible=eligible,gain_db=metrics.delta(baseline['pooled']['overall'],scores['pooled']['overall']))
                row['candidates'].append(candidate);save(ROOT/'training.json',report);print(json.dumps(dict(candidate=candidate['name'],gain_db=candidate['gain_db'],eligible=eligible)),flush=True)
        del model,optimizer;torch.mps.empty_cache()
    report.update(complete=True,elapsed_s=time.perf_counter()-started);save(ROOT/'training.json',report)
    print(json.dumps(dict(complete=True,elapsed_s=report['elapsed_s'])),flush=True)
if __name__=='__main__':run()
