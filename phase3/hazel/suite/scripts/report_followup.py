#!/usr/bin/env python3
"""Render second-round evidence and a revised Phase-I report; preserve the baseline."""
import argparse
import collections
import html
import json
from pathlib import Path
import textwrap
from common import now, sha, write_json

ROOT=Path(__file__).resolve().parents[1]


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
        for ext in ('png','pdf','svg'):fig.savefig(str(base)+'.'+ext,dpi=150)
        plt.close(fig)
        write_json(str(base)+'.provenance.json',dict(time=now(),records=sources,
            statistic='Median of ten chronological block means with min/max block-mean band on lower-conflict panel; raw quantile boxes on upper-calibration panel' if name=='l2-controlled-conflicts' else 'Native median and IQR; box whiskers P05/P95; outliers retained in raw data',
            note='Raw-recomputed distributions. Asterisks on box labels and crosses on curve panels mark noisy selected points; exact qualification and flags accompany every source. No data editing or specification inputs.'))
        saved.append(base.with_suffix('.png'))
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
    cross=[r for r in rows if r['family'] in ('cross_core_reload','cross_core_reload_final')]
    if cross:
        fig,ax=plt.subplots(figsize=(10,4));cross.sort(key=lambda r:(r['parameters']['bytes'],r['parameters']['seed'],r['parameters']['offset']))
        boxes=[dict(med=r['statistics']['median'],q1=r['statistics']['q1'],q3=r['statistics']['q3'],whislo=r['statistics']['p05'],whishi=r['statistics']['p95'],fliers=[],label=('post' if r['family'].endswith('_final') else 'early')+'\n'+str(r['parameters']['bytes']//1024)+'K\n'+('pressure' if r['parameters']['offset'] else 'control')+('*' if r['qualification']=='noisy' else '')) for r in cross]
        ax.bxp(boxes,showfliers=False,medianprops=dict(color='black'));ax.tick_params(axis='x',labelsize=7);ax.set_ylabel(cross[0]['measurement']['unit']+'/target reload');ax.set_title(host+': early and post-refinement remote-pressure controls')
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
    ap=argparse.ArgumentParser();ap.add_argument('--draft',action='store_true');args=ap.parse_args()
    state=json.loads((ROOT/'data_processed/followup/verification.json').read_text())
    if not state['complete'] and not args.draft:raise SystemExit('Final report requires complete follow-up verification')
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Image,Preformatted,Table,TableStyle
    styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='PhaseCode',fontName='Courier',fontSize=5.5,leading=6.5))
    story=[];summary=['# Phase-I follow-up findings','', 'Status: '+('working draft' if args.draft else 'verified measurement round')+'. No Phase II.','']
    def para(text,style='BodyText'):story.append(Paragraph(html.escape(text),styles[style]));story.append(Spacer(1,6))
    para('Phase I: follow-up experiments and revised evidence','Title')
    para('Working draft' if args.draft else 'Verified timing-only follow-up','Heading2')
    para('This supplement revisits the unresolved fields in the baseline report. The original report and raw data remain preserved. Neither complete acquisition nor an uncertain classification alone establishes a physical cache specification.')
    para('The baseline archive is artifacts/phase1-timing-only.zip. This follow-up uses machines/HOST/followup-v1, data_processed/followup, and plots/followup. Every configuration, including discovery trials, contains at least one million timed intervals. Raw data, unsuccessful attempts, seeds, source snapshots, page backing and affinity evidence remain available.')
    methods=[('Spatial granularity','Shift the base address by 0 and 24 bytes while sweeping pair offset at fixed allocation and node count. Find the smallest repeated absolute boundary, allowing larger secondary transitions. Independently repeat below/at/above the candidate with shifts 0, 24 and 40, two new seeds, and two footprints. A confirmation uses the first clean triplet entirely on one core; at most three group attempts are retained.'),
      ('Hierarchy and translation controls','Sweep 1 KiB through 256 MiB using ordinary-page dense, huge-page dense, and huge-page sparse dependent cycles. The sparse spacing is a timing-derived spatial hypothesis. Confirm actual huge backing from the process mapping. Refine every coarse sparse-huge median jump above 20 percent with seven interior points, both page policies, and regular-traversal endpoints. Infer physical roles only after comparing transitions and distributions.'),
      ('Empirical conflicts','Warm a target and time its reload after visiting a candidate pressure set. Start with page-offset-related virtual addresses; remove chunks while retaining a predeclared fraction of the observed full-pool slowdown. Every training measurement is retained. Re-test the selected set and individual deletions with new seeds and mappings. Remapping can change physical congruence; a replicated eviction bound is not automatically associativity.'),
      ('Remote eviction pressure','Select two idle physical cores on the same socket, with every SMT sibling idle. Warm the target only on the measuring core, ask the helper to execute 1024 dependent pressure loads, and time the target reload. Compare with identical handshake-only controls, same-core pressure and hot-target calibration. Repeat across pressure footprints and seeds. No helper pressure address intentionally contains the target. This removes intentional direct upper-cache pressure, but does not independently guarantee lower-cache target eviction.'),
      ('Quality and blindness','Use the original serialized architectural timers and register-only dependency loop, compiled at -O0. Atomics synchronize outside the measured reload interval. The controller waits indefinitely for idle cores and changes cores when necessary. Raw data are never altered; quality warnings are retained. No hardware event counters, cache-reporting interfaces or external cache answers are used.')]
    from reportlab.graphics.shapes import Drawing,Rect,String,Line
    diagram_labels=[['Random A -> A+offset','Shift A alignment','Measure dense offsets','Confirm smallest boundary'],
        ['Pin, map and first-touch','Change page policy / spacing','Sweep and refine W','Compare latency classes'],
        ['Warm target T','Traverse candidate addresses','Time T; delete chunks','Validate new seed / mapping'],
        ['Warm T on core A','Core B: pressure / control','A: time target reload','Compare pairs and seeds'],
        ['Check every SMT sibling','Wait / select idle cores','Run -O0 dependent kernel','Verify all raw data']]
    for (title,body),labels in zip(methods,diagram_labels):
        para(title,'Heading2');para(body)
        drawing=Drawing(510,65)
        for i,label in enumerate(labels):
            x=(i%2)*255;y=35-(i//2)*32
            drawing.add(Rect(x,y,245,25,fillColor=colors.white,strokeColor=colors.black))
            drawing.add(String(x+5,y+9,label,fontSize=8))
        story.append(drawing)
    metadata=json.loads((ROOT/'data_processed/followup/metadata-reference-audit.json').read_text())
    para('Metadata and functional-smoke audit: '+str(metadata['records'])+' records checked, '+str(metadata['smoke_distributions_recomputed'])+' smoke distributions independently recomputed. '+str(len(metadata['historical_reference_resolutions']))+' historical conflict-smoke metadata references omitted a parent-path prefix; the original records remain unchanged and explicit resolutions are recorded in data_processed/followup/metadata-reference-audit.json. Reproduction code now writes the correct relative references.')
    para('Reload diagnostics retain the -O0 timer, function-call and volatile-sink overhead in both pressure and control conditions. Their relative distributions and slow-tail fractions are the evidence; their raw absolute medians are not pure single-cache hit latencies. The primary batched dependency loop remains load-only. One million intervals sharing a cache state are not one million independent experimental replications.')
    for host,d in state['hosts'].items():
        story.append(PageBreak());para(host,'Heading1')
        para(str(d['verified_points'])+' verified points; '+str(d['noisy_points'])+' selected distributions remain noisy; '+str(d['attempts'])+' retained attempts, including '+str(sum(bool(a.get('flags')) for a in d['unsuccessful']))+' flagged attempts. Missing stages: '+str(d['missing_stages'])+'. Every unsuccessful attempt and its explanation is listed in the per-host inference JSON.')
        line=d['spatial']['candidate_bytes'];confirmation=d['spatial_confirmation']
        finding='Spatial sweep candidate: '+str(line)+' bytes. Independent same-core confirmation: '+confirmation['status']+'.'
        para(finding);summary.extend(['## '+host,'',finding,''])
        cache_rows=[['Timing role','Capacity interval (B)','Line / ways / sets']]
        for row in d.get('revised_cache_table',[]):
            cache_rows.append([row['role'],str(row['capacity_interval_bytes']),
                str(row['line_candidate_bytes'])+' / '+str(row['ways_candidate'])+' / '+str(row['derived_sets'])])
        tab=Table([[Paragraph(html.escape(str(v)),styles['BodyText']) for v in row] for row in cache_rows],colWidths=[145,190,175]);tab.setStyle(TableStyle([('LINEBELOW',(0,0),(-1,0),1,colors.black),('VALIGN',(0,0),(-1,-1),'TOP')]));story.append(tab)
        para('None means unresolved. Numerical entries are conditional timing candidates. L1 conflict thresholds are now cross-checked against the independently measured capacity interval before resolving competing thresholds; this revises the inference, not the raw measurements. A tested stride is not proven fundamental. Deeper physical-role brackets come from dense/sparse huge-backed timing classes and may include mixed residency.')
        summary.extend(['| Conditional role | Capacity bracket (KiB) | Line candidate (B) | Ways candidate |', '|---|---:|---:|---:|'])
        for row in d.get('revised_cache_table',[]):
            band=row['capacity_interval_bytes'];bracket='unresolved' if band is None else '–'.join(format(v/1024,'.6g') for v in band)
            summary.append('| '+row['role']+' | '+bracket+' | '+str(row['line_candidate_bytes'])+' | '+str(row['ways_candidate'])+' |')
        summary.extend(['','None means unresolved. These are conditional timing candidates, not independently verified cache specifications. Full table: `data_processed/followup/revised-cache-table.csv`; latency distributions and transition differences: `data_processed/followup/latency-classes.csv`.',''])
        if 'supported_cohorts' in confirmation:para(str(confirmation['supported_cohorts'])+' of '+str(confirmation['total_cohorts'])+' confirmation triplets supported the candidate. The offset sweep has 8-byte resolution; the candidate is a transfer granularity visible in this workload.')
        bounds=[(s['stride'],s.get('replicated_effective_eviction_bound')) for s in d['conflict'].get('searches',[])]
        para('Empirical conflict results (pool stride, replicated pressure-address bound): '+str(bounds)+'. Bounds describe target slowdown under the measured construction, not verified physical ways.')
        summary.extend(['Empirical eviction bounds (stride B, pressure addresses): '+str(bounds)+'.',''])
        table=[['Page / spacing','Candidate intervals (KiB)','Same-core endpoints']]
        for curve in d['capacity']['curves']:
            edges=curve['edges'];table.append([curve['page']+' / '+str(curve['stride']),'; '.join(str(round(e['lower_bytes']/1024,2))+'-'+str(round(e['upper_bytes']/1024,2)) for e in edges),str(sum(e['same_cpu'] for e in edges))+'/'+str(len(edges))])
        tab=Table([[Paragraph(html.escape(str(x)),styles['BodyText']) for x in r] for r in table],colWidths=[95,330,85]);tab.setStyle(TableStyle([('LINEBELOW',(0,0),(-1,0),1,colors.black),('VALIGN',(0,0),(-1,-1),'TOP')]));story.append(tab)
        para('These are measured effective residency transitions. The table records changes without treating each one as a distinct physical cache level. Full below/above distributions and backing evidence are in the per-host inference JSON.')
        para(d['capacity'].get('hierarchy_status','Hierarchy interpretation pending'))
        prefetch=d.get('prefetch',{})
        if prefetch.get('comparisons'):
            rows_prefetch=[['W KiB','Regular median','Random median','Ratio','Same core / clean']]
            for pair in prefetch['comparisons']:
                rows_prefetch.append([format(pair['bytes']/1024,'.6g'),format(pair['regular']['median'],'.5g'),format(pair['randomized']['median'],'.5g'),format(pair['regular_over_randomized_median'],'.4g'),str(pair['same_cpu'])+' / '+str(pair['clean'])])
            t=Table(rows_prefetch,colWidths=[80,105,105,65,155]);t.setStyle(TableStyle([('LINEBELOW',(0,0),(-1,0),1,colors.black),('FONTSIZE',(0,0),(-1,-1),8)]));story.append(t)
            para(prefetch['choice']+' Full distributions are retained in the per-host inference JSON and statistics CSV.')
        for model in d['capacity'].get('plateau_models',[]):
            para('Huge-backed spacing '+str(model['stride'])+' B: BIC selected '+str(model['chosen_classes'])+' effective timing classes; class-change brackets '+str(model['boundaries_bytes'])+' bytes. '+model['limitation'])
            if all('representative' in segment for segment in model['segments']):
                latency_table=[['Class / W KiB','Median [P05, P95]','Mean / SD','Q1 / Q3','Outliers / N','Delta median']]
                for segment in model['segments']:
                    representative=segment['representative'];st=representative['statistics'];transition=segment.get('transition_from_previous',{})
                    fmt=lambda x:format(x,'.4g') if x is not None else 'unresolved'
                    latency_table.append([str(segment['class_index'])+' / '+fmt(representative['working_set_bytes']/1024),
                        fmt(st['median'])+' ['+fmt(st['p05'])+', '+fmt(st['p95'])+']',fmt(st['mean'])+' / '+fmt(st['stddev']),
                        fmt(st['q1'])+' / '+fmt(st['q3']),str(st['outliers'])+' / '+str(st['n']),fmt(transition.get('incremental_median_penalty'))])
                t=Table(latency_table,colWidths=[67,123,87,78,92,63]);t.setStyle(TableStyle([('LINEBELOW',(0,0),(-1,0),1,colors.black),('FONTSIZE',(0,0),(-1,-1),7)]));story.append(t)
                para('Units: '+model['segments'][0]['representative']['unit']+'. '+model['representative_rule']+'. Delta is the difference from the preceding representative median only when both use the same core. These are effective dependent-access classes, conditional on the stated hierarchy interpretation; they do not isolate individual hardware miss penalties. Full distributions and source paths: data_processed/followup/latency-classes.csv.')
        para(d['cross_core']['limitation'])
        lower=d.get('l2_specific',{})
        para('Fixed upper pressure / lower-conflict test','Heading2')
        para('The upper scrub uses odd multiples of the timing-derived L1 indexing period; target and lower candidates differ in the next virtual index bit. Its calibration includes a one-address same-protocol control. The lower scan then keeps that upper pressure fixed, varies lower-candidate counts, and repeats refined transitions with two scrub patterns and two new seeds.')
        para('Upper-scrub timing class calibrated: '+str(lower.get('upper_scrub_calibrated'))+'. Fully replicated lower thresholds (stride, pressure-address count): '+str([(s['stride'],s['fully_replicated_thresholds']) for s in lower.get('strides',[])])+'.')
        para(lower.get('limitation','Measurement pending'))
        stronger=d.get('l2_confirmation',{})
        para('Stronger-scrub confirmation: selected upper count '+str(stronger.get('selected_scrub_count'))+'; all four independent calibration conditions passed: '+str(stronger.get('upper_scrub_calibrated'))+'. Repeated thresholds (stride B, N): '+str([(s['stride'],s['fully_replicated_thresholds']) for s in stronger.get('strides',[])])+'.')
        para(stronger.get('search_rule','Pending stronger-scrub calibration'))
        for calibration in stronger.get('calibrations',[]):
            if calibration.get('failures'):para('Calibration pattern '+str(calibration['variant'])+', seed '+str(calibration['seed'])+': '+'; '.join(calibration['failures'])+'. Centers (one / selected / selected+4): '+str(calibration['centers'])+'.')
        lower_row=next((row for row in d.get('revised_cache_table',[]) if row['role'].startswith('L2')),None)
        if lower_row:
            para('L2 way-count assessment: '+lower_row.get('way_inference_status','Pending')+'.')
            for candidate in lower_row.get('joint_l2_candidates',[]):
                para('Conditional sets if the measured spatial granularity also applies to L2: '+str(candidate['conditional_sets_if_spatial_granularity_is_l2_line_size'])+'. Separate per-level line size remains unverified.')
        summary.extend(['Upper-scrub confirmation: '+str(stronger.get('upper_scrub_calibrated'))+'; repeated lower-conflict thresholds (stride B, N): '+str([(s['stride'],s['fully_replicated_thresholds']) for s in stronger.get('strides',[])])+'.',''])
        if d['cross_core']['comparisons']:
            tail_table=[['Pressure KiB / seed','Control slow %','Pressure slow %','Same pair / clean']]
            for pair in d['cross_core']['comparisons']:
                if pair.get('tails'):
                    tail_table.append([str(pair['bytes']//1024)+' / '+str(pair['seed']),
                        format(100*pair['tails']['control']['fraction_above_threshold'],'.4f'),
                        format(100*pair['tails']['pressure']['fraction_above_threshold'],'.4f'),
                        str(pair['same_pair'])+' / '+str(pair['clean'])])
            t=Table(tail_table,colWidths=[160,105,105,140]);t.setStyle(TableStyle([('LINEBELOW',(0,0),(-1,0),1,colors.black),('FONTSIZE',(0,0),(-1,-1),8)]));story.append(t)
            para('Slow means above that comparison\'s handshake-only control P99 threshold. This is a timing-tail fraction, not a hardware miss rate. Full chronological block ranges and raw thresholds are retained in the host inference JSON; rare effects can be invisible in medians.')
        summary.extend(['Inclusion/exclusion: '+d['cross_core']['status']+'.',''])
        rows=json.loads((ROOT/'data_processed/followup'/(host+'-verified-records.json')).read_text())
        for figure in figures(host,rows):
            story.append(Image(str(figure),width=510,height=306 if 'boxes' in figure.name else 204))
            info=json.loads(figure.with_suffix('.provenance.json').read_text())
            para(str(figure.relative_to(ROOT))+'. '+info['statistic']+'. Asterisks on box labels and crosses on curve panels mark noisy selections. All outliers remain in raw data. Exact sources accompany the figure.')
    story.append(PageBreak());para('Complete added implementations','Heading1')
    para('followup_bench.c includes the unchanged cache_bench.c, whose complete implementation appears in the preserved baseline report. The following complete added implementations and producing source snapshots make this round reproducible. Long source lines wrap for display only.')
    for name in ('src/followup_bench.c','scripts/followup_worker.py','scripts/worker.py','scripts/common.py','scripts/followup.py','scripts/analyze_followup.py'):
        para(name,'Heading2')
        text=(ROOT/name).read_text();lines=[]
        for line in text.splitlines():lines.extend(textwrap.wrap(line,width=145,replace_whitespace=False,drop_whitespace=False) or [''])
        for start in range(0,len(lines),65):story.append(Preformatted('\n'.join(lines[start:start+65]),styles['PhaseCode']))
    directory=ROOT/'report/followup';directory.mkdir(parents=True,exist_ok=True)
    destination=directory/'phase1-followup-report.pdf'
    SimpleDocTemplate(str(destination),rightMargin=40,leftMargin=40,topMargin=40,bottomMargin=40).build(story)
    (directory/'inference-summary.md').write_text('\n'.join(summary)+'\n')
    if not args.draft:
        from pypdf import PdfReader,PdfWriter
        from reportlab.pdfgen import canvas
        import io
        writer=PdfWriter()
        for page in PdfReader(str(destination)).pages:writer.add_page(page)
        separator=io.BytesIO();c=canvas.Canvas(separator)
        c.setFont('Helvetica-Bold',20);c.drawString(50,750,'Preserved baseline report')
        c.setFont('Helvetica',12);c.drawString(50,715,'The following pages retain the original report for provenance.')
        c.drawString(50,695,'The preceding follow-up supersedes the corresponding earlier inferences.')
        c.drawString(50,675,'Original raw data and the original archive remain unchanged.');c.save();separator.seek(0)
        writer.add_page(PdfReader(separator).pages[0])
        for page in PdfReader(str(ROOT/'report/phase1-report.pdf')).pages:writer.add_page(page)
        writer.write(str(directory/'phase1-revised-report.pdf'))
    write_json(directory/'report-manifest.json',dict(time=now(),draft=args.draft,report_sha256=sha(destination),
        revised_report_sha256=sha(directory/'phase1-revised-report.pdf') if not args.draft else None,
        verification_sha256=sha(ROOT/'data_processed/followup/verification.json')))
    print(destination)

if __name__=='__main__':main()
