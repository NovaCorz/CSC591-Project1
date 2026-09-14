#!/usr/bin/env python3
"""Render verified follow-up curve/box evidence on a Slurm compute node."""
import argparse, json, os
from pathlib import Path
import report_followup

ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--hosts',nargs='+',required=True);args=parser.parse_args()
    if not os.environ.get('SLURM_JOB_ID'):raise SystemExit('Slurm job required for plotting')
    output={}
    for host in args.hosts:
        path=ROOT.parent/'analysis/followup'/(host+'-verified-records.json')
        rows=json.loads(path.read_text()); output[host]=[str(p) for p in report_followup.figures(host,rows)]
    target=ROOT.parent/'results/rendered-followup.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps({'job_id':os.environ['SLURM_JOB_ID'],'hosts':output},indent=2)+'\n')
    print(json.dumps({host:len(paths) for host,paths in output.items()}))
if __name__=='__main__':main()
