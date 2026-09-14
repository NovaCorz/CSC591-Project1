#!/usr/bin/env python3
"""Evaluate immutable lab predictions against frozen Hazel summaries; never fit models."""
import argparse, csv, datetime, hashlib, json, math, os, platform, shutil, subprocess, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PRE=ROOT/'prediction/pre_hazel/outputs'
HAZEL=Path('/share/ece592f26/hlee58/tmp/hazel-phase3-20260911')
HOSTS=['haswell','cascadelake','icelake_8358','genoa','turin']
U='UNSUPPORTED'
# id, units, observed point/low/high, frozen prediction point/low/high, frozen curve column
METRICS=[
('l1_capacity','KiB','l1_capacity_mid_kib','l1_capacity_lower_kib','l1_capacity_upper_kib','l1_capacity_point_kib','l1_capacity_empirical_low_kib','l1_capacity_empirical_high_kib',2),
('l1_associativity','ways','l1_associativity_conditional_ways',None,None,'l1_associativity_point_ways','l1_associativity_empirical_low_ways','l1_associativity_empirical_high_ways',3),
('l1_latency','ns/access','l1_like_median_ns_per_access','l1_like_p05_ns_per_access','l1_like_p95_ns_per_access','l1_like_latency_point_ns_per_access','l1_like_latency_empirical_low_ns','l1_like_latency_empirical_high_ns',4),
('l2_capacity','KiB','l2_capacity_mid_kib','l2_capacity_lower_kib','l2_capacity_upper_kib','l2_capacity_point_kib','l2_capacity_95pi_low_kib','l2_capacity_95pi_high_kib',1),
('l2_associativity','ways','l2_associativity_conditional_ways',None,None,'l2_associativity_point_ways','l2_associativity_empirical_low_ways','l2_associativity_empirical_high_ways',5),
('llc_capacity','MiB','llc_capacity_mid_mib','llc_capacity_lower_mib','llc_capacity_upper_mib','llc_like_capacity_point_mib','llc_like_capacity_empirical_low_mib','llc_like_capacity_empirical_high_mib',6),
('line_size','bytes','visible_spatial_boundary_bytes',None,None,'visible_spatial_boundary_bytes',None,None,7),
('software_metric','%','software_metric_pct','software_threshold_sensitivity_low_pct','software_threshold_sensitivity_high_pct','software_metric_point_pct','software_metric_threshold_low_pct','software_metric_threshold_high_pct',8)]
M={m[0]:m for m in METRICS}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def readcsv(p): return list(csv.DictReader(p.open()))
def writecsv(p,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def js(p,x): p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def num(x):
    try:
        v=float(x);return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None
def interval(x):
    if not x:return None,None
    a=json.loads(x);return (None,None) if a is None else tuple(a)
def geometric(a,b):return math.sqrt(a*b) if a is not None and b is not None else U

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--smoke',action='store_true');args=ap.parse_args()
    if not os.environ.get('SLURM_JOB_ID'):raise SystemExit('Run through Slurm: analysis is forbidden on login nodes')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);(out/'plots').mkdir();(out/'frozen-inputs').mkdir()
    inputs={}
    def track(p):
        p=Path(p);inputs[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size};return p
    freeze=json.loads(track(PRE/'freeze-manifest.json').read_text())
    for e in freeze['outputs']:
        p=track(PRE/e['path']);assert sha(p)==e['sha256'],f'Frozen prediction changed: {p}'
    hf=json.loads(track(HAZEL/'results/timing-freeze.json').read_text())
    assert hf['hosts']==HOSTS
    def hz(rel):
        p=track(HAZEL/rel);assert sha(p)==hf['files'][rel]['sha256'],f'Hazel freeze mismatch: {rel}';return p
    cache=readcsv(hz('results/cache-inference-table.csv'))
    latency=readcsv(hz('analysis/followup/latency-classes.csv'))
    summary=json.loads(hz('results/timing-only-summary.json').read_text())
    machines={r['constraint']:r for r in readcsv(hz('results/machine-results.csv'))}
    raw_inventory=json.loads(hz('results/raw-record-inventory.json').read_text())
    predictions={r['constraint']:r for r in readcsv(PRE/'hazel-predictions.csv')}
    lab=readcsv(PRE/'lab-only-chronological-master.csv')
    targets={r['constraint']:r for r in readcsv(track(ROOT/'prediction/pre_hazel/inputs/hazel-targets.csv'))}
    pub=json.loads(track(HERE/'inputs/published-sources.json').read_text())
    track(Path(__file__));track(HERE/'run.slurm')
    for name in ['hazel-predictions.csv','model-parameters.json','future-predictions.csv','team-cache-laws.md','freeze-manifest.json']:
        shutil.copy2(PRE/name,out/'frozen-inputs'/name)
    shutil.copy2(PRE/'plot-data/future-models.dat',out/'frozen-inputs/future-models.dat')
    haz=[];provenance=[]
    for host in HOSTS:
        t=targets[host];r={k:U for k in lab[0]}
        r.update(year=t['year'],machine=host,cpu=machines[host]['exact_cpu_model'],vendor=t['vendor'],isa=t['isa'],microarchitecture=t['generation'],platform_class='server',process_node={'haswell':'22 nm','cascadelake':'14 nm','icelake_8358':'10 nm','genoa':'5 nm CCD / 6 nm IOD','turin':'4 nm CCD / 6 nm IOD'}[host],year_convention=t['year_convention'],year_source_url=t['year_source_url'],dataset='Hazel',inclusion_exclusion='uncertain',llc_sharing_scope='timing domain unresolved; published domain stored separately')
        for role,prefix,div in [('L1-like candidate','l1',1024),('L2-like candidate','l2',1024),('LLC-like candidate','llc',1048576)]:
            c=next(x for x in cache if x['host']==host and x['role']==role)
            lo,hi=interval(c['capacity_interval_bytes']);unit='mib' if prefix=='llc' else 'kib'
            r[f'{prefix}_capacity_lower_{unit}']=lo/div if lo else U
            r[f'{prefix}_capacity_upper_{unit}']=hi/div if hi else U
            r[f'{prefix}_capacity_mid_{unit}']=geometric(lo/div,hi/div) if lo else U
            # Midpoints are a plotting/evaluation convention, not new physical inferences.
            r[f'{prefix}_capacity_candidate_{unit}']=float(c['capacity_candidate_bytes'])/div if c['capacity_candidate_bytes'] else U
            if prefix!='llc':r[f'{prefix}_associativity_conditional_ways']=c['ways_candidate'] or U
            r[f'{prefix}_inference_caveat']=c['caveat']
            if prefix=='l1':r['visible_spatial_boundary_bytes']=c['line_candidate_bytes'] or U
        choices=[x for x in latency if x['host']==host and x['stride']=='64' and x['class_index']=='1']
        assert len(choices)<=1
        if choices:
            x=choices[0];rp=track(HAZEL/'suite'/x['source']);run=json.loads(rp.read_text())
            # The frozen inventory hashes run records; the top-level freeze hashes that inventory.
            frozen_key=str(rp.resolve().relative_to(HAZEL.resolve()))
            assert frozen_key in raw_inventory and sha(rp)==raw_inventory[frozen_key]['record_sha256'],f'unfrozen latency source {rp}'
            assert int(x['n'])==run['exact_raw_count']==1000000 and run['status']=='passed'
            rate=float(run['measurement']['empirical_ticks_per_second']);assert rate>0
            for source,dest in [('median','median'),('p05','p05'),('p95','p95')]:r[f'l1_like_{dest}_ns_per_access']=float(x[source])*1e9/rate
            r['l1_like_median_native_ticks_per_access']=x['median'];r['l1_like_native_unit']=x['unit']
            r['l1_latency_source']=x['source'];r['l1_latency_empirical_ticks_per_second']=rate
            provenance.append({'host':host,'kind':'L1-like ns conversion','source':str(rp),'rate_ticks_per_second':rate,'conversion':'native statistic * 1e9 / empirical_ticks_per_second','nominal_GHz_used':False})
        else:r['l1_latency_source']='UNSUPPORTED: no accepted stride64 first-class representative; no baseline substitution'
        s=summary['details'][host]['baseline']['software_metric'];assert s['same_logical_cpu'] and s['total_timed_accesses']==1000000 and s['standardized_workload_bytes']==1048576
        r.update(software_metric_pct=100*s['estimate'],software_threshold_sensitivity_low_pct=100*s['threshold_sensitivity_rate_range'][0],software_threshold_sensitivity_high_pct=100*s['threshold_sensitivity_rate_range'][1],software_workload_bytes=s['standardized_workload_bytes'],software_block_low_pct=100*s['block_rate_range'][0],software_block_high_pct=100*s['block_rate_range'][1])
        for f in ['l1_miss_penalty','l2_hit_latency','l2_miss_penalty','llc_associativity','llc_hit_latency','llc_memory_penalty']:r[f]='UNSUPPORTED: physical level not isolated by verified evidence'
        r['timing_class_count']=machines[host]['timing_class_count'] or U;r['physical_cache_level_count']=U
        haz.append(r)
    # Lab rows remain numerically identical. Confirm identical standardized software footprint.
    for r in lab:
        p=track(ROOT/f"data_processed/{r['machine']}-inference.json");s=json.loads(p.read_text())['software_metric']
        assert s['standardized_workload_bytes']==1048576 and s['same_logical_cpu']
        r.update(dataset='ECE',software_workload_bytes=1048576,physical_cache_level_count=U)
    master=sorted(lab+haz,key=lambda x:(int(x['year']),x['dataset'],x['machine']))
    writecsv(out/'chronological-master.csv',master);writecsv(out/'hazel-observations.csv',haz)
    js(out/'measurement-provenance.json',provenance)
    comparisons=[]
    for r in haz:
        p=predictions[r['machine']]
        for metric,unit,key,lk,hk,pk,plk,phk,col in METRICS:
            observed=num(r.get(key));pred=num(p[pk]);lo=num(r.get(lk)) if lk else observed;hi=num(r.get(hk)) if hk else observed
            pl=num(p.get(plk)) if plk else pred;ph=num(p.get(phk)) if phk else pred
            z=dict(constraint=r['machine'],year=r['year'],metric=metric,unit=unit,prediction=pred,prediction_low=pl,prediction_high=ph,observation=observed,observation_low=lo,observation_high=hi,
                point_convention='geometric bracket midpoint, not physical estimate' if 'capacity' in metric else 'conditional ways / boundary / median / classifier estimate',
                evaluation_role='future-year extrapolation' if int(r['year'])>2023 else 'unseen machine at year within training span',
                uncertainty_kind='timing brackets are sweep bounds, not confidence intervals; model L2 interval heuristic 95%; other model ranges empirical',status='unresolved observation')
            if observed is not None:
                z.update(signed_error=pred-observed,absolute_error=abs(pred-observed),relative_error_pct=100*(pred-observed)/observed,absolute_relative_error_pct=100*abs(pred-observed)/observed,
                    prediction_point_in_measurement_range=lo<=pred<=hi,observation_point_in_prediction_range=pl<=observed<=ph,intervals_overlap=max(lo,pl)<=min(hi,ph),
                    min_absolute_error_to_measurement_range=max(lo-pred,0,pred-hi),max_absolute_error_to_measurement_range=max(abs(pred-lo),abs(pred-hi)),
                    signed_relative_error_lower_pct=100*(pred/hi-1),signed_relative_error_upper_pct=100*(pred/lo-1) if lo>0 else None,
                    status='point within measurement range' if lo<=pred<=hi else 'point outside measurement range')
                if metric=='software_metric':z['error_unit']='percentage points (relative error separately %)'
            comparisons.append(z)
        for key in ['hierarchy','l1_miss_penalty','l2_hit_latency','l2_miss_penalty','llc_associativity','llc_hit_latency','llc_memory_penalty','inclusion_exclusion']:
            comparisons.append(dict(constraint=r['machine'],year=r['year'],metric=key,prediction=p.get(key,U),observation=r.get(key,U),status='unresolved; not scored as agreement'))
    writecsv(out/'prediction-errors.csv',comparisons)
    accuracy=[]
    for metric in M:
        valid=[c for c in comparisons if c['metric']==metric and c.get('absolute_error') is not None]
        closest=min(valid,key=lambda c:c['absolute_relative_error_pct']) if valid else None
        worst=max(valid,key=lambda c:c['absolute_relative_error_pct']) if valid else None
        accuracy.append(dict(metric=metric,scorable=len(valid),unresolved=5-len(valid),
            mean_absolute_relative_error_pct=sum(c['absolute_relative_error_pct'] for c in valid)/len(valid) if valid else None,
            prediction_point_inside_observation_range=sum(c['prediction_point_in_measurement_range'] for c in valid),
            interval_overlap_count=sum(c['intervals_overlap'] for c in valid),
            closest_constraint=closest['constraint'] if closest else None,closest_absolute_relative_error_pct=closest['absolute_relative_error_pct'] if closest else None,
            largest_error_constraint=worst['constraint'] if worst else None,largest_absolute_relative_error_pct=worst['absolute_relative_error_pct'] if worst else None,
            limitation='capacity scores use bracket midpoints; broad interval overlap does not demonstrate accurate prediction'))
    writecsv(out/'prediction-accuracy-summary.csv',accuracy)
    by={(r['constraint'],r['metric']):r for r in comparisons};pubby={(r['constraint'],r['metric']):r for r in pub['rows']}
    published=[]
    for h in HOSTS:
        for metric in [m[0] for m in METRICS]+['inclusion','llc_package','llc_domain_cores','llc_associativity','hierarchy','l1_miss_penalty','l2_hit_latency','l2_miss_penalty','llc_hit_latency','llc_memory_penalty']:
            p=pubby.get((h,metric));c=by.get((h,metric),{});row={'constraint':h,'metric':metric,'prediction':c.get('prediction',U),'prediction_low':c.get('prediction_low'),'prediction_high':c.get('prediction_high'),'timing_inference_point':c.get('observation',U),'timing_inference_low':c.get('observation_low'),'timing_inference_high':c.get('observation_high'),'published_value':p['published_value'] if p else 'NOT ESTABLISHED BY CITED SOURCES','unit':p['unit'] if p else c.get('unit',''),'status':'not quantitatively comparable'}
            if p:
                source=pub['sources'][p['source_id']];row.update(source_id=p['source_id'],source_url=source['url'],source_locator=source['locator'],qualification=p['qualification'])
                v=num(p['published_value']);o=num(c.get('observation'));pr=num(c.get('prediction'))
                if v is not None and pr is not None:
                    row.update(prediction_minus_published=pr-v,prediction_relative_error_pct=100*(pr-v)/v)
                if v is not None and o is not None:
                    lo=c['observation_low'];hi=c['observation_high'];row.update(timing_midpoint_minus_published=o-v,timing_midpoint_relative_error_pct=100*(o-v)/v,published_inside_timing_bracket=lo<=v<=hi,status='conditional role/domain comparison; bracket containment is not proof')
                if metric=='inclusion':row.update(prediction='uncertain',timing_inference_point='uncertain',status='timing unresolved; published category does not repair inference')
            published.append(row)
    writecsv(out/'prediction-timing-published.csv',published)
    # Domain normalization is explicitly a derived post-verification quantity, never a replacement.
    norm=[]
    for r in haz:
        h=r['machine'];cores=pubby[h,'llc_domain_cores']['published_value'];v=pubby[h,'llc_capacity']['published_value']
        lo=num(r['llc_capacity_lower_mib']);hi=num(r['llc_capacity_upper_mib'])
        norm.append(dict(constraint=h,year=r['year'],published_domain_cores=cores,published_domain_mib=v,published_mib_per_domain_core=v/cores,timing_low_mib_per_domain_core=lo/cores if lo else None,timing_high_mib_per_domain_core=hi/cores if hi else None,status='conditional normalization assuming timing domain corresponds to published domain; not independently established',published_package_mib=pubby[h,'llc_package']['published_value']))
    writecsv(out/'llc-domain-normalization.csv',norm)
    # Preserve every latency class as empirical evidence without assigning physical cache levels.
    classrows=[]
    for x in latency:
        y=dict(x);y['interpretation']='empirical class only; not isolated physical cache hit/miss';classrows.append(y)
    writecsv(out/'hazel-latency-class-evidence.csv',classrows)
    statuses=readcsv(PRE/'required-plot-status.csv')
    for r in statuses:
        r['hazel_status']={1:'5/5 capacity brackets',2:'5/5 conditional way values',3:'4/5 matched representatives; Cascade Lake unresolved',4:'unsupported isolated penalty',5:'3/5 conditional brackets; Cascade Lake and Ice Lake unresolved',6:'1/5 conditional ways (Haswell)',7:'unsupported isolated L2 hit latency',8:'unsupported isolated L2 miss penalty',9:'3/5 effective brackets; domain normalization conditional',10:'unsupported',11:'unsupported isolated LLC hit/memory penalty',12:'5/5 visible 64-byte boundary',13:'5/5 uncertain',14:'5/5 identical 1 MiB workload; threshold sensitive',15:'TODO partner Phase-II comparable PMU metrics'}[int(r['spec_item'])]
    writecsv(out/'requirements-status.csv',statuses)
    selfchecks()
    if not args.smoke:plots(out,master,predictions,comparisons,norm)
    reports(out,comparisons,pub,haz,statuses)
    # Inputs must still be byte-identical at completion.
    for p,e in inputs.items():assert sha(Path(p))==e['sha256'],f'Input mutated during evaluation: {p}'
    assert len(master)==13 and len(haz)==5 and len(comparisons)==80
    js(out/'input-manifest.json',inputs)
    js(out/'validation.json',{'passed':True,'lab_rows':8,'hazel_rows':5,'comparison_rows':len(comparisons),'frozen_prediction_hashes_verified':len(freeze['outputs']),'source_hashes_unchanged':True,'no_refitting':True,'software_workload_bytes':1048576,'smoke':args.smoke,'unit_conversion':'empirical timer rate only','tests':'interval cases, missing values, zero error and denominator checks; frozen inputs and counts'})
    js(out/'provenance.json',{'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'slurm_job_id':os.environ['SLURM_JOB_ID'],'hostname':platform.node(),'python':sys.version,'command':sys.argv,'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'affinity':sorted(os.sched_getaffinity(0)),'prediction_manifest':str(PRE/'freeze-manifest.json'),'timing_manifest':str(HAZEL/'results/timing-freeze.json'),'models_refitted':False,'published_information_used_only_for_comparison':True})
    js(out/'output-manifest.json',{str(p.relative_to(out)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file()})
    print(json.dumps({'passed':True,'output':str(out),'master_rows':13,'comparison_rows':len(comparisons)}))

def selfchecks():
    assert num(U) is None and num('nan') is None and num('0')==0
    assert interval('[32, 36]')==(32,36) and interval('')==(None,None)
    assert geometric(32,128)==64
    for pred,lo,hi,want in [(30,32,36,2),(34,32,36,0),(40,32,36,4)]:assert max(lo-pred,0,pred-hi)==want


def plots(out,master,predictions,comparisons,norm):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.backends.backend_pdf import PdfPages
    plt.rcParams.update({'font.size':12,'axes.linewidth':1.3,'lines.linewidth':1.5,'axes.grid':False,'savefig.facecolor':'white','pdf.fonttype':42,'svg.fonttype':'none'})
    curve=[]
    for line in (out/'frozen-inputs/future-models.dat').read_text().splitlines():
        if line and not line.startswith('#'):curve.append([float(x) for x in line.split()])
    assert min(x[0] for x in curve)==2023
    markers={'Intel':'o','AMD':'s','Ampere':'^'}
    def save(fig,name):
        for ext in ['pdf','svg','png']:fig.savefig(out/'plots'/f'{name}.{ext}',bbox_inches='tight',dpi=140)
    titles={'l1_capacity':'L1-like capacity','l1_associativity':'L1 conditional associativity','l1_latency':'L1-like dependent latency','l2_capacity':'L2-like effective capacity','l2_associativity':'L2 conditional associativity','llc_capacity':'LLC-like effective capacity','line_size':'Smallest visible spatial boundary','software_metric':'Software residency proxy'}
    def panel(ax,m,labels=False):
        metric,unit,key,lk,hk,pk,plk,phk,col=m
        for dataset in ['ECE','Hazel']:
            for vendor in sorted(set(r['vendor'] for r in master)):
                rs=[r for r in master if r['dataset']==dataset and r['vendor']==vendor and num(r.get(key)) is not None]
                if not rs:continue
                xs=[int(r['year']) for r in rs];ys=[float(r[key]) for r in rs]
                lows=[num(r.get(lk)) if lk else y for r,y in zip(rs,ys)];highs=[num(r.get(hk)) if hk else y for r,y in zip(rs,ys)]
                lows=[y if l is None else l for l,y in zip(lows,ys)];highs=[y if h is None else h for h,y in zip(highs,ys)]
                marker=markers.get(vendor,'^') if dataset=='ECE' else ('D' if vendor=='Intel' else '*')
                ax.errorbar(xs,ys,yerr=[[max(0,y-l) for y,l in zip(ys,lows)],[max(0,h-y) for y,h in zip(ys,highs)]],fmt=marker,color='black',mfc='black' if dataset=='ECE' else 'white',ms=6 if dataset=='ECE' else 9,capsize=3,linestyle='none',label=f'{dataset} {vendor}')
                # Solid lines only within one vendor/ISA; no invented pooled architectural lineage.
                if dataset=='ECE' and len(rs)>1:ax.plot(xs,ys,'-',color='0.55',lw=1,zorder=0)
                # Dense coincident ECE values are identified through vendor markers and
                # the master table. Label Hazel targets to avoid overlapping text.
                if labels and dataset=='Hazel':
                    for i,(x,y,r) in enumerate(zip(xs,ys,rs)):
                        offset=(4,-22-9*(i%2)) if vendor=='AMD' else (4,9+9*(i%2))
                        ax.annotate(r['machine'],(x,y),xytext=offset,textcoords='offset points',fontsize=8)
        ax.plot([x[0] for x in curve],[x[col] for x in curve],'--',color='black',lw=2,label='Frozen extrapolation')
        # Frozen target predictions at historical years are separate plus signs, not back-extrapolated dashed lines.
        historical=[p for h,p in predictions.items() if h in HOSTS and int(p['year'])<2023]
        ax.plot([int(p['year']) for p in historical],[float(p[pk]) for p in historical],'+',color='0.35',ms=8,label='Frozen target prediction')
        ax.set(xlabel='Generation introduction year',ylabel=f'{titles[metric]} ({unit})',xlim=(2013,2030));ax.set_xticks([2014,2018,2022,2026,2029]);ax.tick_params(direction='out')
        if 'capacity' in metric:ax.set_yscale('log',base=2)
        if metric=='line_size':ax.set_ylim(56,72)
        missing=[r['machine'] for r in master if r['dataset']=='Hazel' and num(r.get(key)) is None]
        if missing:ax.text(.02,.98,'Unresolved: '+', '.join(missing),transform=ax.transAxes,va='top',fontsize=8,wrap=True)
    with PdfPages(out/'plots/required-chronological-plots.pdf') as book:
        for m in METRICS:
            fig,ax=plt.subplots(figsize=(10,5.5));panel(ax,m,True);ax.legend(fontsize=8,loc='best',ncol=2);fig.tight_layout();save(fig,m[0]);book.savefig(fig,bbox_inches='tight');plt.close(fig)
        fig,ax=plt.subplots(figsize=(10,5));
        for i,r in enumerate(master):
            marker=markers.get(r['vendor'],'^') if r['dataset']=='ECE' else ('D' if r['vendor']=='Intel' else '*')
            ax.plot(int(r['year']),i,marker,color='black',mfc='black' if r['dataset']=='ECE' else 'white',ms=8)
        ax.set_yticks(range(len(master)),[r['machine']+' — uncertain' for r in master],fontsize=9);ax.set(xlabel='Generation introduction year',title='Inclusion/exclusion: all timing classifications remain uncertain');fig.tight_layout();save(fig,'inclusion');book.savefig(fig);plt.close(fig)
        missing=[('l1_miss_penalty','L1 miss penalty: L1-to-next-level service not isolated'),('l2_hit_latency','L2 hit latency: physical L2 residency not isolated'),('l2_miss_penalty','L2 miss penalty: next-level service not isolated'),('llc_associativity','LLC associativity: no supported conditional geometry'),('llc_hit_memory_latency','LLC hit and memory penalty: physical service classes not isolated'),('pmu_trends','PMU trends: TODO partner Phase-II results for two comparable events')]
        for name,note in missing:
            fig,ax=plt.subplots(figsize=(10,4));ax.set(xlim=(2013,2030),xlabel='Generation introduction year',title=note);ax.set_yticks([]);ax.text(.5,.5,'No supported numerical series\nNo invented points or fitted trend',ha='center',transform=ax.transAxes);fig.tight_layout();save(fig,name);book.savefig(fig);plt.close(fig)
    fig,axs=plt.subplots(3,3,figsize=(16,13))
    for ax,m in zip(axs.flat,METRICS):panel(ax,m)
    axs.flat[-1].axis('off');handles,labels=axs.flat[0].get_legend_handles_labels();axs.flat[-1].legend(handles,labels,loc='center',fontsize=11)
    fig.suptitle('ECE observations and unchanged predictions with Hazel measurements',fontsize=17);fig.tight_layout(rect=(0,0,1,.96));save(fig,'chronological-overview');plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(13,5));panel(axs[0],M['l2_capacity'],True);panel(axs[1],M['line_size'],True)
    axs[0].set_title('Kuethe–Lee L2 Capacity Law');axs[1].set_title('Kuethe–Lee Spatial Granularity Law');axs[0].legend(fontsize=7,ncol=2);fig.tight_layout();save(fig,'team-laws-hazel-evaluation');plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5));panel(ax,M['l2_capacity'],True)
    future=next(r for r in readcsv(PRE/'future-predictions.csv') if r['year']=='2029');v=float(future['l2_capacity_point_kib']);lo=float(future['l2_capacity_95pi_low_kib']);hi=float(future['l2_capacity_95pi_high_kib'])
    ax.errorbar(2029,v,yerr=[[v-lo],[hi-v]],fmt='+',color='black',ms=10,capsize=5,label='2029 heuristic 95% interval');ax.legend(fontsize=8,ncol=2);fig.tight_layout();save(fig,'future-2029');plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5))
    for r in norm:
        ax.plot(int(r['year']),r['published_mib_per_domain_core'],'x',color='black')
        lo=r['timing_low_mib_per_domain_core'];hi=r['timing_high_mib_per_domain_core']
        if lo is not None:
            mid=math.sqrt(lo*hi);ax.errorbar(int(r['year']),mid,yerr=[[mid-lo],[hi-mid]],fmt='D',mfc='white',color='black',capsize=4)
        ax.annotate(r['constraint'],(int(r['year']),r['published_mib_per_domain_core']),xytext=(4,7),textcoords='offset points',fontsize=9)
    ax.set(xlabel='Generation introduction year',ylabel='LLC MiB / published domain core',title='Conditional normalization; published domain correspondence unverified');ax.set_yscale('log',base=2);ax.legend(handles=[Line2D([],[],marker='x',color='black',ls='',label='Published domain'),Line2D([],[],marker='D',mfc='white',color='black',ls='',label='Timing bracket / published core count')]);fig.tight_layout();save(fig,'llc-normalized');plt.close(fig)


