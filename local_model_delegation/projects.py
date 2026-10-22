"""Local project identity; no remotes, provider settings, or network access."""
import os
from pathlib import Path
import subprocess


def resolve_project_identity(root: Path) -> dict:
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('invalid_project_root')
    # Git environment overrides must not bind a different repository to this root.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env['LC_ALL'] = 'C'
    try:
        result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                capture_output=True, text=True, timeout=5, env=env)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('project_discovery_failed') from error
    if result.returncode:
        if 'not a git repository' not in result.stderr:
            raise ValueError('project_discovery_failed')
        return {'kind': 'directory', 'identity': str(root)}
    return {'kind': 'git', 'identity': str(Path(result.stdout.strip()).resolve(strict=True))}
