import copy
import importlib.util
import json
import sqlite3
from tests.support import Fixture
from local_model_delegation.contracts import digest
from local_model_delegation.store import Store


NATIVE = {'host':'fixture', 'provider':'fixture', 'model':'native', 'reasoning':'medium', 'boundary':'whole_task'}


class Measurements(Fixture):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('local_model_delegation.measurements'), 'measurement ledger is missing')
        from local_model_delegation import measurements
        return measurements

    def setup_metrics(self):
        m = self.api(); self.write_config(enabled=False); Store(self.state)
        m.initialize_measurements(self.state)
        project = m.register_project(self.state, self.project, 'Example')
        self.project_id = project['project_id']
        return m

    def context(self, **changes):
        manifest = {'instructions':{}, 'toolchain':{'python':'fictional'}, 'checks':{}}
        return {'project_id':self.project_id, 'origin':'normal_work',
                'scope':{'capability':'code_change','language':'python','complexity':'simple',
                         'context_bucket':'small','input_bytes':100,'file_count':1},
                'environment_digest':digest(manifest), 'environment_manifest':manifest,
                'native_binding':NATIVE, 'source_revision':None, 'case_id':'case', 'case_hash':'a'*64, **changes}

    def receipt(self, kind, payload, key='event', **changes):
        return {'schema_version':1,'producer':'fixture','source_key':key,'kind':kind,
                'observed_at':100.0,'payload':payload, **changes}

    def test_additive_initialization_preserves_queue_and_configuration(self):
        m = self.api(); config = self.write_config(enabled=False); store = Store(self.state)
        before = config.read_bytes()
        with store.db() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            jobs = db.execute('SELECT * FROM jobs').fetchall()
        m.initialize_measurements(self.state); m.initialize_measurements(self.state)
        self.assertEqual(before, config.read_bytes())
        with store.db() as db:
            self.assertEqual(version, db.execute('PRAGMA user_version').fetchone()[0])
            self.assertEqual(jobs, db.execute('SELECT * FROM jobs').fetchall())
            db.execute('UPDATE measurement_meta SET version=99')
        with self.assertRaisesRegex(ValueError, 'unsupported_measurement_version'): m.initialize_measurements(self.state)

    def test_projects_and_context_replay_are_not_silently_merged(self):
        m = self.setup_metrics()
        self.assertEqual(m.register_project(self.state, self.project, 'Example')['project_id'], self.project_id)
        self.assertNotEqual(m.register_project(self.state, self.artifact, 'Example')['project_id'], self.project_id)
        a = m.begin_measurement(self.state, 'task', self.context())
        self.assertEqual(a, m.begin_measurement(self.state, 'task', self.context()))
        with self.assertRaisesRegex(ValueError, 'measurement_conflict'):
            m.begin_measurement(self.state, 'task', self.context(case_id='different'))
        with self.assertRaisesRegex(ValueError, 'invalid_measurement_context'):
            m.begin_measurement(self.state, 'bad', self.context(environment_digest='0'*64))

    def test_invalid_receipts_do_not_write_or_create_state(self):
        m = self.setup_metrics(); m.begin_measurement(self.state, 'task', self.context())
        for receipt in [self.receipt('invented', {}), self.receipt('delivery', {}, observed_at=float('nan'))]:
            with self.assertRaises(ValueError): m.append_event(self.state, 'task', receipt)
        with sqlite3.connect(self.state/'state.sqlite3') as db:
            self.assertEqual(0, db.execute('SELECT count(*) FROM measurement_events').fetchone()[0])
        absent = self.root/'absent'
        with self.assertRaisesRegex(ValueError, 'measurement_state_missing'): m.initialize_measurements(absent)
        self.assertFalse(absent.exists())

    def test_cli_initializes_and_records_without_runtime_calls(self):
        import contextlib, io
        from local_model_delegation.cli import main
        from unittest.mock import patch
        self.write_config(enabled=False); Store(self.state)
        def invoke(*args):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(['--state-dir', str(self.state), 'metrics', *args])
            self.assertEqual(code, 0, output.getvalue())
            return json.loads(output.getvalue())
        with patch('local_model_delegation.lmstudio.Runtime.stream', side_effect=AssertionError('no inference')):
            self.assertEqual(invoke('init')['measurement_version'], 1)
            self.project_id = invoke('register','--root',str(self.project),'--label','Example')['project_id']
            path = self.root/'context.json';path.write_text(json.dumps(self.context()))
            self.assertEqual(invoke('begin','--task','native-task','--context',str(path))['task_id'], 'native-task')
        self.assertFalse(json.loads((self.state/'profiles.json').read_text())['routing_enabled'])

    def test_event_replay_and_correction_preserve_history(self):
        m = self.setup_metrics(); m.begin_measurement(self.state, 'task', self.context())
        m.begin_measurement(self.state, 'other', self.context())
        receipt = self.receipt('delivery', {'outcome':'not_integrated','artifact_hash':'a'*64,
                              'checks_hash':'b'*64,'native_task_id':None,'durations':{}})
        first = m.append_event(self.state,'task',receipt)
        self.assertEqual(first, m.append_event(self.state,'task',receipt))
        with self.assertRaisesRegex(ValueError,'measurement_conflict'):
            m.append_event(self.state,'task',{**receipt,'observed_at':101})
        correction = {**receipt,'source_key':'correction','supersedes':first['event_id']}
        with self.assertRaisesRegex(ValueError,'invalid_measurement_correction'):
            m.append_event(self.state,'other',correction)
        m.append_event(self.state,'task',correction)
        with sqlite3.connect(self.state/'state.sqlite3') as db:
            self.assertEqual(2,db.execute('SELECT count(*) FROM measurement_events').fetchone()[0])

    def staged_measurement(self):
        from tests.test_delegation import Delegation
        m = self.api()
        brief = Delegation.generic(self)
        store, job = Delegation.stage_job(self, brief, Delegation.proposal(self, brief))
        m.initialize_measurements(self.state)
        self.project_id = m.register_project(self.state,self.project,'Example')['project_id']
        context = self.context(scope={'capability':brief['capability'],
            **{k:brief['task_requirements'][k] for k in ('language','complexity','context_bucket')},
            'input_bytes':len(__import__('local_model_delegation.contracts',fromlist=['canonical']).canonical(
                {'contract':brief['behavior_contract'],'files':brief['files'],'editable_paths':brief['editable_paths']}).encode()),
            'file_count':len(brief['files'])})
        m.begin_measurement(self.state, job, context, job)
        return m, store, job

    def test_verdict_survives_native_rescue_and_reconciliation(self):
        from tests.test_delegation import Delegation
        from local_model_delegation.validation import prepare_verification, record_verification
        m, store, job = self.staged_measurement()
        session = prepare_verification(self.state, job)
        receipt = Delegation.receipt(self, session); receipt['criteria'] = [False]
        record_verification(self.state, job, receipt)
        with sqlite3.connect(self.state/'state.sqlite3') as db:
            verdicts = db.execute("SELECT receipt FROM measurement_events WHERE kind='local_verdict'").fetchall()
        self.assertEqual(len(verdicts),1, 'local verdict must survive fallback replacement')
        self.assertFalse(json.loads(verdicts[0][0])['payload']['accepted'])
        before = store.attempt(store.job(job)['attempt_id'])
        self.assertEqual(m.reconcile_measurements(self.state)['conflicts'], [])
        self.assertEqual(before, store.attempt(store.job(job)['attempt_id']))
        with sqlite3.connect(self.state/'state.sqlite3') as db:
            db.execute("DELETE FROM measurement_events WHERE kind='local_verdict'")
        m.reconcile_measurements(self.state)
        with sqlite3.connect(self.state/'state.sqlite3') as db:
            self.assertEqual(1,db.execute("SELECT count(*) FROM measurement_events WHERE kind='local_verdict'").fetchone()[0])

    def test_enqueue_context_is_atomic_and_cannot_change_on_retry(self):
        from tests.test_delegation import Delegation
        from local_model_delegation.store import atomic_json
        m = self.setup_metrics(); brief = Delegation.generic(self)
        atomic_json(self.state/'config.json', {'schema_version':2,'routing_enabled':True})
        store = Store(self.state)
        with store.db() as db: store.upgrade_schema(db)
        self.assertIn('measurement', __import__('inspect').signature(store.enqueue).parameters)
        context = self.context(scope={'capability':brief['capability'],
            **{k:brief['task_requirements'][k] for k in ('language','complexity','context_bucket')},
            'input_bytes':len(__import__('local_model_delegation.contracts',fromlist=['canonical']).canonical(
                {'contract':brief['behavior_contract'],'files':brief['files'],'editable_paths':brief['editable_paths']}).encode()),
            'file_count':len(brief['files'])})
        job = store.enqueue(brief, brief['fallback'], measurement=context)
        self.assertEqual(job, store.enqueue(brief, brief['fallback'], measurement=context))
        with self.assertRaisesRegex(ValueError,'measurement_conflict'):
            store.enqueue(brief, brief['fallback'], measurement={**context,'case_id':'changed'})
        with store.db() as db:
            self.assertEqual(1,db.execute('SELECT count(*) FROM jobs').fetchone()[0])

    def test_bound_job_cannot_be_attributed_to_another_project_or_scope(self):
        m, store, job = self.staged_measurement()
        other = m.register_project(self.state,self.artifact,'Other')['project_id']
        with store.db() as db: db.execute('DELETE FROM measurement_tasks WHERE task_id=?',(job,))
        with self.assertRaisesRegex(ValueError,'measurement_project_mismatch'):
            m.begin_measurement(self.state,'forged',self.context(project_id=other),job)
