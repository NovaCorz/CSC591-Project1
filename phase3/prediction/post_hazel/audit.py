#!/usr/bin/env python3
"""Independent bounded checks of packaged comparisons, run only under Slurm."""
import csv,hashlib,json,math,os,re,sys
from pathlib import Path
assert os.environ.get('SLURM_JOB_ID')
out=Path(sys.argv[1]);root=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((out/'output-manifest.json').read_text())
for rel,x in manifest.items():assert sha(out/rel)==x['sha256'],rel
for p,x in json.loads((out/'input-manifest.json').read_text()).items():assert sha(Path(p))==x['sha256'],p
pred={r['constraint']:r for r in csv.DictReader((out/'frozen-inputs/hazel-predictions.csv').open())}
rows=list(csv.DictReader((out/'prediction-errors.csv').open()))
scored=[r for r in rows if r.get('absolute_error')]
for r in scored:
 p=float(r['prediction']);o=float(r['observation']);assert math.isclose(float(r['absolute_error']),abs(p-o),abs_tol=1e-12)
 assert math.isclose(float(r['absolute_relative_error_pct']),100*abs(p-o)/o,abs_tol=1e-10)
for r in rows:
 if r['metric']=='line_size':assert float(r['prediction'])==float(r['observation'])==64
 if r['constraint']=='turin' and r['metric']=='l2_capacity':assert r['intervals_overlap']=='False'
 if r['constraint']=='cascadelake' and r['metric']=='l1_latency':assert r['observation']==''
master=list(csv.DictReader((out/'chronological-master.csv').open()));assert len(master)==13
assert [int(r['year']) for r in master]==sorted(int(r['year']) for r in master)
assert len({r['machine'] for r in master})==13
assert all(int(r['software_workload_bytes'])==1048576 for r in master)
pre=root/'prediction/pre_hazel/outputs'
for n in ['hazel-predictions.csv','model-parameters.json','future-predictions.csv','team-cache-laws.md','freeze-manifest.json']:assert sha(pre/n)==sha(out/'frozen-inputs'/n)
assert sha(pre/'plot-data/future-models.dat')==sha(out/'frozen-inputs/future-models.dat')
future=list(csv.DictReader((out/'frozen-inputs/future-predictions.csv').open()));assert any(int(r['year'])==max(int(x['year']) for x in master)+5 for r in future)
pdf=out/'plots/required-chronological-plots.pdf';raw=pdf.read_bytes();assert raw.startswith(b'%PDF-') and b'%%EOF' in raw[-1024:]
page_count=len(re.findall(rb'/Type /Page\b',raw));assert page_count==15,page_count
for p in (out/'plots').glob('*.pdf'):assert p.read_bytes().startswith(b'%PDF-') and p.stat().st_size>1000
result={'passed':True,'job_id':os.environ['SLURM_JOB_ID'],'verified_output_hashes':len(manifest),'quantitative_comparisons':len(scored),'required_plot_pdf_pages':page_count,'master_rows':13,'frozen_prediction_and_curve_bytes_unchanged':True,'future_horizon_checked':2029,'scope':'hashes, errors, missing-value handling, sample-workload identity, chronological ordering, PDF structure; visual review separate'}
p=out.parent/f'audit-{out.name}.json';p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
