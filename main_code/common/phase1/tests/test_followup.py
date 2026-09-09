"""Synthetic unit fixtures validate inference logic; never experimental results."""
import sys
from pathlib import Path
import unittest
import tempfile
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_followup import spatial_inference
from common import choose_idle

class SpatialLogicTests(unittest.TestCase):
    def fixtures(self,footprints=(524288,2097152),alignments=(0,24)):
        rows=[]
        for footprint in footprints:
            for align in alignments:
                for offset in range(8,137,8):
                    center=10+10*(offset+align>=64)+10*(offset+align>=128)
                    rows.append(dict(family='spatial_alignment',qualification='clean',
                        parameters=dict(bytes=footprint,align=align,offset=offset),
                        statistics=dict(median=center,q1=center,q3=center),selected=dict(cpu=1),
                        record_path='synthetic-unit-fixture'))
        return rows
    def test_secondary_edge_does_not_disqualify_smallest_shifted_boundary(self):
        result=spatial_inference(self.fixtures())
        self.assertEqual(result['candidate_bytes'],64)
        self.assertEqual([c['bytes'] for c in result['candidates']],[64,128])
    def test_single_alignment_or_footprint_is_insufficient(self):
        self.assertIsNone(spatial_inference(self.fixtures(alignments=(0,)))['candidate_bytes'])
        self.assertIsNone(spatial_inference(self.fixtures(footprints=(524288,)))['candidate_bytes'])
    def test_noisy_boundary_cannot_supply_confirmation(self):
        rows=self.fixtures()
        for d in rows:
            if d['parameters']['align']==24:d['qualification']='noisy'
        self.assertIsNone(spatial_inference(rows)['candidate_bytes'])
    def test_missing_point_cannot_create_precise_boundary(self):
        rows=[d for d in self.fixtures() if d['parameters']['offset']+d['parameters']['align']!=64]
        self.assertNotEqual(spatial_inference(rows)['candidate_bytes'],64)
    def test_small_but_resolved_repeated_effect_is_not_hidden_by_percentage_cutoff(self):
        rows=self.fixtures()
        for d in rows:
            p=d['parameters'];p['batch']=128
            center=100+8*(p['offset']+p['align']>=64)
            d['statistics']=dict(median=center,q1=center,q3=center)
        result=spatial_inference(rows)
        self.assertEqual(result['candidate_bytes'],64)
        self.assertTrue(all(not e['passes_original_10_percent_cutoff'] for e in result['candidates'][0]['evidence']))
    def test_sub_resolution_shift_is_not_an_edge(self):
        rows=self.fixtures()
        for d in rows:
            p=d['parameters'];p['batch']=128
            center=100+.001*(p['offset']+p['align']>=64)
            d['statistics']=dict(median=center,q1=center,q3=center)
        self.assertIsNone(spatial_inference(rows)['candidate_bytes'])
    def test_diagonal_conditions_do_not_substitute_for_factorial_replication(self):
        rows=[d for d in self.fixtures() if (d['parameters']['bytes'],d['parameters']['align']) in ((524288,0),(2097152,24))]
        self.assertIsNone(spatial_inference(rows)['candidate_bytes'])

class PairSelectionTests(unittest.TestCase):
    def test_pair_selection_tries_another_socket_before_waiting(self):
        from common import choose_idle_pair
        rows=[dict(cpu=0,core=0,socket=0,node=0),dict(cpu=1,core=0,socket=1,node=1),dict(cpu=2,core=1,socket=1,node=1)]
        first,second=choose_idle_pair(rows,[{0:0,1:0,2:0}]*2,{0,1,2},preferred=0)
        self.assertEqual(first['socket'],1)
        self.assertEqual(second['socket'],1)
        self.assertNotEqual(first['core'],second['core'])
    def test_other_core_smt_sibling_must_also_be_idle(self):
        rows=[dict(cpu=i,core=i%2,socket=0,node=0) for i in range(4)]
        windows=[{0:0,1:0,2:0,3:.9}]*2
        with self.assertRaises(RuntimeError):choose_idle(rows,windows,{1,3})
    def test_pair_cannot_be_formed_from_one_physical_core(self):
        rows=[dict(cpu=i,core=0,socket=0,node=0) for i in range(2)]
        primary=rows[0]
        allowed={r['cpu'] for r in rows if r['core']!=primary['core']}
        with self.assertRaises(RuntimeError):choose_idle(rows,[{0:0,1:0}]*2,allowed)