def reports(out,comparisons,pub,haz,statuses):
    lines=['# Frozen predictions evaluated against Hazel','',
    'The original ECE-only models and prediction curves are unchanged. This package uses Hazel only for evaluation. Native timing inferences and published information remain separate. The source freeze manifests identify their actual timestamps; this comparison does not establish a pre-execution prediction freeze.','',
    '## Reading the comparisons','',
    'Errors use prediction minus observation. Capacity point comparisons use the same geometric bracket-midpoint convention as the frozen training dataset; they are not new physical capacity estimates. The original capacity candidates and brackets are retained in the master table. Error bounds use bracket endpoints. Bracket overlap is compatibility, not accurate identification. Latency bars are P5–P95 sample-distribution spans, not confidence intervals on the median. Software bars show threshold sensitivity; they are not hardware hit-rate confidence intervals.','',
    'Only Turin (2024) is later than the newest ECE training year (2023). Haswell, Cascade Lake, Ice Lake and Genoa test transfer to unseen machines at years within the training span. Original future dashed curve samples are copied byte-for-byte; historical target predictions appear as plus signs. Solid connections are confined to the same vendor/ISA, avoiding an implied cross-vendor lineage.','',
    '## Quantitative comparison','',
    '| Metric | Machine | Frozen prediction | Observed point [range] | Absolute error | Interpretation |','|---|---|---:|---:|---:|---|']
    def f(x):return f'{x:.6g}' if isinstance(x,(float,int)) else str(x)
    for c in comparisons:
        if c['metric'] not in M:continue
        o=c['observation'];obs='unresolved' if o is None else f"{f(o)} [{f(c['observation_low'])}, {f(c['observation_high'])}]"
        lines.append(f"| {c['metric']} ({c['unit']}) | {c['constraint']} | {f(c['prediction'])} | {obs} | {f(c.get('absolute_error','—'))} | {c['status']} |")
    lines+=['','## Interpretation by quantity','',
    '- **Capacity:** L1 remains a small, stepwise structure; the constant model cannot identify the 32 versus 48 KiB choice. The L2 exponential rule describes the four pooled lab servers but must be judged against both measured brackets and the separate published organization. Broad LLC brackets cannot verify a precise constant-capacity forecast. Cascade Lake and Ice Lake deeper capacities are unresolved, so no error is assigned.','- **Associativity:** The eight-way L1 point prediction matches Haswell, Cascade Lake and Genoa, but underpredicts Ice Lake and Turin by four ways (33.33% of the observed value). The empirical training range contains all five. Only Haswell has a supported Hazel L2 way inference; missing values do not count as successes.','- **Latency and penalties:** The four available matched L1-like representatives use recorded empirical timer rates for ns/access. Cascade Lake has no qualifying stride64 class row, so substituting its baseline median would change the measurement definition. Neither ns nor TSC ticks are asserted to be core cycles. Physical L2/LLC hit latencies and incremental cache/memory penalties remain unsupported; empirical class statistics are supplied separately without physical labels. The data do not support a general monotonically increasing latency law.','- **Line size and inclusion:** All five Hazel timing boundaries equal the 64-byte prediction. This supports the scoped spatial-granularity law, not an independently measured line size for every level. All inclusion classifications remain uncertain and are not counted as successful categorical predictions.','- **Residency proxy:** All thirteen machines use the same 1 MiB standardized workload. Point errors can be large even though threshold-sensitivity ranges overlap. This demonstrates sensitivity to classifier calibration and workload residence; it does not establish a hardware hit-rate trend.','- **Cross-architecture and platform effects:** The frozen server model pools Intel, AMD and Arm; it is not an AMD-specific law. The small sample cannot separate year, ISA, server/desktop class, chiplet topology, frequency, and memory-platform effects. The figures retain desktop observations but the frozen forecasts use the selected lab-server subset.','',
    '## Published verification','',
    'See `prediction-timing-published.csv` for the three-way comparison, source locators, and scope qualifications. Manufacturer MB/KB cache labels are represented as binary MiB/KiB. Intel socket LLCs and AMD per-CCD LLCs are compared conditionally with the effective domain observed by a pinned core. The AMD 384 MiB package sum is never substituted for a 32 MiB CCD domain. `llc-domain-normalization.csv` provides explicitly conditional MiB/core normalization. Missing published latencies/ways are left unestablished; generic core latency claims are not used as SKU-specific nanosecond targets.','',
    'The closest well-defined prediction is the 64-byte spatial boundary. The L1 way prediction misses the two twelve-way cores. Hardware capacity agreement can be checked where the timing brackets exist; wide LLC containment provides weak evidence. Architecture and sharing-domain differences are plausible explanations, not experimentally isolated causes.','',
    '## Requirements and remaining unsupported work','',
    'The fifteen required chronological plot categories are tracked in `requirements-status.csv`. Unsupported physical quantities have explicitly labeled panels instead of invented values. Two comparable PMU trend series require the partner’s Phase-II data. No PMU collection or ECE hardware verification is performed here. Report/slides integration is separate from these analysis outputs.','',
    '## Sources','']
    for key,s in pub['sources'].items():lines.append(f"- **{key}**: [{s['title']}]({s['url']}), {s['locator']}. {s['facts']}")
    (out/'comparison-summary.md').write_text('\n'.join(lines)+'\n')
    cs={r['constraint']:r for r in comparisons if r['metric']=='l2_capacity'}
    law=['# Kuethe–Lee laws: Hazel evaluation and future scaling','',
    'The equations, fitted observations, and parameters are unchanged from `frozen-inputs/team-cache-laws.md` and `model-parameters.json`. No Hazel observation was used to refit either law.','',
    '## Kuethe–Lee L2 Capacity Law','',
    'Frozen rule: log2(C_KiB) = log2(2172.232032) + 0.358490566 × (year − 2023). The four pooled ECE servers span 2014–2023; the reported doubling time is 2.79 years and anchored R² is 0.925. The response is a timing-bracket midpoint, not independently identified physical L2.','',
    '| Hazel target | Predicted KiB | Timing bracket KiB | Point inside bracket? |','|---|---:|---:|---|']
    for h,c in cs.items():law.append(f"| {h} | {f(c['prediction'])} | {f(c['observation_low'])}–{f(c['observation_high'])} | {c.get('prediction_point_in_measurement_range','unresolved')} |")
    law+=['',
    'The Haswell prediction falls below its narrow timing bracket, while Genoa is overpredicted; their heuristic model intervals still overlap their timing brackets. Turin is overpredicted by 156.42% relative to the bracket midpoint, and its timing bracket does not overlap the frozen heuristic 95% prediction interval. This fails the model’s 2024 future-year test. Cascade Lake and Ice Lake cannot test L2 accuracy with the frozen unresolved timing evidence. This weakens the exponential rule as a transferable prediction; it does not invalidate the original four-point descriptive fit.','',
    'Scaling cannot continue indefinitely. SRAM area, leakage, access energy, wire delay, and banking/interconnect overhead constrain capacity. Device density and wire delay are technology limits; die-area budgets, SKU segmentation and acceptable hit latency are design/economic choices. A stepwise or piecewise rule is more plausible than indefinite exponential growth. These observations do not locate a numerical wall or its year.','',
    '## Kuethe–Lee Spatial Granularity Law','',
    'Frozen rule: B(year) = 64 bytes. Eight ECE machines from 2014–2023 support the original constant behavior rule; all five Hazel boundaries match exactly, including 2024 Turin. The Hazel evidence supports this scoped rule. An observed range of 64–64 is not a probabilistic guarantee outside the sample.','',
    'A fixed transfer granularity balances spatial reuse and tag overhead against false sharing, wasted transfers, and bandwidth/energy cost. Interconnect and energy costs impose physical constraints; coherence granularity and compatibility are design choices. Larger vector widths or caches do not force larger lines. The likely continuation is flat or a design-driven step; sectoring or a different access pattern could expose a different boundary. No exact change date is supported. This is the behavior law rather than a latency-cost law because isolated deeper-cache cost measurements are unsupported.','',
    '## Five years beyond the newest measured generation','',
    'The newest measured generation is Turin (2024), making 2029 the required approximately five-year target. The existing frozen 2029 row therefore meets the horizon without modification. L2-like capacity: **9.421 MiB**, heuristic 95% interval **3.737–23.752 MiB**; visible spatial boundary: **64 bytes**. Exact values are in `frozen-inputs/future-predictions.csv`. The 2028 row is five years beyond the newest lab system and is retained as a separate earlier forecast.','',
    'The 2029 values are model-conditional forecasts, not validated hardware claims. Hazel’s failure to follow the L2 point forecast reduces confidence in extrapolating it further. We preserve the original model rather than conceal that weakness by refitting. Future cache partitioning, 3D stacking, chiplet organization, and server design goals may cause large deviations. At least three original lab observations remain on the future figure, with the unchanged dashed continuation.','',
    'Compared with Moore’s component-count observation, this dataset is small, heterogeneous and based partly on operational timing brackets. It supports scoped empirical descriptions and a tested constant boundary, not a universal exponential cache law.']
    (out/'team-laws-and-future.md').write_text('\n'.join(law)+'\n')

if __name__=='__main__':main()
