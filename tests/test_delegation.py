import copy
import json
from pathlib import Path
from unittest.mock import patch
from local_repair.contracts import validate_brief, text_hash
from local_repair.store import Store, atomic_json
from tests.support import Fixture


class Delegation(Fixture):
    def generic(self, capability='code_change'):
        source = 'export const trim = text => text.trimStart();\n'
        (self.project / 'helper.js').write_text(source)
        return {'schema_version': 2, 'origin_chat_id': 'fixture-chat', 'task_key': 'generic',
                'capability': capability, 'source_root': str(self.project),
                'files': {'helper.js': {'content': source, 'sha256': text_hash(source)}},
                'editable_paths': [] if capability == 'file_summary' else ['helper.js', 'test_helper.js'],
                'behavior_contract': 'Trim both ends' if capability != 'file_summary' else 'Explain trimming',
                'task_requirements': {'language': 'javascript', 'complexity': 'simple', 'context_bucket': 'small',
                                      'urgency': 'normal', 'wait_budget_seconds': 30},
                'fallback': {'model': 'fictional-native', 'reasoning_effort': 'medium'},
                'acceptance': {'method': 'native_verified', 'criteria': ['Matches the supplied contract'],
                               'protected_paths': [], 'checks': [] if capability == 'file_summary' else [
                                   {'id': 'syntax', 'argv': ['/usr/bin/true'], 'cwd': '.', 'timeout_seconds': 5}]}}

    def proposal(self, brief):
        if brief['capability'] == 'file_summary':
            return {'summary': 'The function trims leading whitespace.', 'claims': [
                {'text': 'Uses trimStart', 'path': 'helper.js', 'sha256': brief['files']['helper.js']['sha256'],
                 'start_line': 1, 'end_line': 1}]}
        return {'files': {'helper.js': 'export const trim = text => text.trim();\n'}, 'summary': 'Trim both ends'}

    def stage_job(self, brief, candidate=None):
        profile = self.profile()
        profile.update(schema_version=2, qualification_status='qualified', capabilities=[brief['capability']],
                       scope=[{'capability': brief['capability'], **{k: brief['task_requirements'][k] for k in ('language','complexity','context_bucket')}, 'max_input_bytes': 100000}])
        profile['approval'].update(capabilities=profile['capabilities'], scope=copy.deepcopy(profile['scope']))
        atomic_json(self.state / 'config.json', {'schema_version': 2, 'routing_enabled': True, 'visibility_enabled': True})
        atomic_json(self.state / 'profiles/fictional.json', profile)
        store = Store(self.state)
        job = store.reserve(brief, profile, self.loaded())
        path = self.state / 'jobs' / job['job_id'] / 'candidate.json'
        text = json.dumps(candidate or self.proposal(brief))
        atomic_json(path, {'text': text, 'sha256': text_hash(text)})
        with store.db(write=True) as db:
            db.execute("UPDATE attempts SET state='complete'")
            db.execute("UPDATE jobs SET status='candidate_ready',result_path=?", (str(path),))
        return store, job['job_id']

    def api(self, name):
        from local_repair import validation
        function = getattr(validation, name, None)
        self.assertTrue(callable(function), name + ' must exist')
        return function

    def receipt(self, session):
        return {**{k: session[k] for k in ('session_token','job_id','attempt_id','native_task_id','candidate_hash','source_hash','acceptance_hash')},
                'criteria': [True], 'checks': {'syntax': True}, 'claims': []}

    def test_schema_two_accepts_javascript_and_python(self):
        brief = self.generic()
        self.assertEqual(validate_brief(brief), brief)
        brief['task_requirements']['language'] = 'python'
        self.assertEqual(validate_brief(brief), brief)

    def test_summary_cannot_write_files(self):
        parse = self.api('parse_proposal'); brief = self.generic('file_summary')
        with self.assertRaisesRegex(ValueError, 'invalid_candidate'):
            parse(json.dumps({'files': {'helper.js': 'bad'}, 'summary': 'bad'}), brief)

    def test_summary_citation_must_match_snapshot(self):
        parse = self.api('parse_proposal'); brief = self.generic('file_summary'); candidate = self.proposal(brief)
        self.assertEqual(parse(json.dumps(candidate), brief), candidate)
        candidate['claims'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'invalid_citation'): parse(json.dumps(candidate), brief)

    def test_code_proposal_respects_paths_and_protected_tests(self):
        parse = self.api('parse_proposal'); brief = self.generic()
        for name in ('../escape.js', 'not-allowed.js', 'helper.js'):
            brief['acceptance']['protected_paths'] = ['helper.js']
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse(json.dumps({'files': {name: 'bad'}, 'summary': 'bad'}), brief)

    def test_prompt_excludes_oracles_and_tools(self):
        from local_repair import worker
        self.assertTrue(callable(getattr(worker, 'build_request', None)), 'build_request must exist')
        brief = self.brief()
        request = worker.build_request(brief, self.profile(), 'fictional-instance')
        self.assertNotIn('independent_tests', request['input'])
        self.assertNotIn('checks', request['input'])
        self.assertNotIn('tools', request)

    def test_candidate_cannot_supply_verification_receipt(self):
        parse = self.api('parse_proposal'); brief = self.generic(); candidate = self.proposal(brief)
        candidate['receipt'] = {'accepted': True}
        with self.assertRaisesRegex(ValueError, 'invalid_candidate'): parse(json.dumps(candidate), brief)

    def test_receipt_rejects_changed_hash_or_attempt(self):
        prepare, record = self.api('prepare_verification'), self.api('record_verification')
        store, identifier = self.stage_job(self.generic())
        session = prepare(self.state, identifier)
        self.assertEqual(store.job(identifier)['status'], 'checking')
        for field in ('session_token', 'candidate_hash', 'attempt_id', 'source_hash', 'acceptance_hash'):
            receipt = self.receipt(session); receipt[field] = 'forged'
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'verification_mismatch'):
                record(self.state, identifier, receipt)
        self.assertEqual(record(self.state, identifier, self.receipt(session))['status'], 'accepted')
        self.assertIn('trimStart', (self.project / 'helper.js').read_text())

    def test_abandoned_native_check_can_resume(self):
        prepare = self.api('prepare_verification')
        store, identifier = self.stage_job(self.generic())
        first, second = prepare(self.state, identifier), prepare(self.state, identifier)
        self.assertEqual(first['session_token'], second['session_token'])
        self.assertEqual(store.job(identifier)['status'], 'checking')

    def test_native_receipt_cannot_accept_after_revocation(self):
        prepare, record = self.api('prepare_verification'), self.api('record_verification')
        store, identifier = self.stage_job(self.generic())
        session = prepare(self.state, identifier)
        path = self.state / 'profiles/fictional.json'; profile = json.loads(path.read_text()); profile['approval'] = None
        atomic_json(path, profile)
        with self.assertRaisesRegex(ValueError, 'model_not_approved'): record(self.state, identifier, self.receipt(session))
        self.assertNotEqual(store.job(identifier)['status'], 'accepted')

    def test_wrong_summary_fails_trusted_claim_review(self):
        prepare, record = self.api('prepare_verification'), self.api('record_verification')
        store, identifier = self.stage_job(self.generic('file_summary'))
        session = prepare(self.state, identifier); receipt = self.receipt(session)
        receipt.update(checks={}, claims=[False])
        self.assertEqual(record(self.state, identifier, receipt)['status'], 'fallback_required')

    def test_missing_isolation_never_executes_candidate(self):
        prepare = self.api('prepare_verification')
        store, identifier = self.stage_job(self.generic())
        with patch('local_repair.validation._qualified_isolation', return_value=False):
            with self.assertRaisesRegex(ValueError, 'verification_unsupported'): prepare(self.state, identifier)
        self.assertNotEqual(store.job(identifier)['status'], 'accepted')

    def test_javascript_checks_cannot_read_private_receipt_or_network(self):
        import shutil
        import sys
        from local_repair.validation import run_native_checks
        node = shutil.which('node')
        if not node or sys.platform != 'darwin': self.skipTest('JavaScript/macOS isolation unavailable')
        brief = self.generic()
        canary = self.root / 'private-canary'; canary.write_text('secret fixture')
        script = ("const fs=require('fs'),net=require('net'); let denied=false;"
                  "try{fs.readFileSync(" + json.dumps(str(canary)) + ")}catch(e){denied=e.code==='EPERM'||e.code==='EACCES'};"
                  "if(!denied)process.exit(9);"
                  "const s=net.connect(9,'127.0.0.1');s.on('connect',()=>process.exit(10));"
                  "s.on('error',e=>process.exit(['EPERM','EACCES'].includes(e.code)?0:11));")
        brief['acceptance']['checks'][0]['argv'] = [str(Path(node).resolve()), '-e', script]
        store, identifier = self.stage_job(brief)
        self.assertEqual(run_native_checks(self.state, identifier)['checks'], {'syntax': True})
        self.assertEqual(store.job(identifier)['status'], 'checking')

    def test_new_file_appearing_after_snapshot_prevents_acceptance(self):
        prepare, record = self.api('prepare_verification'), self.api('record_verification')
        store, identifier = self.stage_job(self.generic())
        session = prepare(self.state, identifier)
        (self.project / 'test_helper.js').write_text('unrelated work')
        with self.assertRaisesRegex(ValueError, 'source_changed'): record(self.state, identifier, self.receipt(session))

    def test_native_candidate_without_selected_local_model_uses_same_checks(self):
        from local_repair.validation import prepare_verification,record_verification
        brief=self.generic('file_summary')
        atomic_json(self.state/'config.json',{'schema_version':2,'routing_enabled':True,'visibility_enabled':True})
        store=Store(self.state);job=store.enqueue(brief,brief['fallback'])
        store.decide_wait(job['job_id'],{'action':'fallback','reason':'no_qualified_model'})
        claim=store.claim_fallback(job['job_id']);native='/root/'+claim['task_name']
        store.attach_fallback(job['job_id'],claim['dispatch_token'],native)
        candidate=self.root/'native.json';candidate.write_text(json.dumps(self.proposal(brief)))
        store.record_fallback_candidate(job['job_id'],native,candidate)
        session=prepare_verification(self.state,job['job_id']);receipt=self.receipt(session);receipt.update(checks={},claims=[True])
        self.assertEqual(record_verification(self.state,job['job_id'],receipt)['status'],'accepted')

    def test_invalid_generic_candidate_selects_fallback_automatically(self):
        from local_repair.validation import prepare_verification
        brief=self.generic();store,identifier=self.stage_job(brief,{'files':{'unauthorized.js':'bad'},'summary':'bad'})
        with self.assertRaises(ValueError):prepare_verification(self.state,identifier)
        self.assertEqual(store.job(identifier)['status'],'fallback_required')

    def test_malformed_summary_path_selects_fallback(self):
        from local_repair.validation import prepare_verification
        brief=self.generic('file_summary');candidate=self.proposal(brief);candidate['claims'][0]['path']=[]
        store,identifier=self.stage_job(brief,candidate)
        with self.assertRaises(ValueError):prepare_verification(self.state,identifier)
        self.assertEqual(store.job(identifier)['status'],'fallback_required')
