"""Local project identity; no remotes, provider settings, or network access."""
import os
from pathlib import Path
import subprocess


def _git_path(root, field):
    # Git environment overrides must not bind a different repository to this root.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env['LC_ALL'] = 'C'
    try:
        result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--path-format=absolute', field],
                                capture_output=True, timeout=5, env=env)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('project_discovery_failed') from error
    if result.returncode:
        if b'not a git repository' not in result.stderr:
            raise ValueError('project_discovery_failed')
        return None
    return Path(os.fsdecode(result.stdout.removesuffix(b'\n'))).resolve(strict=True)


def resolve_project_identity(root: Path) -> dict:
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('invalid_project_root')
    common = _git_path(root, '--git-common-dir')
    return {'kind': 'git', 'identity': str(common)} if common else {'kind': 'directory', 'identity': str(root)}


def assessment_projects(project_root, owner_reference, repositories=None):
    """Discover a bounded selection container; never create campaigns or grants."""
    if not isinstance(owner_reference, str) or not owner_reference.strip():
        raise ValueError('project_permission_required')
    root = Path(project_root).resolve(strict=True)
    identity = resolve_project_identity(root)
    entries = []
    kind = identity['kind']
    if kind == 'git':
        owning_root = _git_path(root, '--show-toplevel')
        if owning_root is None:
            raise ValueError('project_discovery_failed')
        entries.append({'root': str(owning_root), 'project': identity})
    else:
        for child in sorted(root.iterdir()):
            if child.is_symlink() or not child.is_dir() or not (child / '.git').exists():
                continue
            project = resolve_project_identity(child)
            if project['kind'] != 'git' or _git_path(child, '--show-toplevel') != child:
                raise ValueError('project_discovery_failed')
            entries.append({'root': str(child), 'project': project})
        if entries:
            kind = 'umbrella'
        else:
            entries.append({'root': str(root), 'project': identity})
    candidates = {}
    for entry in entries:
        candidates.setdefault(entry['project']['identity'], entry)
    selected = []
    if repositories is None:
        if kind != 'umbrella':
            selected = list(candidates.values())
    else:
        if not isinstance(repositories, list) or not repositories:
            raise ValueError('invalid_repository_selection')
        by_root = {entry['root']: entry for entry in entries}
        seen = set()
        for value in repositories:
            if not isinstance(value, str) or not value.strip() or '\0' in value or '..' in Path(value).parts:
                raise ValueError('invalid_repository_selection')
            path = Path(value)
            path = path if path.is_absolute() else root / path
            entry = by_root.get(str(path))
            if entry is None or entry['project']['identity'] in seen:
                raise ValueError('invalid_repository_selection')
            seen.add(entry['project']['identity'])
            selected.append(entry)
    return {'kind': kind, 'root': str(root), 'candidates': list(candidates.values()),
            'selected': selected, 'selection_required': not selected}
