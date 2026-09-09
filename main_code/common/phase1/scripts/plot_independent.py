#!/usr/bin/env python3
"""Plot verified diagnostic statistics; never reclassify or discard an attempt."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from common import sha,write_json


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workspace',type=Path,default=Path(__file__).resolve().parents[1]);a=ap.parse_args()
    root=a.workspace;src=root/'data_processed/independent-load';out=root/'plots/independent-load';out.mkdir(parents=True,exist_ok=True)
    summary=json.loads((src/'summary.json').read_text());records={d['record']:d for d in json.loads((src/'verified-records.json').read_text())}
    fig,axes=plt.subplots(4,2,figsize=(11,11),layout='constrained');sources=[]
    for ax,s in zip(axes.flat,summary):
        boxes=[];positions=[];colors=[]
        for i,p in enumerate(s['pairs']):
            for stream,record in enumerate(p['records']):
                d=records[record];st=d['statistics'];sources.append(record)
                boxes.append(dict(med=st['median'],q1=st['q1'],q3=st['q3'],whislo=st['p05'],whishi=st['p95'],fliers=[]))
                positions.append(i*3+stream);colors.append('#345c9c' if stream==0 else '#c45b24')
        if boxes:
            artists=ax.bxp(boxes,positions=positions,widths=.65,patch_artist=True,showfliers=False)
            for b,c in zip(artists['boxes'],colors):b.set_facecolor(c);b.set_alpha(.65)
        ax.set_xticks([i*3+.5 for i in range(len(s['pairs']))],
            [str(p['seed'])[-3:]+('/DI' if p['order']==[1,4] else '/ID')+'\ncpu '+str(p['cpu']) for p in s['pairs']],fontsize=7)
        ax.set_title(s['host']+' | '+str(s['qualified_pairs'])+'/6 qualified pairs',fontsize=10)
        ax.set_ylabel(s['unit'],fontsize=8);ax.tick_params(axis='y',labelsize=8);ax.grid(axis='y',alpha=.2);ax.set_ylim(bottom=0)
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color='#345c9c',label='D: one dependency chain'),Patch(color='#c45b24',label='I: four independent chains')],loc='outside upper center',ncols=2)
    fig.savefig(out/'distributions.pdf');fig.savefig(out/'distributions.svg');plt.close(fig)
    write_json(out/'provenance.json',dict(inputs={str((src/n).relative_to(root)):sha(src/n) for n in ['summary.json','verified-records.json','verification.json']},
        records=sources,description='Every qualified pair; median/IQR boxes and P5/P95 whiskers. No raw interval removed. Units and pair seed/order/CPU retained.',
        files={n:sha(out/n) for n in ['distributions.pdf','distributions.svg']}))


if __name__=='__main__':main()
