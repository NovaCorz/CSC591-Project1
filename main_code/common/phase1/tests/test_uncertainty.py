import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from uncertainty_worker import conflict_offsets,detected_edges


class UncertaintyTests(unittest.TestCase):
    def test_reject_stride_that_overlaps_scrub_index_bit(self):
        with self.assertRaises(ValueError):
            conflict_offsets(16384,16384,8,6)

    def test_scrub_and_candidate_index_hypotheses(self):
        for period,ways in ((4096,8),(16384,4)):
            for stride in (32768,65536,131072,262144,524288):
                for variant in (1,2):
                    offsets=conflict_offsets(period,stride,64,ways+2,variant)
                    self.assertEqual(len(offsets),len(set(offsets)))
                    self.assertTrue(all(v%period==0 for v in offsets))
                    self.assertTrue(all(v//period%2==1 for v in offsets[:ways+2]))
                    self.assertTrue(all(v//period%2==0 for v in offsets[ways+2:]))
                    self.assertLess(max(offsets),536870912)

    def test_noisy_or_cross_core_edges_are_not_refined(self):
        def row(n,median,cpu=0,status='passed'):
            return dict(parameters=dict(candidate_count=n),status=status,selected=dict(cpu=cpu),
                        statistics=dict(median=median,q1=median-.1,q3=median+.1))
        self.assertEqual(detected_edges([row(4,2),row(6,4)],'candidate_count'),[[4,6]])
        self.assertEqual(detected_edges([row(4,2),row(6,4,1)],'candidate_count'),[])
        self.assertEqual(detected_edges([row(4,2),row(6,4,status='noisy')],'candidate_count'),[])
        self.assertEqual(detected_edges([row(4,2),row(6,2.1)],'candidate_count'),[])

if __name__=='__main__':unittest.main()

from analyze_uncertainty import conflict


class ConditionalGeometryTests(unittest.TestCase):
    def records(self,strides=(65536,131072)):
        rows=[]
        for stride in strides:
            for variant in (1,2):
                for seed in (1001,1101):
                    for n in (4,5):
                        median=2 if n==4 else 4
                        rows.append(dict(family='batched_conflict',parameters=dict(samples=1000000,conflict_stride=stride,
                            scrub_count=10,variant=variant,seed=seed,series='heldout',candidate_count=n,page='huge'),
                            started=str(n),qualification='clean',selected=dict(cpu=0),
                            measurement=dict(anon_huge_before_kib=4096,anon_huge_after_kib=4096,mapped_bytes=4194304),
                            statistics=dict(median=median,q1=median-.1,q3=median+.1),
                            record_path=str((stride,variant,seed,n))))
        return rows

    def plan(self,strides=(65536,131072)):
        return dict(conflict_strides=list(strides),l1_ways=8,l2_interval=[262144,294912],conflict_required=True)

    def test_replicated_geometry_is_conditional_not_physical(self):
        d=conflict(self.records(),self.plan())
        self.assertEqual(d['conditional_l2_ways'],4)
        self.assertIsNone(d['physical_l2_ways'])

    def test_capacity_incompatible_period_does_not_supply_ways(self):
        strides=(131072,262144)
        d=conflict(self.records(strides),self.plan(strides))
        self.assertIsNone(d['conditional_l2_ways'])

    def test_one_noisy_required_repeat_blocks_candidate(self):
        rows=self.records();rows[0]['qualification']='noisy'
        self.assertIsNone(conflict(rows,self.plan())['conditional_l2_ways'])

    def test_unbacked_huge_mapping_cannot_establish_index_geometry(self):
        rows=self.records();rows[0]['measurement']['anon_huge_after_kib']=0
        self.assertIsNone(conflict(rows,self.plan())['conditional_l2_ways'])

from uncertainty_worker import blocked_pairs


class QualityRepairTests(unittest.TestCase):
    def row(self,n,cpu=0,status='passed'):
        return dict(parameters=dict(candidate_count=n),selected=dict(cpu=cpu),status=status)

    def test_all_cross_core_pairs_are_repaired_without_latency_selection(self):
        rows=[self.row(2,0),self.row(4,1),self.row(6,0)]
        self.assertEqual(blocked_pairs(rows),[[2,4],[4,6]])

    def test_noisy_endpoint_requires_both_neighbor_comparisons(self):
        rows=[self.row(2),self.row(4,status='noisy'),self.row(6)]
        self.assertEqual(blocked_pairs(rows),[[2,4],[4,6]])

    def test_clean_same_core_pairs_do_not_trigger_repair(self):
        self.assertEqual(blocked_pairs([self.row(6),self.row(2),self.row(4)]),[])

from uncertainty_worker import clean_cross_core_pairs


class CapacityPairRepairTests(unittest.TestCase):
    def row(self,w,cpu,status='passed'):
        return dict(parameters=dict(bytes=w),selected=dict(cpu=cpu),status=status)

    def test_repairs_core_changes_in_both_directions(self):
        self.assertEqual(clean_cross_core_pairs([self.row(1024,0),self.row(2048,1),self.row(4096,0)]),[[1024,2048],[2048,4096]])

    def test_does_not_skip_noisy_intermediate_point(self):
        self.assertEqual(clean_cross_core_pairs([self.row(1024,0),self.row(2048,0,'noisy'),self.row(4096,1)]),[])