class SaturationInferenceTests(unittest.TestCase):
    def fixture(self,root):
        rows=[];groups=[]
        for variant in (1,2):
            for seed in (101,202):
                refs=[]
                for i,value in enumerate((10,20,20)):
                    ref='synthetic-'+str(variant)+'-'+str(seed)+'-'+str(i);refs.append(ref)
                    rows.append(dict(attempt=ref,record_path=ref,qualification='clean',
                        block_means=[value]*10,selected=dict(cpu=1),
                        measurement=dict(anon_huge_before_kib=2,anon_huge_after_kib=2,mapped_bytes=2048)))
                groups.append(dict(variant=variant,seed=seed,attempts=[dict(same_core_clean=True,records=refs)]))
        (root/'l2-confirmation.json').write_text(json.dumps(dict(selected_scrub_count=12,calibrations=groups,refinements=[],rule='synthetic unit fixture')))
        return rows
    def test_all_four_independent_calibrations_required(self):
        from analyze_followup import strong_lower_inference,ROOT
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            root=Path(tmp);rows=self.fixture(root)
            self.assertTrue(strong_lower_inference(rows,root)['upper_scrub_calibrated'])
            rows[-2]['block_means']=[10]*10
            self.assertFalse(strong_lower_inference(rows,root)['upper_scrub_calibrated'])
    def test_changed_core_cannot_pass_calibration(self):
        from analyze_followup import strong_lower_inference,ROOT
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
            root=Path(tmp);rows=self.fixture(root);rows[-2]['selected']['cpu']=2
            self.assertFalse(strong_lower_inference(rows,root)['upper_scrub_calibrated'])

class CapacityMatchingTests(unittest.TestCase):
    def test_extra_dense_class_does_not_shift_common_level_boundaries(self):
        from analyze_followup import common_class_boundaries
        models=[dict(boundaries_bytes=[[32,64],[128,256],[2048,4096],[16384,32768]]),
                dict(boundaries_bytes=[[32,64],[2048,4096],[16384,32768]])]
        self.assertEqual([d['interval'] for d in common_class_boundaries(models)],[[2048,4096],[16384,32768]])
    def test_refinement_does_not_borrow_coarse_endpoint_from_another_core(self):
        from analyze_followup import matched_refinement_edges
        rows=[]
        for family,w,cpu,value in [('capacity_control',256,0,10),('capacity_refinement',256,2,10),('capacity_refinement',288,2,20)]:
            rows.append(dict(family=family,qualification='clean',started=str(len(rows)),
                parameters=dict(page='huge',stride=64,comparison_interval=[256,512],bytes=w),
                selected=dict(cpu=cpu),statistics=dict(median=value,q1=value,q3=value),
                measurement=dict(anon_huge_before_kib=2,anon_huge_after_kib=2,mapped_bytes=2048),
                record_path='synthetic-unit-fixture-'+str(len(rows))))
        result=matched_refinement_edges(rows)
        self.assertEqual(len(result),1)
        self.assertTrue(result[0]['edges'][0]['same_cpu'])
        self.assertEqual(result[0]['edges'][0]['sources'],['synthetic-unit-fixture-1','synthetic-unit-fixture-2'])

class LowerConstructionTests(unittest.TestCase):
    def test_upper_and_lower_lists_stay_disjoint_and_bounded(self):
        from followup_worker import lower_parameter_factory
        with tempfile.TemporaryDirectory() as tmp:
            factory=lower_parameter_factory(Path(tmp),4096,12)
            for variant in (1,2):
                p=factory(65536,16,123,variant)
                offsets=[int(v) for v in Path(p['address_list']).read_text().splitlines()]
                self.assertEqual(len(offsets),28)
                self.assertEqual(len(set(offsets)),28)
                self.assertTrue(all(v%8192==4096 for v in offsets[:12]))
                self.assertTrue(all(v%8192==0 for v in offsets[12:]))
                self.assertTrue(all(0<v<p['bytes']-8 for v in offsets))
                self.assertEqual(p['batch'],56)
    def test_empty_lower_pool_preserves_scrub(self):
        from followup_worker import lower_parameter_factory
        with tempfile.TemporaryDirectory() as tmp:
            p=lower_parameter_factory(Path(tmp),4096,12)(65536,0,123)
            self.assertEqual(len(Path(p['address_list']).read_text().splitlines()),12)
            self.assertEqual(p['batch'],24)

if __name__=='__main__':unittest.main()
