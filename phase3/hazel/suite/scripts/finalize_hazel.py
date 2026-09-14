#!/usr/bin/env python3
"""Run final timing-only validation, plots, and tables on a compute node."""
import json, os
from pathlib import Path
import subprocess, sys

ROOT=Path(__file__).resolve().parents[1]
GENERATIONS={'haswell':'Haswell','broadwell':'Broadwell','skylake':'Skylake-SP','cascadelake':'Cascade Lake',
 'icelake_6326':'Ice Lake-SP','icelake_8358':'Ice Lake-SP','sapphirerapids':'Sapphire Rapids','genoa':'Zen 4 / Genoa','turin':'Zen 5 / Turin'}
def eligible():
 hosts=['haswell','cascadelake','icelake_8358','genoa','turin']
 for host in hosts:
  runroot=ROOT.parent/'runs'/host
  for marker in ['baseline/full/collection-finished.json','followup-v1/inclusion_final-finished.json','page_control/collection-finished.json']:
   if not (runroot/marker).exists():raise RuntimeError('Missing acquisition marker: '+str(runroot/marker))
  if not any((runroot/name/'full-finished.json').exists() for name in ['independent-load-v1','independent-load-diagnostic-v2']):
   raise RuntimeError('Independent diagnostic incomplete: '+host)
 return hosts
def run(command,env):
 print(json.dumps({'stage_command':command}),flush=True)
 subprocess.run(command,cwd=ROOT,env=env,check=True)

def main():
 if not os.environ.get('SLURM_JOB_ID'):raise SystemExit('Slurm job required')
 hosts=eligible();generations={GENERATIONS[h] for h in hosts}
 if len(generations)<5 or 'haswell' not in hosts or 'turin' not in hosts or not ({'genoa','turin'}&set(hosts)):
  raise SystemExit('Minimum five-generation oldest/newest/AMD completion gate is not satisfied: '+str(hosts))
 env=dict(os.environ);env['PYTHONPATH']=str(ROOT.parent/'tools/python-packages')+((':'+env['PYTHONPATH']) if env.get('PYTHONPATH') else '')
 env['MPLCONFIGDIR']=str(ROOT.parent/'results/matplotlib-config');Path(env['MPLCONFIGDIR']).mkdir(parents=True,exist_ok=True)
 (ROOT/'report').mkdir(exist_ok=True)
 run([sys.executable,'scripts/analyze.py','--final','--hosts',*hosts],env)
 run([sys.executable,'scripts/analyze_followup.py','--final','--hosts',*hosts,'--jobs','1'],env)
 run([sys.executable,'scripts/analyze_independent.py','--hosts',*hosts],env)
 run([sys.executable,'scripts/render_followup.py','--hosts',*hosts],env)
 run([sys.executable,'scripts/summarize_hazel.py','--hosts',*hosts],env)
 print(json.dumps({'status':'complete','hosts':hosts,'distinct_generations':sorted(generations)}))
if __name__=='__main__':main()
