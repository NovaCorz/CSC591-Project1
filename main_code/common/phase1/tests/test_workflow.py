import gzip
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from common import choose_idle, read_raw, stats, utilization

class StatisticsTests(unittest.TestCase):
    def test_distribution(self):
        s = stats([1, 2, 3, 4, 100], 2)
        self.assertEqual(s['median'], 1.5)
        self.assertEqual(s['q1'], 1)
        self.assertEqual(s['q3'], 2)
        self.assertEqual(s['outliers'], 1)
        self.assertAlmostEqual(s['mean'], 11)
        self.assertAlmostEqual(s['stddev'], math.sqrt(1902.5)/2)
    def test_endian_and_compression(self):
        import struct
        with tempfile.TemporaryDirectory() as d:
            for little, fmt in [(True,'<3Q'), (False,'>3Q')]:
                p=Path(d)/'raw.gz'
                with gzip.open(p,'wb') as f: f.write(struct.pack(fmt, 1, 257, 2**40))
                self.assertEqual(list(read_raw(p,little)), [1,257,2**40])
    def test_truncated_raw_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad'; p.write_bytes(b'1')
            with self.assertRaises(ValueError): read_raw(p)

class CoreTests(unittest.TestCase):
    rows=[dict(cpu=0,core=0,socket=0,node=0),dict(cpu=1,core=1,socket=0,node=0),dict(cpu=2,core=0,socket=0,node=0)]
    def test_busy_sibling_forces_another_core(self):
        selected=choose_idle(self.rows,[{0:0,1:.01,2:.9}]*2,{0,1,2})
        self.assertEqual(selected['cpu'],1)
    def test_recheck_catches_new_activity(self):
        with self.assertRaises(RuntimeError):
            choose_idle(self.rows,[{0:0,1:0,2:0},{0:.8,1:.8,2:0}],{0,1,2})
    def test_cpuset_obeyed_and_idle_retry_avoids_prior(self):
        self.assertEqual(choose_idle(self.rows,[{0:0,1:0,2:0}],{0,1},avoid=[0])['cpu'],1)
    def test_retry_prefers_another_physical_core_over_previous_smt_partner(self):
        self.assertEqual(choose_idle(self.rows,[{0:0,1:.02,2:0}],{0,1,2},avoid=[0],preferred=0)['cpu'],1)
    def test_no_ticks_not_assumed_idle(self):
        self.assertEqual(utilization({0:dict(total=1,idle=1)},{0:dict(total=1,idle=1)})[0],1)

class PreferredCoreTests(unittest.TestCase):
    def test_preferred_idle_core_is_kept_and_busy_core_is_replaced(self):
        rows=[dict(cpu=0,core=0,socket=0,node=0),dict(cpu=1,core=1,socket=0,node=0)]
        self.assertEqual(choose_idle(rows,[{0:0,1:.02}],{0,1},preferred=1)['cpu'],1)
        self.assertEqual(choose_idle(rows,[{0:0,1:.9}],{0,1},preferred=1)['cpu'],0)

class RecomputeTests(unittest.TestCase):
    def test_rounding_allowance_cannot_hide_sample_or_median_changes(self):
        from common import statistics_agree
        a=stats([1,2,3,4,100]);b=dict(a,stddev=a['stddev']+1e-14)
        self.assertTrue(statistics_agree(a,b))
        self.assertFalse(statistics_agree(a,dict(b,n=a['n']-1)))
        self.assertFalse(statistics_agree(a,dict(b,median=a['median']+1e-14)))
        self.assertFalse(statistics_agree(a,dict(b,stddev=a['stddev']+.0001)))

class TimerConversionTests(unittest.TestCase):
    def test_counter_frequency_and_wall_calibration_are_distinct(self):
        from analyze import ns_scale
        arm=dict(unit='CNTVCT_ticks',counter_frequency=10000000,empirical_ticks_per_second=9999000)
        self.assertEqual(ns_scale(arm)[0],100)
        x86=dict(unit='TSC_ticks',empirical_ticks_per_second=2000000000)
        self.assertEqual(ns_scale(x86)[0],.5)
        self.assertIsNone(ns_scale(dict(unit='TSC_ticks',empirical_ticks_per_second=0))[0])
        self.assertEqual(ns_scale(dict(unit='monotonic_raw_ns'))[0],1)

class BatchConsistencyTests(unittest.TestCase):
    def test_skipped_noisy_conflict_point_produces_only_a_bound(self):
        from analyze import conflict_inference
        rows=[dict(family='associativity',qualification='verified_clean',parameters=dict(stride=4096,bytes=n*4096),
            statistics=dict(median=m,q1=m,q3=m),record_path=str(n)) for n,m in ((8,1),(10,2))]
        result=conflict_inference(rows)
        self.assertEqual(result['candidates'],[])
        self.assertEqual(result['bounded_candidates'][0]['resident_addresses_upper'],9)

    def test_alternate_batch_cannot_create_a_boundary_at_the_same_size(self):
        from analyze import boundaries
        def row(size,median,role='primary suite'):
            return dict(family='capacity',parameters=dict(bytes=size,order='random'),
                qualification='verified_clean',analysis_role=role,statistics=dict(median=median,q1=median,q3=median),
                record_path=str((size,median)),measurement=dict(unit='TSC_ticks'),selected=dict(cpu=0,socket=0,node=0))
        candidates=boundaries([row(1024,1),row(1024,100,'alternate batch control'),row(2048,1),row(4096,2)])
        self.assertEqual([(c['lower_bytes'],c['upper_bytes']) for c in candidates],[(2048,4096)])

    def test_alternate_batch_cannot_satisfy_primary_coverage(self):
        import json
        from analyze import coverage_issues
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'batch-calibration.json').write_text(json.dumps(dict(passed=True,chosen_batch=256,trials=[dict(overhead_fraction=.01)])))
            (root/'candidate-boundaries.json').write_text(json.dumps(dict(intervals=[])))
            cfg=dict(min_bytes=1024,max_bytes=2048)
            rows=[dict(family='capacity',parameters=dict(bytes=1024,order='random',batch=512))]
            missing="missing coarse capacity (1024, 'random')"
            self.assertIn(missing,coverage_issues(rows,root,cfg))
            rows.append(dict(family='capacity',parameters=dict(bytes=1024,order='random',batch=256)))
            self.assertNotIn(missing,coverage_issues(rows,root,cfg))

if __name__=='__main__': unittest.main()
