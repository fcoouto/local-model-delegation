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
