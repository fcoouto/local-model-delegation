"""Frozen, allowlisted text repositories and deterministic model workspace actions."""
import os
from pathlib import Path
import re
import shutil
import stat
import unicodedata

from .contracts import canonical, digest, safe_path, text_hash

FILE_BYTES = 4 * 1024 * 1024
TOTAL_BYTES = 128 * 1024 * 1024
FILE_COUNT = 8192
RESPONSE_BYTES = 32 * 1024
DENIED_PARTS = {'.git', '.ssh', '.aws', '.codex', '.superpowers', '.venv',
                'node_modules', '__pycache__', 'credentials', 'secrets'}


def _fields(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise ValueError('invalid_repository_contract')


def _path(root, name):
    path = safe_path(root, name)
    parts = [part.casefold() for part in name.split('/')]
    if (len(name.encode()) > 1024 or any(part in DENIED_PARTS for part in parts)
            or any(part == '.env' or part.startswith('.env.') for part in parts)
            or parts[-1].endswith(('.pem', '.key', '.p12', '.sqlite', '.sqlite3', '.pyc'))):
        raise ValueError('private_repository_path')
    return path


def _root(root):
    root = Path(root)
    if not root.is_absolute() or root.is_symlink() or root != root.resolve() or not root.is_dir():
        raise ValueError('invalid_repository_root')
    return root


def _names(root, paths):
    if not isinstance(paths, list) or not 1 <= len(paths) <= FILE_COUNT:
        raise ValueError('invalid_repository_paths')
    seen = set()
    for name in paths:
        _path(root, name)
        folded = unicodedata.normalize('NFC', name).casefold()
        if folded in seen:
            raise ValueError('repository_path_collision')
        seen.add(folded)
    return sorted(paths)


def _read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > FILE_BYTES:
            raise ValueError('invalid_repository_file')
        data = stream.read(FILE_BYTES + 1)
    if len(data) > FILE_BYTES or b'\0' in data:
        raise ValueError('invalid_repository_file')
    return data.decode('utf-8')


def snapshot(root, paths, destination, *, revision=None):
    """Read only explicit regular files; a failed export leaves no partial fixture."""
    root = _root(root)
    paths = _names(root, paths)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink() or destination != destination.resolve():
        raise ValueError('repository_destination_exists')
    contents, total = {}, 0
    for name in paths:
        path = _path(root, name)
        if revision is None:
            content = _read(path)
        else:
            from .project_assessment import _git
            if not isinstance(revision, str) or not re.fullmatch('[a-f0-9]{40}', revision):
                raise ValueError('invalid_project_revision')
            _git(root, 'merge-base', '--is-ancestor', revision, 'HEAD')
            entry = _git(root, 'ls-tree', revision, '--', name).split(b'\t')[0].split()
            if len(entry) != 3 or entry[0] not in (b'100644', b'100755') or entry[1] != b'blob':
                raise ValueError('invalid_repository_file')
            if int(_git(root, 'cat-file', '-s', entry[2].decode())) > FILE_BYTES:
                raise ValueError('invalid_repository_file')
            content = _git(root, 'cat-file', 'blob', entry[2].decode()).decode('utf-8')
            if '\0' in content:
                raise ValueError('invalid_repository_file')
        total += len(content.encode())
        if total > TOTAL_BYTES:
            raise ValueError('repository_too_large')
        contents[name] = content
    files = {name: {'size': len(text.encode()), 'sha256': text_hash(text)} for name, text in contents.items()}
    destination.mkdir(mode=0o700, parents=True)
    try:
        for name, content in contents.items():
            target = _path(destination, name)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes(content.encode())
            target.chmod(0o600)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {'schema_version': 1, 'files': files, 'digest': digest(files)}


def validate_snapshot(root, manifest):
    root = _root(root)
    _fields(manifest, 'schema_version files digest')
    if type(manifest['schema_version']) is not int or manifest['schema_version'] != 1 or not isinstance(manifest['files'], dict):
        raise ValueError('invalid_repository_manifest')
    paths = _names(root, list(manifest['files']))
    if digest(manifest['files']) != manifest['digest']:
        raise ValueError('repository_manifest_changed')
    total = 0
    for name in paths:
        item = manifest['files'][name]
        _fields(item, 'size sha256')
        if type(item['size']) is not int or not 0 <= item['size'] <= FILE_BYTES:
            raise ValueError('invalid_repository_size')
        total += item['size']
        if total > TOTAL_BYTES:
            raise ValueError('repository_too_large')
        content = _read(_path(root, name))
        if len(content.encode()) != item['size'] or text_hash(content) != item['sha256']:
            raise ValueError('repository_source_changed')
    actual = set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('repository_symlink')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('invalid_repository_file')
        actual.add(path.relative_to(root).as_posix())
    if actual != set(paths):
        raise ValueError('repository_source_changed')


def _offset(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('invalid_repository_offset')
    return value


def _page(items, offset, key):
    _offset(offset, len(items))
    result = {key: [], 'next': None}
    for index in range(offset, len(items)):
        candidate = {key: result[key] + [items[index]], 'next': index + 1 if index + 1 < len(items) else None}
        if len(canonical(candidate).encode()) > RESPONSE_BYTES:
            result['next'] = index
            break
        result = candidate
    return result


def context_action(root, manifest, action):
    validate_snapshot(root, manifest)
    root = Path(root)
    if not isinstance(action, dict):
        raise ValueError('invalid_repository_action')
    kind = action.get('action')
    if kind == 'list':
        _fields(action, 'action directory offset')
        directory = action['directory']
        if directory != '':
            _path(root, directory)
        prefix = directory + '/' if directory else ''
        entries = [{'path': path, **item} for path, item in sorted(manifest['files'].items()) if path.startswith(prefix)]
        return _page(entries, action['offset'], 'entries')
    if kind == 'read':
        _fields(action, 'action path offset')
        name = action['path']
        if not isinstance(name, str) or name not in manifest['files']:
            raise ValueError('repository_path_not_available')
        data = _read(_path(root, name)).encode()
        start = _offset(action['offset'], len(data))
        prefix = data[:start].decode('utf-8')
        chunk = data[start:start + RESPONSE_BYTES].decode('utf-8', errors='ignore')

        def response(count):
            text = chunk[:count]
            end = start + len(text.encode())
            return {'path': name, 'sha256': manifest['files'][name]['sha256'], 'start': start, 'end': end,
                    'start_line': prefix.count('\n') + 1, 'end_line': prefix.count('\n') + text.count('\n') + 1,
                    'partial_start': start > 0 and data[start - 1] != 10,
                    'partial_end': end < len(data) and (end == 0 or data[end - 1] != 10),
                    'content': text, 'next': end if end < len(data) else None}

        low, high = 0, len(chunk)
        while low < high:
            middle = (low + high + 1) // 2
            if len(canonical(response(middle)).encode()) <= RESPONSE_BYTES:
                low = middle
            else:
                high = middle - 1
        return response(low)
    if kind == 'search':
        _fields(action, 'action paths query offset')
        paths = _names(root, action['paths'])
        if len(paths) > 64 or not set(paths) <= set(manifest['files']):
            raise ValueError('repository_search_scope')
        query = action['query']
        if not isinstance(query, str) or not query or len(query.encode()) > 1024 or '\0' in query:
            raise ValueError('invalid_repository_query')
        matches, skipped = [], 0
        offset = _offset(action['offset'], TOTAL_BYTES)
        for name in paths:
            content = _read(_path(root, name))
            position = 0
            while (position := content.find(query, position)) >= 0:
                if skipped >= offset:
                    matches.append({'path': name, 'offset': len(content[:position].encode()),
                                    'snippet': content[position:position + min(len(query) + 80, 256)]})
                    if len(canonical({'matches': matches, 'next': skipped + 1}).encode()) > RESPONSE_BYTES:
                        matches.pop()
                        return {'matches': matches, 'next': skipped}
                skipped += 1
                position += len(query)
        if offset > skipped:
            raise ValueError('invalid_repository_offset')
        return {'matches': matches, 'next': None}
    raise ValueError('invalid_repository_action')


def apply_edits(root, manifest, editable_paths, proposal):
    validate_snapshot(root, manifest)
    _names(Path(root), editable_paths)
    _names(Path(root), list(set(manifest['files']) | set(editable_paths)))
    _fields(proposal, 'action summary edits')
    if (proposal['action'] != 'submit' or not isinstance(proposal['summary'], str)
            or not isinstance(proposal['edits'], list) or not 1 <= len(proposal['edits']) <= 64):
        raise ValueError('invalid_repository_proposal')
    result = {}
    for edit in proposal['edits']:
        _fields(edit, 'path sha256 changes')
        name = edit['path']
        if not isinstance(name, str) or name not in editable_paths or name in result:
            raise ValueError('candidate_path_not_allowed')
        path = _path(Path(root), name)
        item = manifest['files'].get(name)
        if item is None and (path.exists() or any(parent.is_file() for parent in path.parents)):
            raise ValueError('invalid_repository_creation')
        if edit['sha256'] != (item['sha256'] if item else None):
            raise ValueError('repository_edit_stale')
        changes = edit['changes']
        if not isinstance(changes, list) or not 1 <= len(changes) <= 256:
            raise ValueError('invalid_repository_edits')
        original = _read(path) if item else ''
        spans = []
        for change in changes:
            _fields(change, 'old new')
            old, new = change['old'], change['new']
            if any(not isinstance(value, str) or '\0' in value for value in (old, new)):
                raise ValueError('invalid_repository_edit')
            if item is None:
                if old or len(changes) != 1:
                    raise ValueError('invalid_repository_creation')
                start = 0
            else:
                start = original.find(old)
                if not old or start < 0 or original.find(old, start + 1) >= 0:
                    raise ValueError('ambiguous_repository_edit')
            spans.append((start, start + len(old), new))
        spans.sort()
        if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
            raise ValueError('overlapping_repository_edits')
        modified = original
        for start, end, new in reversed(spans):
            modified = modified[:start] + new + modified[end:]
        if len(modified.encode()) > FILE_BYTES:
            raise ValueError('repository_edit_too_large')
        result[name] = modified
    total = sum(item['size'] for item in manifest['files'].values())
    total += sum(len(content.encode()) - manifest['files'].get(name, {}).get('size', 0) for name, content in result.items())
    if total > TOTAL_BYTES or len(set(manifest['files']) | set(result)) > FILE_COUNT:
        raise ValueError('repository_too_large')
    return result
