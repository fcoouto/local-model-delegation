import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from local_model_delegation.contracts import digest, text_hash
from local_model_delegation.repository_context import (
    snapshot, validate_snapshot, context_action, apply_edits, RESPONSE_BYTES,
)


class RepositoryContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'large.py').write_text('a = 1\n' + '# large\n' * 25000)
        (self.source / 'small.py').write_text('one\ntwo\nthree\n')
        self.frozen = self.root / 'frozen'
        self.manifest = snapshot(self.source, ['large.py', 'small.py'], self.frozen)

    def test_large_files_and_changed_source_fail_closed(self):
        validate_snapshot(self.frozen, self.manifest)
        self.assertGreater(self.manifest['files']['large.py']['size'], 100000)
        (self.frozen / 'large.py').write_text('changed')
        with self.assertRaises(ValueError):
            validate_snapshot(self.frozen, self.manifest)

    def test_extra_file_and_manifest_tampering_rejected(self):
        other = copy.deepcopy(self.manifest)
        other['files']['small.py']['size'] += 1
        with self.assertRaises(ValueError):
            validate_snapshot(self.frozen, other)
        (self.frozen / 'extra.py').write_text('extra')
        with self.assertRaises(ValueError):
            context_action(self.frozen, self.manifest, {'action': 'list', 'directory': '', 'offset': 0})

    def test_hostile_paths_and_case_collisions_rejected(self):
        (self.source / 'alias.py').symlink_to(self.source / 'small.py')
        (self.source / '.env').write_text('fictional')
        for paths in [['../outside'], ['/etc/passwd'], ['alias.py'], ['.env'], ['small.py', 'SMALL.py']]:
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                snapshot(self.source, paths, self.root / 'rejected')
            self.assertFalse((self.root / 'rejected').exists())

    def test_bounded_utf8_reads_cover_huge_line_exactly(self):
        text = '\"\\\té' * 40000
        (self.source / 'long.txt').write_text(text)
        frozen = self.root / 'long'
        manifest = snapshot(self.source, ['long.txt'], frozen)
        position, parts = 0, []
        while True:
            result = context_action(frozen, manifest, {'action': 'read', 'path': 'long.txt', 'offset': position})
            self.assertLessEqual(len(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()), RESPONSE_BYTES)
            self.assertEqual(result['start'], position)
            parts.append(result['content'])
            self.assertEqual(result['end'] - position, len(result['content'].encode()))
            if result['next'] is None:
                break
            self.assertGreater(result['next'], position)
            position = result['next']
        self.assertEqual(''.join(parts), text)
        with self.assertRaises(ValueError):
            context_action(frozen, manifest, {'action': 'read', 'path': 'long.txt', 'offset': 4})

    def test_list_search_and_invalid_actions(self):
        listing = context_action(self.frozen, self.manifest, {'action': 'list', 'directory': '', 'offset': 0})
        self.assertEqual([item['path'] for item in listing['entries']], ['large.py', 'small.py'])
        result = context_action(self.frozen, self.manifest, {'action': 'search', 'paths': ['small.py'], 'query': 'two', 'offset': 0})
        self.assertEqual(result['matches'][0]['offset'], 4)
        for action in [
            {'action': 'read', 'path': '../secret', 'offset': 0},
            {'action': 'read', 'path': 'small.py', 'offset': True},
            {'action': 'read', 'path': 'small.py', 'offset': 0, 'shell': 'x'},
            {'action': 'search', 'paths': ['small.py'], 'query': '', 'offset': 0},
            {'action': 'shell', 'command': 'pwd'},
        ]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                context_action(self.frozen, self.manifest, action)

    def proposal(self, changes=None, sha=None):
        return {'action': 'submit', 'summary': 'Change the middle line.', 'edits': [
            {'path': 'small.py', 'sha256': sha or text_hash('one\ntwo\nthree\n'),
             'changes': changes or [{'old': 'two', 'new': 'second'}]},
        ]}

    def test_exact_edit_preserves_full_source_and_does_not_write(self):
        result = apply_edits(self.frozen, self.manifest, ['small.py'], self.proposal())
        self.assertEqual(result, {'small.py': 'one\nsecond\nthree\n'})
        self.assertEqual((self.frozen / 'small.py').read_text(), 'one\ntwo\nthree\n')

    def test_stale_ambiguous_overlapping_and_undeclared_edits_rejected(self):
        proposals = [self.proposal(sha='0' * 64), self.proposal([{'old': '\n', 'new': '!'}]),
                     self.proposal([{'old': 'one\ntwo', 'new': 'x'}, {'old': 'two', 'new': 'y'}]),
                     self.proposal([{'old': '', 'new': 'x'}]), self.proposal([{'old': 'two', 'new': '\x00'}])]
        for proposal in proposals:
            with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                apply_edits(self.frozen, self.manifest, ['small.py'], proposal)
        with self.assertRaises(ValueError):
            apply_edits(self.frozen, self.manifest, ['large.py'], self.proposal())

    def test_explicit_creation_only(self):
        proposal = {'action': 'submit', 'summary': 'New helper.', 'edits': [
            {'path': 'new.py', 'sha256': None, 'changes': [{'old': '', 'new': 'value = 1\n'}]},
        ]}
        with self.assertRaises(ValueError):
            apply_edits(self.frozen, self.manifest, ['small.py'], proposal)
        self.assertEqual(apply_edits(self.frozen, self.manifest, ['new.py'], proposal), {'new.py': 'value = 1\n'})

    def test_special_file_read_never_blocks(self):
        fifo = self.source / 'pipe'
        os.mkfifo(fifo)
        real_open = os.open
        def guarded_open(path, flags, *args, **kwargs):
            self.assertTrue(flags & os.O_NONBLOCK)
            return real_open(path, flags, *args, **kwargs)
        with patch('local_model_delegation.repository_context.os.open', side_effect=guarded_open):
            with self.assertRaises(ValueError):
                snapshot(self.source, ['pipe'], self.root / 'pipe-copy')

    def test_file_and_total_size_limits(self):
        with patch('local_model_delegation.repository_context.FILE_BYTES', 10):
            with self.assertRaises(ValueError):
                snapshot(self.source, ['small.py'], self.root / 'too-large')
        with patch('local_model_delegation.repository_context.TOTAL_BYTES', 10):
            with self.assertRaises(ValueError):
                validate_snapshot(self.frozen, self.manifest)

    def test_creation_rejects_case_alias_and_file_as_directory(self):
        for name in ['SMALL.py', 'small.py/child.py']:
            proposal = {'action': 'submit', 'summary': 'Invalid creation', 'edits': [
                {'path': name, 'sha256': None, 'changes': [{'old': '', 'new': 'x'}]},
            ]}
            with self.subTest(name=name), self.assertRaises(ValueError):
                apply_edits(self.frozen, self.manifest, [name], proposal)

