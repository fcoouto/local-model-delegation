import copy
import importlib.util
import time
from local_repair.store import Store
from tests import test_scheduler


from tests.support import Fixture


class Capacity(Fixture):
    generic=test_scheduler.Scheduler.generic
    setup_queue=test_scheduler.Scheduler.setup_queue
    resources=test_scheduler.Scheduler.resources
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('local_repair.capacity'),'capacity module must exist')
        from local_repair import capacity
        return capacity

    def measured(self,p):
        from local_repair.contracts import digest
        return {**p,'capacity_evidence':{'qualified':True,'limit':2,'machine_fingerprint':'fixture-machine',
                 'settings_digest':digest(p['request_settings']),'artifact_digest':p['artifact']['digest'],
                 'context_length':8192,'request_bytes':4*1024**3,'batches':3,'median_slowdown':1.2}}

    def test_unknown_resource_data_closes_admission(self):
        module=self.module(); store,brief,p=self.setup_queue();p=self.measured(p)
        for key in ('available_bytes','physical_bytes','observed_at','swapout_delta_bytes','machine_fingerprint'):
            r=self.resources();r[key]=None
            with self.subTest(key=key):self.assertEqual(module.qualified_limit(p,self.loaded(2),r),0)

    def test_disk_size_is_not_parallel_capacity(self):
        module=self.module();store,brief,p=self.setup_queue()
        p.pop('capacity_evidence')
        self.assertEqual(module.qualified_limit(p,self.loaded(20),self.resources()),0)
        self.assertEqual(module.qualified_limit(self.measured(p),self.loaded(20),self.resources()),2)

    def test_changed_machine_or_settings_invalidates_capacity(self):
        module=self.module();store,brief,p=self.setup_queue();p=self.measured(p)
        changed=copy.deepcopy(p);changed['request_settings']['max_output_tokens']+=1
        self.assertEqual(module.qualified_limit(changed,self.loaded(2),self.resources()),0)
        r=self.resources();r['machine_fingerprint']='changed'
        self.assertEqual(module.qualified_limit(p,self.loaded(2),r),0)

    def test_two_models_cannot_reserve_same_free_memory(self):
        self.module();store,brief,p=self.setup_queue();r=self.resources();estimate={'bytes':10*1024**3,'non_evicting':True}
        first=store.reserve_load(p,estimate,r)
        other={**p,'model_id':'second-fictional-model'}
        with self.assertRaisesRegex(ValueError,'insufficient_resources'):store.reserve_load(other,estimate,r)
        self.assertEqual(first['operation_id'],store.reserve_load(p,estimate,r)['operation_id'])

    def test_unowned_instance_is_never_unloaded(self):
        module=self.module();store,brief,p=self.setup_queue()
        job=store.reserve(brief,p,self.loaded())
        key=store.attempt(job['attempt_id'])['instance_key']
        self.assertEqual(module.release_idle(self.state,key)['reason'],'instance_not_owned')

    def test_unknown_eviction_behavior_blocks_load(self):
        module=self.module();store,brief,p=self.setup_queue()
        self.assertEqual(module.ensure_loaded(self.state,'fictional')['reason'],'lifecycle_unqualified')
        with store.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM model_operations').fetchone()[0],0)

    def test_lost_load_ack_retains_reservation_without_repost(self):
        self.module();store,brief,p=self.setup_queue();estimate={'bytes':2*1024**3,'non_evicting':True}
        first=store.reserve_load(p,estimate,self.resources())
        with store.db(write=True) as db:db.execute("UPDATE model_operations SET state='uncertain'")
        second=store.reserve_load(p,estimate,self.resources())
        self.assertEqual(first['operation_id'],second['operation_id'])
        self.assertEqual(second['state'],'uncertain')

    def test_measurement_steps_require_three_correct_batches(self):
        module=self.module();store,brief,p=self.setup_queue()
        batches=[{'concurrency':1,'task_seconds':[10],'all_correct':True,'request_bytes':1024**3,'pressure':'normal','swapout_delta_bytes':0} for _ in range(3)]
        batches += [{'concurrency':2,'task_seconds':[14,14],'all_correct':True,'request_bytes':1024**3,'pressure':'normal','swapout_delta_bytes':0} for _ in range(3)]
        self.assertEqual(module.qualify_measurements(p,batches,self.resources(),8192)['limit'],2)
        batches[-1]['all_correct']=False
        self.assertEqual(module.qualify_measurements(p,batches,self.resources(),8192)['limit'],1)

    def test_capacity_drop_preserves_healthy_jobs(self):
        module=self.module();store,brief,p=self.setup_queue();first=store.enqueue(brief,brief['fallback'])
        store.admit(first['job_id'],p,self.loaded(2),self.resources())
        other=store.enqueue({**brief,'task_key':'second'},brief['fallback'])
        pressure=self.resources();pressure['pressure']='critical'
        self.assertEqual(store.admit(other['job_id'],p,self.loaded(2),pressure)['status'],'waiting')
        self.assertEqual(store.job(first['job_id'])['status'],'reserved')

    def test_broad_recovery_does_not_reset_external_instance(self):
        module=self.module();store,brief,p=self.setup_queue();job=store.reserve(brief,p,self.loaded())
        attempt=store.attempt(job['attempt_id'])
        from local_repair.recovery import close_instance,recover_once
        from unittest.mock import Mock
        close_instance(store,attempt['instance_key']);runtime=Mock()
        with self.assertRaisesRegex(ValueError,'instance_not_owned'):recover_once(store,attempt['instance_key'],runtime)
        runtime.unload.assert_not_called();runtime.load.assert_not_called()
