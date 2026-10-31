"""Recover archived calibration and build stock pairs without claiming fresh originals."""
from pathlib import Path
import collections,datetime,hashlib,json,shutil,subprocess,sys,struct
from fractions import Fraction
import numpy as np
import tifffile
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media,stock_still,stock_cnn_metadata,train_stock_sr
BASE=Path('/Volumes/OWC_8TB/gpr_work/artifacts')
ROOT=BASE/'stock_sr_mission_calibrated_20261031-metadata-v2'
PARAMS=BASE/'mission1_three_leaf_all42_gvid_20260623/review'
DIRECT=BASE/'mission1_sourcegpr_gvid_8k_sr_prores_review_20260621'
AUDIT=REPO/'docs/stock-sr-mission-source-receipts/audit.json'
GROUPS=REPO/'docs/stock-sr-mission-source-receipts/scene-groups.json'
SDK=REPO/'build-runtime/source/app/gpr_tools/gpr_tools'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n')
def main():
    ROOT.mkdir(exist_ok=False);shutil.copy2(Path(__file__),ROOT/Path(__file__).name)
    old=json.loads(AUDIT.read_text());groups=json.loads(GROUPS.read_text());by={r['stem']:r for r in old['archived_references']};assert len(by)==42
    direct={p.stem.split('_')[-1]:p for p in (DIRECT/'params').glob('*.txt')};assert len(direct)==10
    p=dict(schema='gpr.stock_sr_mission_calibrated_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),driver_sha256=sha(Path(__file__)),source_audit_sha256=sha(AUDIT),scene_groups_sha256=sha(GROUPS),sdk_sha256=sha(SDK),enum_source_sha256=sha(REPO/'source/lib/gpr_sdk/public/gpr_tuning_info.h'),sdk_pixel_format_2='RGGB14',
        helper_source_sha256={n:sha(REPO/'tools'/n) for n in ['train_stock_sr.py','stock_still.py','raw_media.py','stock_cnn_metadata.py']},
        archive_params={r['stem']:dict(path=str(PARAMS/(r['stem']+'_params.json')),sha256=sha(PARAMS/(r['stem']+'_params.json'))) for r in groups['sources']},direct_params={s:dict(path=str(f),sha256=sha(f)) for s,f in direct.items()},
        patch_plane_pixels=128,training_patches_per_source=32,validation_patches_per_source=32,seed=20261107,stock_quality=3,output_scale=2,
        source_contract='Cached historical SDK camera-GPR count references plus recovered per-frame archived parameters; not freshly decoded originals or lossless sensor truth. New uncompressed DNG packaging checked independently; ten separate source-GPR parameter archives corroborate core calibration.',
        split='Preserve previous conservative venue split:28playground train,6home validation,8lake historical-test. Final/test counts hashed only; no final/test DNG packaging or patch extraction.',
        simulation='Same-site integer half-up 2x2 average, then ACTUAL stockQ3 encode/decode in original count domain. Sensor calibration retained; normalization only downstream of actual codec.',
        restored_archive_fields='BaselineExposure and AnalogBalance via typed metadata carrier because legacy SDK profile struct omits them; verify WB/matrices/exposure/balance numerically against each archive before pairs',
        metadata_checks=['Stem, archived timestamp and ISO correspond; full geometry/pixel-format/black-white valid','All10 direct-source params tuning/profile dictionaries equal recovered42 archive','Independent TIFF vs cached counts, current SDK source re-decode and metadata pixel hash; no image transforms','Supported low-to-high calibration exact after simulation except explicit opaque XMP omission'],quality_approval=False)
    save(ROOT/'protocol.json',p);root=ROOT/'dataset';root.mkdir()
    count=sum(0 if r['split']=='test' else 32 for r in groups['sources']);assert count==1088
    inputs=np.lib.format.open_memmap(root/'inputs.npy',mode='w+',dtype='<u2',shape=(count,4,128,128));targets=np.lib.format.open_memmap(root/'targets.npy',mode='w+',dtype='<u2',shape=(count,4,256,256))
    report=dict(schema='gpr.stock_sr_dataset.v1',complete=False,protocol_sha256=sha(ROOT/'protocol.json'),seed=p['seed'],patch_plane_pixels=128,input_shape=[count,4,128,128],target_shape=[count,4,256,256],dtype='<u2',cfa='RGGB',sample_bits=14,stock_quality=3,output_scale=2,source_contract=p['source_contract'],split_contract=p['split'],sources=[])
    metadata=dict(schema='gpr.stock_sr_mission_calibration_audit.v1',complete=False,protocol_sha256=sha(ROOT/'protocol.json'),original_sources_freshly_decoded=False,rows=[])
    rng=np.random.default_rng(p['seed']);cursor=0
    for index,source in enumerate(groups['sources']):
        stem=source['stem'];prior=by[stem];raw=Path(source['raw_path']);assert sha(raw)==source['raw_sha256']==prior['raw_sha256']
        params_path=PARAMS/(stem+'_params.json');params=json.loads(params_path.read_text());assert sha(params_path)==p['archive_params'][stem]['sha256']
        exif=params['exif_info'];tuning=params['tuning_info'];profile=params['profile_info']
        dt=datetime.datetime.strptime(exif['date_time_original'],'%Y-%m-%d %H:%M:%S').strftime('%Y:%m:%d %H:%M:%S')
        assert dt==prior['recorded_datetime'] and int(exif['iso_speed_rating'])==int(prior['recorded_iso']) and stem+'.GPR' in exif['image_description']
        assert [params['input_width'],params['input_height'],params['input_pitch']]==[8192,6144,16384] and tuning['pixel_format']==2
        assert set(tuning['static_black_level'].values())=={16} and set(tuning['dgain_saturation_level'].values())=={16383}
        assert set(tuning['gain_map'])=={'size','channel_0','channel_1','channel_2','channel_3'}
        phases=[]
        for ch in range(4):
            gain=tuning['gain_map']['channel_'+str(ch)];area=gain['area'];assert area['bottom']==6144 and area['right']==8192 and area['row_pitch']==area['col_pitch']==2
            phases.append((area['top'],area['left']));assert len(gain['values'])==gain['points']['h']*gain['points']['v']
        assert set(phases)=={(0,0),(0,1),(1,0),(1,1)}
        corroborated=False
        if stem in direct:
            d=json.loads(direct[stem].read_text());assert d['tuning_info']==tuning and d['profile_info']==profile;corroborated=True
        m=dict(stem=stem,split=source['split'],group=source['group'],raw_sha256=sha(raw),params_sha256=sha(params_path),identity_fields_correspond=True,archived_cfa='RGGB',black_level=[16]*4,white_level=16383,wb_gains=tuning['wb_gains'],color_matrix_1=profile['color_matrix_1'],color_matrix_2=profile['color_matrix_2'],baseline_exposure=profile['baseline_exposure'],gainmap_phases=phases,direct_source_params_corroborated=corroborated)
        metadata['rows'].append(m)
        row=dict(stem=stem,path=str(raw),sha256=sha(raw),group=source['group'],split=source['split'],width=8192,height=6144,archived_raw_sha256=sha(raw),archived_params_sha256=sha(params_path),archived_metadata_only=True,black_level=[16.]*4,white_level=16383,wb_gains=tuning['wb_gains'])
        report['sources'].append(row)
        if source['split']=='test':row.update(patch_start=None,patch_count=0);continue
        work=root/f'source-{index:03d}';work.mkdir();dng=work/'reference.dng'
        command=[str(SDK),'-i',str(raw),'-a',str(params_path),'--no-preview','-o',str(dng)]
        result=subprocess.run(command,capture_output=True,text=True);(work/'pack.stdout').write_text(result.stdout);(work/'pack.stderr').write_text(result.stderr);assert result.returncode==0,(stem,result.stderr)
        meta=raw_media.extract(dng,14);tags={r['code']:r for r in meta['image']};assert meta['cfa']=='RGGB' and (meta['width'],meta['height'])==(8192,6144)
        assert raw_media.values(tags[50714])==(16.,)*4 and raw_media.values(tags[50717])==(16383,)
        # The stock SDK's legacy profile struct omits these archived fields.
        # Restore them with the existing typed metadata writer, keeping pixels.
        def rational_record(code,values,signed=False):
            pairs=[Fraction(str(v)).limit_denominator(1000000) for v in values]
            flat=[n for value in pairs for n in (value.numerator,value.denominator)]
            return raw_media.record(code,10 if signed else 5,len(pairs),struct.pack('<'+('i' if signed else 'I')*len(flat),*flat))
        meta['image']=[r for r in meta['image'] if r['code'] not in (50730,50727)]
        meta['image'] += [rational_record(50730,[profile['baseline_exposure']],True),rational_record(50727,profile['analog_balance'])]
        carrier=work/'reference-with-profile.dng';raw_media.write(carrier,meta,raw.read_bytes());carrier.replace(dng)
        meta=raw_media.extract(dng,14);tags={r['code']:r for r in meta['image']}
        assert abs(raw_media.values(tags[50730])[0]-profile['baseline_exposure'])<1e-6
        assert np.allclose(raw_media.values(tags[50727]),profile['analog_balance'],rtol=1e-6,atol=1e-6)
        neutral=raw_media.values(tags[50728]);actual_wb=[neutral[1]/neutral[0],1.,neutral[1]/neutral[2]]
        assert np.allclose(actual_wb,[tuning['wb_gains'][k] for k in ['r_gain','g_gain','b_gain']],rtol=1e-5,atol=1e-6)
        for code,key in [(50721,'color_matrix_1'),(50722,'color_matrix_2')]:assert np.allclose(raw_media.values(tags[code]),profile[key],rtol=1e-5,atol=1e-6)
        with tifffile.TiffFile(dng) as f:reference=f.asarray()
        assert hashlib.sha256(reference.astype('<u2').tobytes()).hexdigest()==source['raw_sha256']
        independent=work/'independent-reference.raw';stock_still.run(SDK,['-i',dng,'-o',independent],None);assert sha(independent)==source['raw_sha256'];independent.unlink()
        lowmeta,omissions=stock_cnn_metadata.simulated_half(meta);highmeta,_=stock_cnn_metadata.scaled(lowmeta,2)
        supported={**meta,'image':[r for r in meta['image'] if r['code']!=700]};assert stock_still.canonical(highmeta)==stock_still.canonical(supported)
        high=train_stock_sr.deinterleave(reference);small=train_stock_sr.downsample(high);low=np.empty((3072,4096),dtype='<u2')
        for site in range(4):low[site//2::2,site%2::2]=small[site]
        input_raw=work/'input.raw';low.tofile(input_raw)
        encoded=stock_still.encode(input_raw,lowmeta,3,SDK,work/'input-q3.gpr');decoded=stock_still.decode(work/'input-q3.gpr',14,SDK,work/'decoded.dng')
        with tifffile.TiffFile(work/'decoded.dng') as f:decoded_low=f.asarray()
        assert hashlib.sha256(decoded_low.astype('<u2').tobytes()).hexdigest()==decoded['raw_sha256'];decoded_low.tofile(work/'decoded.raw')
        planes=train_stock_sr.deinterleave(decoded_low);positions=[]
        for _ in range(32):
            y=int(rng.integers(0,(1536-128)//8+1))*8;x=int(rng.integers(0,(2048-128)//8+1))*8
            inputs[cursor]=planes[:,y:y+128,x:x+128];targets[cursor]=high[:,2*y:2*y+256,2*x:2*x+256];positions.append([y,x]);cursor+=1
        row.update(path=str(dng),sha256=sha(dng),patch_start=cursor-32,patch_count=32,low_plane_yx=positions,reference_raw_sha256=source['raw_sha256'],low_input_raw_sha256=sha(input_raw),low_gpr_sha256=encoded['output_sha256'],low_decoded_raw_sha256=decoded['raw_sha256'],simulation_metadata_omissions=omissions,independent_repackaged_pixels_verified=True,supported_simulated_calibration_roundtrip_exact=True)
        m.update(repackaged_metadata_sha256=hashlib.sha256(stock_still.canonical(meta)).hexdigest(),repackaged_pixels_exact=True,independent_sdk_read_exact=True)
        save(root/'dataset.json',report);save(ROOT/'calibration-audit.json',metadata)
        print(json.dumps(dict(stem=stem,split=source['split'],patches=32,total_patches=cursor,metadata_corroborated=corroborated)),flush=True)
        del reference,high,small,low,decoded_low,planes
    assert cursor==count;inputs.flush();targets.flush();del inputs,targets
    report.update(complete=True,input_sha256=sha(root/'inputs.npy'),target_sha256=sha(root/'targets.npy'));save(root/'dataset.json',report)
    assert len(metadata['rows'])==42 and sum(r['direct_source_params_corroborated'] for r in metadata['rows'])==10
    metadata.update(complete=True,direct_source_corroborated=10,archived_per_frame=42,split_counts=dict(collections.Counter(r['split'] for r in metadata['rows'])),test_patch_pixels_read=False)
    save(ROOT/'calibration-audit.json',metadata);print(json.dumps(dict(complete=True,patches=cursor,split_counts=metadata['split_counts'])),flush=True)
if __name__=='__main__':main()
