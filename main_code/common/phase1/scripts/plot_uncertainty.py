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
    plt.style.use('grayscale')
    directory=ROOT/'plots/uncertainty';directory.mkdir(parents=True,exist_ok=True)
    saved=[]
    def save(fig,name,sources,layout_rect=None):
        fig.suptitle(host+(' | full observed timing tails; no trimming' if name=='distribution-tails' else ' | timing only | medians and IQR; quality flags retained'),fontsize=10)
        fig.tight_layout(rect=layout_rect);base=directory/(host+'-'+name)
        for extension in ('svg',):fig.savefig(str(base)+'.'+extension,dpi=150)
        plt.close(fig)
        description=('Exact empirical tail frequencies from the complete raw distributions; zero intervals stated separately from the logarithmic axis. First chronological clean distribution per shown family, or first noisy distribution if none is clean.' if name=='distribution-tails' else 'Native median/IQR; boxes use P05/P95 whiskers. All outliers remain in raw files.')
        write_json(str(base)+'.provenance.json',dict(time=now(),sources=sources,statistics=description))
        provenance=json.loads(Path(str(base)+'.provenance.json').read_text())
        cohort_file=('capacity-matched.json' if name.startswith('capacity-matched') else 'spatial-cohorts.json' if name.startswith('spatial') else 'conflict-repair.json' if name.startswith('conflict') else None)
        provenance['comparison_cohort_policy']=('machines/'+host+'/uncertainty-v1/'+cohort_file+' (when present); all attempted cohorts retained, first clean same-core cohort supports inference' if cohort_file else 'First chronological clean distribution per configuration, otherwise first retained noisy distribution; comparison qualifications are in the host inference JSON')
        write_json(str(base)+'.provenance.json',provenance)
        saved.append(dict(name=name,file=str(base.with_suffix('.svg').relative_to(ROOT)),sources=sources))
    def curve(ax,g,axis,label,scale=1,marker='o',style_index=None):
        g=sorted(g,key=lambda r:r['parameters'][axis]);x=[r['parameters'][axis]/scale for r in g]
        y=[r['statistics']['median'] for r in g]
        index=len(ax.get_legend_handles_labels()[1]) if style_index is None else style_index
        color=str(.13*(index%6))
        marker=('o','s','^','D','v','P')[index%6]
        ax.plot(x,y,marker=marker,markersize=3,label=label,color=color,linestyle=('-','--',':','-.')[index%4])
        ax.fill_between(x,[r['statistics']['q1'] for r in g],[r['statistics']['q3'] for r in g],color=color,alpha=.13)
        for x0,r in zip(x,g):
            if r['qualification']!='clean' or r.get('comparison_accepted') is False:ax.plot(x0,r['statistics']['median'],'kx',markersize=8)
        if g:ax.set_ylabel(g[0]['statistic_unit'])
    conflicts=[r for r in rows if r['family']=='batched_conflict']
    for scrub in sorted({r['parameters']['scrub_count'] for r in conflicts}):
        g=[r for r in conflicts if r['parameters']['scrub_count']==scrub];strides=sorted({r['parameters']['conflict_stride'] for r in g})
        all_keys=sorted({(r['parameters']['series'],r['parameters']['seed'],r['parameters']['variant']) for r in g})
        fig,axes=plt.subplots(2,3,figsize=(8,4.8))
        legend={}
        for ax,stride in zip(axes.flat,strides):
            local=[r for r in g if r['parameters']['conflict_stride']==stride]
            keys=sorted({(r['parameters']['series'],r['parameters']['seed'],r['parameters']['variant']) for r in local})
            for series,seed,variant in keys:
                chosen=[r for r in local if (r['parameters']['series'],r['parameters']['seed'],r['parameters']['variant'])==(series,seed,variant)]
                curve(ax,chosen,'candidate_count',{'discovery':'D','heldout':'H','discovery-repair':'RD','repair-heldout':'RH'}.get(series,series)+str(seed)+'/P'+str(variant),style_index=all_keys.index((series,seed,variant)))
            ax.set_title(str(stride//1024)+' KiB stride; '+str(scrub)+' scrub nodes',fontsize=8);ax.set_xlabel('Live candidate nodes')
            handles,labels=ax.get_legend_handles_labels()
            legend.update(zip(labels,handles))
        for ax in list(axes.flat)[len(strides):]:ax.set_visible(False)
        fig.legend(list(legend.values()),list(legend),loc='lower center',fontsize=7.5,ncol=5)
        save(fig,'conflicts-scrub-'+str(scrub),[r['record_path'] for r in g],layout_rect=(0,.14,1,1))
    capacity=[r for r in rows if r['family'] in ('capacity_repeat','capacity_regular_repeat')]
    if capacity:
        fig,axes=plt.subplots(1,2,figsize=(8,3.2))
        for ax,page in zip(axes,('huge','base')):
            for seed in sorted({r['parameters']['seed'] for r in capacity}):
                for family,marker in (('capacity_repeat','o'),('capacity_regular_repeat','s')):
                    g=[r for r in capacity if r['parameters']['seed']==seed and r['parameters']['page']==page and r['family']==family]
                    curve(ax,g,'bytes',('random ' if family=='capacity_repeat' else 'regular ')+str(seed),1048576,marker)
            ax.set_xlabel('Logical working set (MiB)');ax.set_title(page+' page policy');ax.legend(fontsize=8)
        save(fig,'capacity',[r['record_path'] for r in capacity])
    matched=collections.defaultdict(list)
    for r in rows:
        if r['family']=='capacity_matched':
            p=r['parameters'];matched[p['page'],p['seed'],tuple(p['repair_interval']),p['series'],p['repair_repetition']].append(r)
    items=sorted(matched.items())
    for start in range(0,len(items),4):
        fig,axes=plt.subplots(2,2,figsize=(8,4.8));sources=[]
        for ax,((page,seed,interval,series,rep),g) in zip(axes.flat,items[start:start+4]):
            g.sort(key=lambda r:r['parameters']['bytes']);boxes=[]
            for r in g:
                st=r['statistics'];mark='*' if r['qualification']!='clean' or r.get('comparison_accepted') is False else ''
                boxes.append(dict(med=st['median'],q1=st['q1'],q3=st['q3'],whislo=st['p05'],whishi=st['p95'],fliers=[],label=format(r['parameters']['bytes']/1048576,'.5g')+mark))
                sources.append(r['record_path'])
            ax.bxp(boxes,showfliers=False);ax.set_xlabel('MiB; * = noisy/unaccepted cohort');ax.set_ylabel(g[0]['statistic_unit'])
            ax.set_title(page+'; seed '+str(seed)+'; '+series+'; repeat '+str(rep),fontsize=8)
        for ax in list(axes.flat)[len(items[start:start+4]):]:ax.set_visible(False)
        save(fig,'capacity-matched-'+str(start//4+1),sources)
    spatial=[r for r in rows if r['family']=='spatial_residency']
    groups=collections.defaultdict(list)
    for r in spatial:
        p=r['parameters'];groups[p['bytes'],p['align'],p['seed'],p['cohort_repetition']].append(r)
    items=sorted(groups.items())
    for start in range(0,len(items),4):
        fig,axes=plt.subplots(2,2,figsize=(8,4.8));sources=[]
        for ax,((w,a,s,rep),g) in zip(axes.flat,items[start:start+4]):
            g.sort(key=lambda r:r['parameters']['offset']);boxes=[]
            for r in g:
                st=r['statistics'];boxes.append(dict(med=st['median'],q1=st['q1'],q3=st['q3'],whislo=st['p05'],whishi=st['p95'],fliers=[],label=str(r['parameters']['offset'])+('*' if r['qualification']!='clean' else '')))
                sources.append(r['record_path'])
            ax.bxp(boxes,showfliers=False);ax.set_xlabel('Pair offset (B); * = noisy');ax.set_ylabel(g[0]['statistic_unit'])
            ax.set_title(str(w//1024)+' KiB allocation; align '+str(a)+'; seed '+str(s)+'; repeat '+str(rep),fontsize=8)
        for ax in list(axes.flat)[len(items[start:start+4]):]:ax.set_visible(False)
        save(fig,'spatial-'+str(start//4+1),sources)
    # Dense local boxes for every replicated effective conflict boundary.
    inference=json.loads((PROCESSED/(host+'-inference.json')).read_text())
    for index,edge in enumerate(inference['conflict']['repeated_thresholds']):
        g=[r for r in conflicts if r['record_path'] in edge['sources']]
        if not g:continue
        fig,ax=plt.subplots(figsize=(8,2.4));boxes=[]
        for r in sorted(g,key=lambda r:(r['parameters']['seed'],r['parameters']['variant'],r['parameters']['candidate_count'])):
            p=r['parameters'];st=r['statistics']
            boxes.append(dict(med=st['median'],q1=st['q1'],q3=st['q3'],whislo=st['p05'],whishi=st['p95'],fliers=[],label=str(p['candidate_count'])+'\ns'+str(p['seed'])+'v'+str(p['variant'])))
        ax.bxp(boxes,showfliers=False);ax.tick_params(axis='x',labelsize=6);ax.set_ylabel(g[0]['statistic_unit'])
        ax.set_xlabel('Live candidates / seed / scrub pattern');ax.set_title('Repeated effective threshold '+str(edge['interval'])+'; stride '+str(edge['stride']//1024)+' KiB')
        save(fig,'conflict-box-'+str(index+1),edge['sources'])
    representatives=[]
    for family in ('spatial_residency','capacity_repeat','batched_conflict'):
        group=sorted([r for r in rows if r['family']==family],key=lambda r:r['started'])
        clean=[r for r in group if r['qualification']=='clean']
        if group:representatives.append((clean or group)[0])
    if representatives:
        fig,ax=plt.subplots(figsize=(8,3.2));zeros=[]
        for index,r in enumerate(representatives):
            values=read_raw(ROOT/r['raw_path'],r['measurement']['little_endian']);counts=collections.Counter(values)
            remaining=len(values);x=[];y=[];divisor=r['parameters']['batch']
            for value,count in sorted(counts.items()):
                if value>0:x.append(value/divisor);y.append(remaining/len(values))
                remaining-=count
            if x:
                ax.step(x,y,where='post',label=r['family']+('*' if r['qualification']!='clean' else ''),linestyle=('-','--',':')[index],color=str(index*.25))
                ax.plot(x[-1],y[-1],'o',color=str(index*.25),markersize=3)
            zeros.append(r['family']+': '+str(counts.get(0,0)))
        ax.set_xscale('log');ax.set_yscale('log');ax.set_xlabel(representatives[0]['statistic_unit']);ax.set_ylabel('Empirical fraction >= observed time')
        ax.set_title('Full observed tails; first chronological clean distribution per family\nZero intervals (outside logarithmic x axis): '+', '.join(zeros),fontsize=9)
        ax.legend(fontsize=8);save(fig,'distribution-tails',[r['record_path'] for r in representatives])
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
        rows=json.loads((ROOT/"data_processed/uncertainty"/(host+"-selected.json")).read_text())
        figures(host,rows)

if __name__=="__main__":main()
