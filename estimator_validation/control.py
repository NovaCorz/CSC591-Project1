"""Lightweight SSH orchestration for ECE hosts only; no local benchmarks."""
import concurrent.futures,hashlib,io,json,subprocess,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'estimator_validation'
sys.path.insert(0,str(ROOT/'scripts'));from phase1 import ssh_args
HOSTS=json.loads((ROOT/'config/phase1.json').read_text())['hosts']
REMOTE='ece592_estimator_validation_20260913_v1'
stage=sys.argv[1];assert stage in ['smoke','full','collect']
files={'cache_bench.c':ROOT/'src/cache_bench.c','common.py':ROOT/'scripts/common.py','worker.py':P/'worker.py','region_pmu.c':P/'region_pmu.c'}
manifest={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in files.items()}
manifest['phase1_source_repository_commit']=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
manifest['partner_repository_commit']='f0b43d2419224bcc16f9fb4e9a187aeeb90da847'
(P/'source-manifest.json').write_text(json.dumps(manifest,indent=2))
def execute(host):
 d=P/'hosts'/host;d.mkdir(parents=True,exist_ok=True)
 if stage=='smoke':
  buf=io.BytesIO()
  with tarfile.open(fileobj=buf,mode='w') as tar:
   for name,path in files.items():tar.add(path,arcname=name)
   tar.add(P/'source-manifest.json',arcname='source-manifest.json')
  p=subprocess.run(ssh_args(host)+['mkdir -p '+REMOTE+' && tar -xf - -C '+REMOTE],input=buf.getvalue(),capture_output=True)
  if p.returncode:raise RuntimeError(p.stderr.decode())
 if stage in ['smoke','full']:
  cmd=ssh_args(host)+['cd '+REMOTE+' && python3 worker.py '+stage]
  with (d/(stage+'.stdout')).open('w') as stdout,(d/(stage+'.stderr')).open('w') as stderr:
   p=subprocess.run(cmd,stdout=stdout,stderr=stderr)
  (d/(stage+'-execution.json')).write_text(json.dumps({'command':cmd,'returncode':p.returncode},indent=2))
  print(host,stage,p.returncode,flush=True)
 # Retrieve small summaries after every stage; no raw arrays processed locally.
 cmd=ssh_args(host)+['cd '+REMOTE+' && tar --exclude="*.u64" -czf - results']
 with (d/'summaries.tar.gz').open('wb') as f:
  p=subprocess.run(cmd,stdout=f,stderr=subprocess.PIPE)
 if p.returncode:raise RuntimeError(p.stderr.decode())
 if stage=='collect':
  with (d/'raw-and-provenance.tar.gz').open('wb') as f:
   p=subprocess.run(ssh_args(host)+['tar -C '+REMOTE+' -czf - results cache_bench.c region_pmu.c worker.py common.py source-manifest.json full-stage-source-manifest.json'],stdout=f,stderr=subprocess.PIPE)
  if p.returncode:raise RuntimeError(p.stderr.decode())
 return host
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 futures={pool.submit(execute,h):h for h in HOSTS}
 for f in concurrent.futures.as_completed(futures):
  try:f.result()
  except Exception as e:print(futures[f],str(e),flush=True)
