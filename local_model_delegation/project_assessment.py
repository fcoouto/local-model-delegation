"""Project-grounded assessment preparation. Preparation never submits inference."""
import hashlib
import math
import os
from pathlib import Path
import re
import subprocess

from .contracts import COMPLEXITIES, CAPABILITIES, MAX_ANSWER_BYTES, canonical, digest, safe_path
from .projects import resolve_project_identity

DIFFICULTIES = COMPLEXITIES
ROLES = {'Coordinator', 'Scout', 'Builder', 'Tester', 'Reviewer', 'Scribe', 'Investigator'}


def difficulty_distribution(count):
    mixes = {6: (1, 2, 2, 1), 7: (2, 2, 2, 1), 8: (2, 3, 2, 1),
             9: (2, 3, 3, 1), 10: (2, 4, 3, 1)}
    if type(count) is not int or count not in mixes:
        raise ValueError('invalid_assignment_count')
    return dict(zip(DIFFICULTIES, mixes[count]))


def _fields(value, names, reason='invalid_project_pack'):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError(reason)


def _text(value, *, identifier=False):
    if (not isinstance(value, str) or not value.strip() or len(value) > 20000
            or '\0' in value or (identifier and not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value))):
        raise ValueError('invalid_project_pack')


def _git(root, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env['LC_ALL'] = 'C'
    result = subprocess.run(['git', '-C', str(root), *args], env=env,
                            capture_output=True, timeout=10)
    if result.returncode:
        raise ValueError('project_revision_unavailable')
    return result.stdout


def _source_evidence(root, evidence):
    _fields(evidence, 'path sha256 revision')
    path = safe_path(root, evidence['path'])
    if '.git' in Path(evidence['path']).parts:
        raise ValueError('unsafe_project_source')
    expected = evidence['sha256']
    if not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected):
        raise ValueError('invalid_project_pack')
    revision = evidence['revision']
    if revision is not None:
        if not isinstance(revision, str) or not re.fullmatch('[a-f0-9]{40}', revision):
            raise ValueError('invalid_project_revision')
        _git(root, 'merge-base', '--is-ancestor', revision, 'HEAD')
        entry = _git(root, 'ls-tree', revision, '--', evidence['path']).decode().split()
        if not entry or entry[0] not in ('100644', '100755'):
            raise ValueError('unsafe_project_source')
        size = int(_git(root, 'cat-file', '-s', revision + ':' + evidence['path']))
        if size > MAX_ANSWER_BYTES:
            raise ValueError('oversized_project_source')
        data = _git(root, 'show', revision + ':' + evidence['path'])
    else:
        if not path.is_file() or path.stat().st_size > MAX_ANSWER_BYTES:
            raise ValueError('unsafe_project_source')
        data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('project_source_changed')


def project_preview(project_root, pack, owner_reference):
    """Validate source-grounded task descriptions without touching model/state files."""
    if not isinstance(owner_reference, str) or not owner_reference.strip():
        raise ValueError('project_permission_required')
    root = Path(project_root).resolve(strict=True)
    identity = resolve_project_identity(root)
    _fields(pack, 'schema_version project domains workload')
    if type(pack['schema_version']) is not int or pack['schema_version'] != 1:
        raise ValueError('invalid_project_pack')
    if pack['project'] != identity:
        raise ValueError('project_identity_mismatch')
    if len(canonical(pack).encode()) > MAX_ANSWER_BYTES:
        raise ValueError('oversized_project_pack')
    domains = pack['domains']
    if not isinstance(domains, list) or not 1 <= len(domains) <= 16:
        raise ValueError('invalid_project_pack')
    ids, scenarios, domain_ids, reports = set(), set(), set(), []
    for domain in domains:
        _fields(domain, 'id specialty role capability language weight assignments')
        for key in ('id', 'language'):
            _text(domain[key], identifier=True)
        _text(domain['specialty'])
        if (domain['id'] in domain_ids or domain['role'] not in ROLES
                or domain['capability'] not in CAPABILITIES):
            raise ValueError('invalid_project_domain')
        domain_ids.add(domain['id'])
        tasks = domain['assignments']
        if not isinstance(tasks, list):
            raise ValueError('invalid_project_pack')
        expected = difficulty_distribution(len(tasks))
        counts = dict.fromkeys(DIFFICULTIES, 0)
        for task in tasks:
            _fields(task, 'id title origin difficulty difficulty_reason context_bucket contract source_evidence verification_plan execution')
            for key in ('id', 'context_bucket'):
                _text(task[key], identifier=True)
            for key in ('title', 'difficulty_reason', 'contract', 'verification_plan'):
                _text(task[key])
            if task['origin'] not in ('historical', 'constructed') or task['difficulty'] not in counts:
                raise ValueError('invalid_project_assignment')
            counts[task['difficulty']] += 1
            normalized = ' '.join(task['contract'].split()).casefold()
            if task['id'] in ids or normalized in scenarios:
                raise ValueError('duplicate_project_assignment')
            ids.add(task['id'])
            scenarios.add(normalized)
            evidence = task['source_evidence']
            if not isinstance(evidence, list) or not 1 <= len(evidence) <= 16:
                raise ValueError('missing_project_evidence')
            for source in evidence:
                _source_evidence(root, source)
            if task['origin'] == 'historical' and not any(e['revision'] for e in evidence):
                raise ValueError('missing_historical_revision')
            if task['execution'] is not None and not isinstance(task['execution'], dict):
                raise ValueError('invalid_project_execution')
        if counts != expected:
            raise ValueError('project_difficulty_distribution')
        reports.append({'id': domain['id'], 'specialty': domain['specialty'], 'role': domain['role'],
                        'capability': domain['capability'], 'language': domain['language'],
                        'weight': domain['weight'], 'difficulty_counts': counts,
                        'assignments': [{k: v for k, v in t.items() if k != 'execution'} for t in tasks]})
    workload = pack['workload']
    _fields(workload, 'owner_reference basis unassessed_weight', 'invalid_project_workload')
    weights = [d['weight'] for d in domains] + [workload['unassessed_weight']]
    if any(w is not None for w in weights):
        if (any(type(w) not in (float, int) or not math.isfinite(w) or not 0 <= w <= 1 for w in weights)
                or not math.isclose(sum(weights), 1, abs_tol=1e-9)
                or not isinstance(workload['owner_reference'], str) or not workload['owner_reference'].strip()
                or not isinstance(workload['basis'], str) or not workload['basis'].strip()):
            raise ValueError('invalid_project_workload')
    elif workload['owner_reference'] is not None or workload['basis'] is not None:
        raise ValueError('invalid_project_workload')
    result = {'schema_version': 1, 'status': 'draft', 'project': identity,
              'owner_reference': owner_reference, 'pack_digest': digest(pack),
              'domains': reports, 'assignment_count': len(ids), 'ready_for_assessment': False,
              'workload_coverage': None, 'unassessed_workload_share': workload['unassessed_weight'],
              'remaining': ['Executable reference validation, runtime budgets and frozen run consent are required.'],
              'limitations': ['Source hashes establish provenance, not task quality or representativeness.',
                              'One extra-high assignment provides exploratory evidence only.',
                              'Task distributions are not workload frequencies.']}
    return {**result, 'preview_digest': digest(result)}
