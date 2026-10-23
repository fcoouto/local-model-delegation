"""Assessment runtimes and disposable checks live outside durable plugin state."""
import os
from pathlib import Path


def workspace_root(state_dir):
    state = Path(state_dir).absolute()
    if state != state.resolve() or state == state.parent:
        raise ValueError('unsafe_assessment_storage')
    root = state.with_name(state.name + '-assessment-workspaces')
    if (root != root.resolve() or (root.exists() and not root.is_dir())
            or any((root/name).exists() or (root/name).is_symlink()
                   for name in ('config.json', 'state.sqlite3'))):
        raise ValueError('unsafe_assessment_storage')
    if root.exists() and (root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077):
        raise ValueError('unsafe_assessment_storage')
    return root


def storage_info(state_dir):
    root = workspace_root(state_dir)
    return {'state_root': str(Path(state_dir).absolute()), 'workspace_root': str(root),
            'runtimes': str(root/'runtimes'), 'reference_checks': str(root/'reference-checks')}
