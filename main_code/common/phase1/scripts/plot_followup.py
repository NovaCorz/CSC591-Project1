#!/usr/bin/env python3
"""Generate SVG evidence only in an external experiment workspace."""
import argparse
import collections
import json
from pathlib import Path
from common import now, sha, write_json, read_raw
ROOT=Path(__file__).resolve().parents[1]
PROCESSED=ROOT/"data_processed/uncertainty"

def figures(host,rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    directory=ROOT/'plots/followup';directory.mkdir(parents=True,exist_ok=True)
    saved=[]
    def save(fig,name,sources):
        baseline=json.loads((ROOT/'data_processed'/(host+'-inference.json')).read_text())
        fig.suptitle(host+' | '+baseline.get('course_cpu_model','')+' | '+baseline.get('isa',''),fontsize=10)
        fig.tight_layout();base=directory/(host+'-'+name)
        for ext in ('svg',):fig.savefig(str(base)+'.'+ext,dpi=150)
        plt.close(fig)
        write_json(str(base)+'.provenance.json',dict(time=now(),records=sources,
            statistic='Median of ten chronological block means with min/max block-mean band on lower-conflict panel; raw quantile boxes on upper-calibration panel' if name=='l2-controlled-conflicts' else 'Native median and IQR; box whiskers P05/P95; outliers retained in raw data',
            note='Raw-recomputed distributions. Asterisks on box labels and crosses on curve panels mark noisy selected points; exact qualification and flags accompany every source. No data editing or specification inputs.'))
        saved.append(base.with_suffix('.svg'))
    colors=['black','0.35','0.65'];markers=['o','s','^']
    spatial=[r for r in rows if r['family']=='spatial_alignment']
    footprints=sorted({r['parameters']['bytes'] for r in spatial})
    if footprints:
        fig,axes=plt.subplots(1,len(footprints),figsize=(10,4),squeeze=False)
        for ax,w in zip(axes[0],footprints):
            for j,align in enumerate(sorted({r['parameters']['align'] for r in spatial})):
                g=sorted([r for r in spatial if r['parameters']['bytes']==w and r['parameters']['align']==align],key=lambda r:r['parameters']['offset'])
                x=[r['parameters']['offset'] for r in g];y=[r['statistics']['median'] for r in g]
                ax.plot(x,y,marker=markers[j%3],color=colors[j%3],label='base shift '+str(align)+' B',markersize=3)
                ax.fill_between(x,[r['statistics']['q1'] for r in g],[r['statistics']['q3'] for r in g],color=colors[j%3],alpha=.15)
                for r in g:
                    if r['qualification']=='noisy':ax.plot(r['parameters']['offset'],r['statistics']['median'],'x',color='black',markersize=9)
            ax.set_title(host+': '+str(w//1024)+' KiB allocation');ax.set_xlabel('Pair offset (bytes)');ax.set_ylabel(rows[0]['measurement']['unit']+'/access');ax.legend(fontsize=8)
        save(fig,'spatial-alignment',[r['record_path'] for r in spatial])
    cap=[r for r in rows if r['family'] in ('capacity_control','capacity_refinement')]
    if cap:
        fig,ax=plt.subplots(figsize=(10,4));keys=sorted({(r['parameters']['page'],r['parameters']['stride']) for r in cap})
        for j,(page,stride) in enumerate(keys):
            chosen={}
            for r in sorted(cap,key=lambda r:r['started']):
                p=r['parameters']
                if (p['page'],p['stride'])==(page,stride):chosen.setdefault(p['bytes'],r)
            g=[chosen[w] for w in sorted(chosen)];x=[r['parameters']['bytes']/1024 for r in g]
            ax.plot(x,[r['statistics']['median'] for r in g],marker=markers[j%3],color=colors[j%3],markersize=3,label=page+', spacing '+str(stride)+' B')
            ax.fill_between(x,[r['statistics']['q1'] for r in g],[r['statistics']['q3'] for r in g],color=colors[j%3],alpha=.15)
            for r in g:
                if r['qualification']=='noisy':ax.plot(r['parameters']['bytes']/1024,r['statistics']['median'],'x',color='black')
        ax.set_xscale('log',base=2);ax.set_yscale('log',base=2);ax.set_xlabel('Working set (KiB)');ax.set_ylabel(cap[0]['measurement']['unit']+'/access');ax.set_title(host+': page-backing and spacing controls');ax.legend(fontsize=8)
        save(fig,'capacity-controls',[r['record_path'] for r in cap])
        intervals=collections.defaultdict(list)
        for r in cap:
            p=r['parameters']
            if 'comparison_interval' in p:intervals[p['page'],tuple(p['comparison_interval'])].append(r)
        items=sorted(intervals.items())
        for page in range(0,len(items),6):
            fig,axes=plt.subplots(2,3,figsize=(10,6));sources=[]
            for ax,((policy,interval),group) in zip(axes.flat,items[page:page+6]):
                group.sort(key=lambda r:r['parameters']['bytes'])
                edge=next((i for i in range(len(group)-1) if group[i+1]['statistics']['median']>1.15*group[i]['statistics']['median'] and group[i+1]['statistics']['q1']>group[i]['statistics']['q3']),None)
                start=min(edge,len(group)-3) if edge is not None else 0
                selected=group[max(0,start):max(0,start)+3]
                boxes=[dict(med=r['statistics']['median'],q1=r['statistics']['q1'],q3=r['statistics']['q3'],whislo=r['statistics']['p05'],whishi=r['statistics']['p95'],fliers=[],label=format(r['parameters']['bytes']/1024,'.4g')+('*' if r['qualification']=='noisy' else '')) for r in selected]
                ax.bxp(boxes,showfliers=False,medianprops=dict(color='black'));ax.set_xlabel('Working set (KiB)')
                ax.set_ylabel(selected[0]['measurement']['unit']+'/access',fontsize=8);ax.set_title(policy+': candidate '+str([w//1024 for w in interval])+' KiB',fontsize=8)
                sources.extend(r['record_path'] for r in selected)
            for ax in list(axes.flat)[len(items[page:page+6]):]:ax.set_visible(False)
            save(fig,'capacity-boxes-'+str(page//6+1),sources)
    confirms=[r for r in rows if r['family']=='spatial_confirmation']
    if confirms:
        chosen=collections.defaultdict(list)
        for r in confirms:
            p=r['parameters'];chosen[p['bytes'],p['align'],p['seed'],p['cohort_repetition']].append(r)
        groups=sorted(chosen.items())
        for page in range(0,len(groups),6):
            fig,axes=plt.subplots(2,3,figsize=(10,6))
            sources=[]
            for ax,((w,align,seed,rep),group) in zip(axes.flat,groups[page:page+6]):
                group.sort(key=lambda r:r['parameters']['offset'])
                boxes=[dict(med=r['statistics']['median'],q1=r['statistics']['q1'],q3=r['statistics']['q3'],whislo=r['statistics']['p05'],whishi=r['statistics']['p95'],fliers=[],label=str(r['parameters']['offset'])+('*' if r['qualification']=='noisy' else '')) for r in group]
                ax.bxp(boxes,showfliers=False,medianprops=dict(color='black'))
                ax.set_title(str(w//1024)+' KiB; shift '+str(align)+'; seed '+str(seed),fontsize=8)
                ax.set_xlabel('Offset (B)');ax.set_ylabel(group[0]['measurement']['unit']+'/access',fontsize=8)
                sources.extend(r['record_path'] for r in group)
            for ax in list(axes.flat)[len(groups[page:page+6]):]:ax.set_visible(False)
            save(fig,'confirmation-boxes-'+str(page//6+1),sources)
    conflicts=[r for r in rows if r['family']=='empirical_conflict']
    if conflicts:
        fig,axes=plt.subplots(1,3,figsize=(10,4));strides=sorted({r['parameters']['search_stride'] for r in conflicts})
        for ax,stride in zip(axes,strides):
            for label,marker,color in [('training','o','0.65'),('heldout','s','black')]:
                g=[r for r in conflicts if r['parameters']['search_stride']==stride and ('heldout' in r['parameters']['search_label'])==(label=='heldout')]
                ax.scatter([r['parameters']['candidate_count'] for r in g],[r['statistics']['median'] for r in g],s=12,marker=marker,color=color,label=label)
            ax.set_title('Pool stride '+str(stride//1024)+' KiB');ax.set_xlabel('Pressure addresses');ax.set_ylabel(conflicts[0]['measurement']['unit']+'/target reload');ax.legend(fontsize=8)
        save(fig,'empirical-conflicts',[r['record_path'] for r in conflicts])
        cohorts=collections.defaultdict(list)
        for r in conflicts:
            p=r['parameters']
            if p['search_label'].startswith('heldout-'):cohorts[p['search_stride'],p['seed']].append(r)
        items=sorted(cohorts.items())
        for page in range(0,len(items),6):
            fig,axes=plt.subplots(2,3,figsize=(10,6));sources=[]
            for ax,((stride,seed),group) in zip(axes.flat,items[page:page+6]):
                controls=sorted([r for r in group if r['parameters']['search_label'] in ('heldout-hot','heldout-full')],key=lambda r:r['parameters']['search_label'],reverse=True)
                deletions=sorted([r for r in group if r['parameters']['search_label'].startswith('heldout-delete-')],key=lambda r:int(r['parameters']['search_label'].rsplit('-',1)[1]))
                selected=controls+[deletions[i] for i in sorted({0,len(deletions)//2,len(deletions)-1})] if deletions else controls
                boxes=[]
                for r in selected:
                    st=r['statistics'];label=r['parameters']['search_label'].replace('heldout-','').replace('delete-','D')
                    boxes.append(dict(med=st['median'],q1=st['q1'],q3=st['q3'],whislo=st['p05'],whishi=st['p95'],fliers=[],label=label+('*' if r['qualification']=='noisy' else '')))
                    sources.append(r['record_path'])
                ax.bxp(boxes,showfliers=False,medianprops=dict(color='black'));ax.tick_params(axis='x',labelsize=7)
                ax.set_ylabel(group[0]['measurement']['unit']+'/reload',fontsize=8);ax.set_title(str(stride//1024)+' KiB stride; seed '+str(seed),fontsize=8)
                ax.set_xlabel('Hot / full / deletion index (first, middle, last)',fontsize=7)
            for ax in list(axes.flat)[len(items[page:page+6]):]:ax.set_visible(False)
            save(fig,'empirical-heldout-boxes-'+str(page//6+1),sources)
    cross=[r for r in rows if r['family']=='cross_core_reload']
    if cross:
        fig,ax=plt.subplots(figsize=(10,4));cross.sort(key=lambda r:(r['parameters']['bytes'],r['parameters']['seed'],r['parameters']['offset']))
        boxes=[dict(med=r['statistics']['median'],q1=r['statistics']['q1'],q3=r['statistics']['q3'],whislo=r['statistics']['p05'],whishi=r['statistics']['p95'],fliers=[],label=str(r['parameters']['bytes']//1024)+'K\n'+('pressure' if r['parameters']['offset'] else 'control')+('*' if r['qualification']=='noisy' else '')) for r in cross]
        ax.bxp(boxes,showfliers=False,medianprops=dict(color='black'));ax.tick_params(axis='x',labelsize=7);ax.set_ylabel(cross[0]['measurement']['unit']+'/target reload');ax.set_title(host+': remote-pressure and handshake-only distributions')
        save(fig,'cross-core-reload',[r['record_path'] for r in cross])
    lower=[r for r in rows if r['family'] in ('l2_conflict','l2_upper_calibration')]
    if lower:
        fig,axes=plt.subplots(1,2,figsize=(10,4))
        cal=sorted([r for r in lower if r['family']=='l2_upper_calibration' and r['parameters']['mode']=='probe'],key=lambda r:r['parameters']['upper_scrub_count'])
        if cal:
            boxes=[dict(med=r['statistics']['median'],q1=r['statistics']['q1'],q3=r['statistics']['q3'],whislo=r['statistics']['p05'],whishi=r['statistics']['p95'],fliers=[],label=str(r['parameters']['upper_scrub_count'])+('*' if r['qualification']=='noisy' else '')) for r in cal]
            axes[0].bxp(boxes,showfliers=False,medianprops=dict(color='black'))
        axes[0].set_xlabel('Fixed upper-scrub addresses');axes[0].set_ylabel(lower[0]['measurement']['unit']+'/target reload');axes[0].set_title('Upper-eviction calibration')
        strides=sorted({r['parameters']['l2_candidate_stride'] for r in lower if r['family']=='l2_conflict'})
        shapes=['o','s','^','D','v','P','X']
        for j,stride in enumerate(strides):
            group=sorted([r for r in lower if r['family']=='l2_conflict' and r['parameters']['l2_candidate_stride']==stride and r['parameters']['l2_label']=='coarse'],key=lambda r:r['parameters']['l2_candidate_count'])
            x=[r['parameters']['l2_candidate_count'] for r in group]
            y=[(sorted(r['block_means'])[4]+sorted(r['block_means'])[5])/2 for r in group]
            color=str(.65*j/max(1,len(strides)-1))
            axes[1].plot(x,y,marker=shapes[j%len(shapes)],color=color,markersize=3,label=str(stride//1024)+' KiB stride')
            axes[1].fill_between(x,[min(r['block_means']) for r in group],[max(r['block_means']) for r in group],color=color,alpha=.13)
            for r,v in zip(group,y):
                if r['qualification']=='noisy':axes[1].plot(r['parameters']['l2_candidate_count'],v,'x',color='black')
        axes[1].set_xlabel('Variable lower-candidate addresses');axes[1].set_ylabel('Median of block means ('+lower[0]['measurement']['unit']+')');axes[1].set_title('Upper pressure held fixed');axes[1].legend(fontsize=7)
        save(fig,'l2-controlled-conflicts',[r['record_path'] for r in lower])
        groups=collections.defaultdict(list)
        for r in lower:
            p=r['parameters']
            if p['l2_label']=='heldout-refinement':groups[p['l2_candidate_stride'],p['upper_scrub_variant'],p['seed'],p.get('calibration_repetition',0)].append(r)
        for r in rows:
            if r['family']=='l2_strong_conflict':
                p=r['parameters'];groups[p['l2_candidate_stride'],p['upper_scrub_variant'],p['seed'],p.get('calibration_repetition',0)].append(r)
        items=sorted(groups.items())
        for page in range(0,len(items),6):
            fig,axes=plt.subplots(2,3,figsize=(10,6));sources=[]
            for ax,((stride,variant,seed,rep),group) in zip(axes.flat,items[page:page+6]):
                group.sort(key=lambda r:r['parameters']['l2_candidate_count'])
                boxes=[dict(med=r['statistics']['median'],q1=r['statistics']['q1'],q3=r['statistics']['q3'],whislo=r['statistics']['p05'],whishi=r['statistics']['p95'],fliers=[],label=str(r['parameters']['l2_candidate_count'])+('*' if r['qualification']=='noisy' else '')) for r in group]
                ax.bxp(boxes,showfliers=False,medianprops=dict(color='black'));ax.set_xlabel('Lower-candidate addresses')
                ax.set_ylabel(group[0]['measurement']['unit']+'/reload',fontsize=8);ax.set_title(str(stride//1024)+' KiB, pattern '+str(variant)+', scrub N='+str(group[0]['parameters']['upper_scrub_count'])+', seed '+str(seed),fontsize=7)
                sources.extend(r['record_path'] for r in group)
            for ax in list(axes.flat)[len(items[page:page+6]):]:ax.set_visible(False)
            save(fig,'l2-heldout-boxes-'+str(page//6+1),sources)
    saturation=[r for r in rows if r['family']=='l2_saturation']
    if saturation:
        groups=collections.defaultdict(list)
        for r in saturation:
            p=r['parameters'];groups[p['l2_label'],p['upper_scrub_variant'],p['seed'],p['calibration_repetition']].append(r)
        items=sorted(groups.items())
        for page in range(0,len(items),6):
            fig,axes=plt.subplots(2,3,figsize=(10,6));sources=[]
            for ax,((label,variant,seed,rep),group) in zip(axes.flat,items[page:page+6]):
                group.sort(key=lambda r:r['parameters']['upper_scrub_count'])
                boxes=[dict(med=r['statistics']['median'],q1=r['statistics']['q1'],q3=r['statistics']['q3'],whislo=r['statistics']['p05'],whishi=r['statistics']['p95'],fliers=[],label=str(r['parameters']['upper_scrub_count'])+('*' if r['qualification']=='noisy' else '')) for r in group]
                ax.bxp(boxes,showfliers=False,medianprops=dict(color='black'));ax.set_xlabel('Upper scrub addresses')
                ax.set_ylabel(group[0]['measurement']['unit']+'/reload',fontsize=8)
                ax.set_title(label.replace('saturation-','')+', pattern '+str(variant)+', seed '+str(seed),fontsize=7)
                sources.extend(r['record_path'] for r in group)
            for ax in list(axes.flat)[len(items[page:page+6]):]:ax.set_visible(False)
            save(fig,'upper-saturation-boxes-'+str(page//6+1),sources)
    inference=json.loads((ROOT/'data_processed/followup'/(host+'-inference.json')).read_text())
    models=inference['capacity']['plateau_models']
    if models and all('representative' in segment for model in models for segment in model['segments']):
        fig,axes=plt.subplots(1,len(models),figsize=(10,4),squeeze=False);sources=[]
        for ax,model in zip(axes[0],models):
            boxes=[]
            for segment in model['segments']:
                r=segment['representative'];st=r['statistics'];sources.append(r['source'])
                boxes.append(dict(med=st['median'],q1=st['q1'],q3=st['q3'],whislo=st['p05'],whishi=st['p95'],fliers=[],label=str(segment['class_index'])+' / '+str(r['working_set_bytes']//1024)+'K'))
            ax.bxp(boxes,showfliers=False,medianprops=dict(color='black'));ax.set_yscale('log',base=2)
            ax.set_xlabel('Effective class / representative footprint');ax.set_ylabel(model['segments'][0]['representative']['unit'])
            ax.set_title('Huge-backed spacing '+str(model['stride'])+' B');ax.tick_params(axis='x',labelsize=7)
        save(fig,'latency-classes',sources)
    return saved

def main():
    global ROOT, PROCESSED
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace",type=Path,required=True)
    ap.add_argument("--hosts",nargs="+")
    args=ap.parse_args()
    ROOT=args.workspace.resolve()
    clone=Path(__file__).resolve().parents[4]
    if ROOT==clone or clone in ROOT.parents:
        ap.error("Use an external restored experiment workspace")
    PROCESSED=ROOT/"data_processed/uncertainty"
    allowed=json.loads((ROOT/"config/phase1.json").read_text())["hosts"]
    if set(args.hosts or allowed)-set(allowed):ap.error("Unknown host")
    for host in args.hosts or allowed:
        rows=json.loads((ROOT/"data_processed/followup"/(host+"-verified-records.json")).read_text())
        figures(host,rows)

if __name__=="__main__":main()
