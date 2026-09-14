#!/usr/bin/env python3
"""Run only on the named ECE lab machines, never on an HPC login node."""
import fcntl,json,os,platform,shutil,subprocess,sys,time,traceback
from pathlib import Path
from common import now,write_json,sha,read_raw,stats,topology,select_idle
ROOT=Path(__file__).resolve().parent
HOST=platform.node().split('.')[0]
assert HOST in ['sunbird','thunderbird','skylark','artemisia','charnwood','crux','ookay','upgrade']
os.chdir(ROOT)
out=ROOT/'results';out.mkdir(exist_ok=True)
lock=open(out/'worker.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
stage=sys.argv[1];assert stage in ['smoke','full']
space=shutil.disk_usage(ROOT)
write_json(out/'storage.json',dict(free_bytes=space.free,expected_raw_bytes=9*1000000*8))
assert space.free>1024**3,'Less than 1 GiB free for this validation workspace'
def command(cmd,name,env=None,timeout=120):
 start=now();p=subprocess.run(cmd,capture_output=True,universal_newlines=True,env=env,timeout=timeout)
 write_json(out/(name+'.json'),dict(command=cmd,started=start,finished=now(),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
 if p.returncode:raise RuntimeError(name+': '+p.stderr)
 return p
if not (out/'build.json').exists():
 command(['gcc','--version'],'compiler')
 flags=['-O0','-g','-std=c11','-Wall','-Wextra','-Werror','-fno-omit-frame-pointer']
 command(['gcc']+flags+['cache_bench.c','-o','cache_bench'],'compile-benchmark')
 command(['gcc','-O2','-shared','-fPIC','-Wall','-Wextra','-Werror','region_pmu.c','-ldl','-o','region_pmu.so'],'compile-observer')
 write_json(out/'build.json',dict(flags=flags,source_sha256=sha(ROOT/'cache_bench.c'),binary_sha256=sha(ROOT/'cache_bench'),observer_sha256=sha(ROOT/'region_pmu.c')))
rows,topo=topology()
model=[x.strip() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith(('model name','CPU implementer','CPU part'))]
write_json(out/'environment.json',dict(host=HOST,hostname=platform.node(),platform=platform.platform(),architecture=platform.machine(),cpu_identity=sorted(set(model)),topology=topo,allowed_cpus=sorted(os.sched_getaffinity(0)),timestamp=now(),source_manifest=json.loads((ROOT/'source-manifest.json').read_text())))
cfg=dict(idle_windows=2,idle_seconds=1,idle_fraction=.05)
records=[]
def run(name,size,level,samples):
 folder=out/stage/name;folder.mkdir(parents=True,exist_ok=True)
 if (folder/'record.json').exists():return json.loads((folder/'record.json').read_text())
 while True:
  idle=select_idle(rows,cfg);write_json(folder/'idle-latest.json',idle)
  if idle['selected']:break
  print('Waiting for idle core: '+name,flush=True);time.sleep(15)
 cpu=idle['selected']['cpu'];cfg['_preferred_cpu']=cpu
 write_json(folder/'idle.json',idle)
 raw=folder/'raw.u64';env=os.environ.copy()
 for key in ['LD_PRELOAD','VALIDATION_LEVEL','VALIDATION_OUTPUT']:env.pop(key,None)
 if level:
  env.update(LD_PRELOAD=str(ROOT/'region_pmu.so'),VALIDATION_LEVEL=level,VALIDATION_OUTPUT=str(folder/'pmu.json'))
 cmd=[str(ROOT/'cache_bench'),'chase',str(size),'8','0',str(samples),'1','5922026',str(cpu),'random',str(raw)]
 start=now();p=subprocess.run(cmd,capture_output=True,universal_newlines=True,env=env,timeout=1200)
 (folder/'stdout.log').write_text(p.stdout);(folder/'stderr.log').write_text(p.stderr)
 r=dict(name=name,host=HOST,level=level,bytes=size,samples=samples,command=cmd,started=start,finished=now(),returncode=p.returncode,cpu=cpu,observer_environment={k:env[k] for k in ['LD_PRELOAD','VALIDATION_LEVEL','VALIDATION_OUTPUT'] if k in env},issues=[])
 if p.returncode:r['issues'].append('benchmark failed')
 else:
  m=json.loads(p.stdout);r['measurement']=m
  values=read_raw(raw,m['little_endian']);assert len(values)==samples
  r['statistics']=stats(values);r['raw_sha256']=sha(raw)
  r['blocks']=[stats(values[i:i+10000]) for i in range(0,len(values),10000)]
  if m['cpu']!=cpu or m['final_cpu']!=cpu:r['issues'].append('affinity mismatch')
  if m['major_faults']:r['issues'].append('major page faults')
  if m['involuntary_switches']:r['issues'].append('involuntary context switches retained')
  if level:
   q=json.loads((folder/'pmu.json').read_text());r['pmu']=q
   assert q['calls']==2,'region hook did not see exactly two calls'
   if q['errno']:r['issues'].append('PMU unavailable: errno '+str(q['errno']))
   elif q['read_bytes']!=40 or q['nr']!=2:r['issues'].append('invalid PMU group read')
   elif not q['running_ns'] or q['running_ns']!=q['enabled_ns']:r['issues'].append('PMU group not fully scheduled')
   elif not q['accesses'] or q['misses']>q['accesses']:r['issues'].append('PMU ratio not a hit probability')
  else: assert not (folder/'pmu.json').exists()
 write_json(folder/'record.json',r);print(name+': '+str(r['issues']),flush=True)
 return r
try:
 if stage=='smoke':
  for level in [None,'L1D','LL']:records.append(run('smoke-'+str(level),1048576,level,10000))
  assert all(r['returncode']==0 and r['statistics']['n']==10000 for r in records)
  write_json(out/'smoke-passed.json',dict(timestamp=now(),records=records,note='Unavailable PMUs are retained, not a functional benchmark failure.'))
 else:
  assert (out/'smoke-passed.json').exists()
  for level in [None,'L1D','LL']:
   smoke=json.loads((out/'smoke-passed.json').read_text())['records']
   if level and any(r['level']==level and r.get('pmu',{}).get('errno') for r in smoke):
    write_json(out/('unavailable-'+level+'.json'),dict(level=level,reason='Event pair unavailable in smoke; no duplicate full attempt',source='smoke-passed.json'))
    continue
   for label,size in [('hot',1024),('target',1048576),('cold',268435456)]:
    records.append(run(str(level)+'-'+label,size,level,1000000))
  write_json(out/'full-complete.json',dict(timestamp=now(),records=records))
except Exception:
 (out/(stage+'-failure.txt')).write_text(traceback.format_exc());raise
