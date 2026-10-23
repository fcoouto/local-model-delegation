import json
from unittest.mock import patch
from local_model_delegation.contracts import load_json
from local_model_delegation.validation import parse_proposal, parse_python_proposal
from tests.support import Fixture, FIXED


class CandidateJSON(Fixture):
    def parsers(self):
        brief = self.brief()
        generic = {**brief, 'capability': 'code_change',
                   'acceptance': {'protected_paths': []}}
        return [(parse_python_proposal, brief), (parse_proposal, generic)]

    def test_plain_and_single_fenced_json(self):
        value = {'files': {'helper.py': FIXED}, 'summary': 'Literal ``` stays data'}
        raw = json.dumps(value)
        for parse, brief in self.parsers():
            expected = parse(raw, brief)
            for text in [raw, ' \n```json\n' + raw + '\n```\t',
                         '```\n' + raw + '\n```', '```json\r\n' + raw + '\r\n```']:
                with self.subTest(parser=parse.__name__, text=text):
                    self.assertEqual(parse(text, brief), expected)

    def test_ambiguous_or_invalid_wrappers_rejected(self):
        raw = json.dumps({'files': {'helper.py': FIXED}, 'summary': 'fix'})
        fenced = '```json\n' + raw + '\n```'
        invalid = ['Here is JSON:\n' + fenced, fenced + '\nDone.', fenced + '\n' + fenced,
                   '```python\n' + raw + '\n```', '```json\n' + raw,
                   '```json\n' + raw + '\n````', '```json ' + raw + '```',
                   '```json\n' + raw + raw + '\n```', '```json\n\n```',
                   '```json\n{"files":{},"files":{},"summary":""}\n```',
                   '```json\n{"files":{},"summary":NaN}\n```',
                   '```json\n{"files":{"../escape.py":"pass"},"summary":""}\n```']
        for parse, brief in self.parsers():
            for text in invalid:
                with self.subTest(parser=parse.__name__, text=text), self.assertRaises(ValueError):
                    parse(text, brief)
            with patch('local_model_delegation.validation.MAX_ANSWER_BYTES', len(raw.encode())), self.assertRaisesRegex(ValueError, 'oversized_answer'):
                parse(fenced, brief)

    def test_summary_and_state_json_boundaries(self):
        brief = self.brief()
        name, item = next(iter(brief['files'].items()))
        brief['capability'] = 'file_summary'
        value = {'summary': 'Summary', 'claims': [{'text': 'Claim', 'path': name,
                 'sha256': item['sha256'], 'start_line': 1, 'end_line': 1}]}
        text = '```json\n' + json.dumps(value) + '\n```'
        self.assertEqual(parse_proposal(text, brief), value)
        with self.assertRaises(ValueError): load_json(text)
        value['claims'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'invalid_citation'):
            parse_proposal('```json\n' + json.dumps(value) + '\n```', brief)
