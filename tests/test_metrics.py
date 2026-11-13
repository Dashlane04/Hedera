import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('metrics',root/'scripts/metrics.py')
metrics=importlib.util.module_from_spec(spec); spec.loader.exec_module(metrics)


class MetricsTest(unittest.TestCase):
    def test_common_population_keeps_zero_rate(self):
        self.assertAlmostEqual(metrics.jain([10,0]),.5)
        self.assertIsNone(metrics.jain([0,0]))
        self.assertAlmostEqual(metrics.jain([10,10]),1)

    def test_conditional_tail_missing_diagnostics_and_fairness_population(self):
        scratch=root/'tmp/metric-tests';scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            p=Path(tmp).resolve()
            self.assertTrue(p.is_relative_to(scratch.resolve()))
            s=dict(measurement_start_s=1,measurement_end_s=3,duration_s=4,route_changes=0)
            (p/'summary.json').write_text(json.dumps(s))
            header='flow_id,src,dst,start,stop,bytes,completed,fct,window_rx_bytes,route_changes,cohort\n'
            (p/'flows.csv').write_text(header+'0,0,8,0.2,4,100,1,0.7,100,0,finite\n1,1,9,0.2,4,100,0,-1,0,0,finite\n')
            result,details,cohorts=metrics.run_metrics(p)
            self.assertEqual(result['finite_cohort_size'],2)
            self.assertEqual(result['completed_finite'],1)
            self.assertEqual(result['conditional_p95_fct_s'],.7)
            self.assertIsNone(result['jain_goodput_common_active'])
            self.assertIsNone(result['window_retransmissions'])
            (p/'flows.csv').write_text(header+'0,0,8,0.2,4,0,0,-1,2500000,0,background\n1,1,9,0.2,4,0,0,-1,0,0,background\n2,2,10,2,2.5,0,0,-1,100,0,burst\n')
            result,details,cohorts=metrics.run_metrics(p)
            self.assertEqual(result['fairness_population'],2)
            self.assertAlmostEqual(result['jain_goodput_common_active'],.5)
            self.assertEqual(details[0]['goodput_mbps'],10)
            self.assertIsNone(result['conditional_p95_fct_s'])

if __name__=='__main__': unittest.main()
