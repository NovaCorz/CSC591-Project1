"""Check the property that distinguishes the two audited native loops."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from independent_worker import audit_loops
from analyze_independent import pair_summary


class NativeDependencyAudit(unittest.TestCase):
    def assembly(self,isa,parallel):
        def loop(name,regs):
            loads='\n'.join(('ldr '+r+', ['+r+']') if isa=='aarch64' else ('mov (%'+r+'),%'+r) for r in regs)
            return '<'+name+'>:\n'+loads+'\n'+('b.ne 10' if isa=='aarch64' else 'jne 10')+'\n\n'
        r='x0' if isa=='aarch64' else 'rax'
        return loop('serial4',[r]*4)+loop('parallel4',parallel)

    def test_both_isas(self):
        for isa,regs in [('aarch64',['x0','x1','x2','x3']),('x86_64',['rax','rbx','rcx','rdx'])]:
            self.assertEqual(len(audit_loops(self.assembly(isa,regs),isa)),2)

    def test_reject_serialized_parallel_kernel(self):
        with self.assertRaises(RuntimeError):audit_loops(self.assembly('x86_64',['rax']*4),'x86_64')

    def test_reject_missing_load(self):
        with self.assertRaises(RuntimeError):audit_loops(self.assembly('aarch64',['x0','x1','x2']),'aarch64')


class MatchedPairValidation(unittest.TestCase):
    def records(self):
        return [dict(parameters=dict(streams=s,batch=4096,seed=1,bytes=1024,stride=8,samples=1000000),
            measurement=dict(ring_hash='same',unit='TSC_ticks'),selected=dict(cpu=2),status='passed',
            statistics=dict(median=m),record=str(s)) for s,m in [(1,4),(4,1)]]

    def test_ratio_uses_matched_medians(self):
        self.assertEqual(pair_summary(self.records())['ratio'],4)

    def test_reject_different_cpu(self):
        r=self.records();r[1]['selected']['cpu']=3
        with self.assertRaises(AssertionError):pair_summary(r)

    def test_reject_noisy_arm(self):
        r=self.records();r[1]['status']='noisy'
        with self.assertRaises(AssertionError):pair_summary(r)

if __name__=='__main__':unittest.main()
