"""Project evidence summaries; curated samples never establish statistical reliability."""
from collections import Counter
from .contracts import canonical, digest, text_hash


def summarize(record, results):
    buckets, families = [], []
    coverage = 0.0 if record['pack']['workload']['unassessed_weight'] is not None else None
    for domain in record['pack']['domains']:
        outcomes = [r for r in results if r['domain_id'] == domain['id']]
        families.append({'domain_id': domain['id'], 'role': domain['role'], 'specialty': domain['specialty'],
                         'counts': dict(Counter(r['disposition'] for r in outcomes)),
                         'origins': dict(Counter(r['origin'] for r in outcomes)), 'planned': len(outcomes)})
        if coverage is not None:
            coverage += domain['weight'] * sum(r['disposition'] == 'passed' for r in outcomes) / len(outcomes)
        bands = sorted({(t['difficulty'], t['context_bucket']) for t in domain['assignments']})
        for difficulty, context in bands:
            tasks = [t for t in domain['assignments'] if (t['difficulty'], t['context_bucket']) == (difficulty, context)]
            ids = {t['id'] for t in tasks}
            selected = [r for r in outcomes if r['case_id'] in ids]
            counts = dict.fromkeys(('passed', 'failed', 'unfinished', 'not_run', 'pending'), 0)
            counts.update(Counter(r['disposition'] for r in selected))
            suitable = counts['passed'] == len(tasks) and len(tasks) >= 2
            recommendation = ('suitable_within_tested_scope' if suitable else
                              'mixed_results_requiring_narrower_scope' if counts['failed'] and counts['passed'] else 'not_established')
            briefs = [t['brief'] for t in record['trials'] if t['case_id'] in ids and t['cycle'] == 1]
            size = min(len(canonical({'contract': b['behavior_contract'], 'files': b['files'],
                                      'editable_paths': b['editable_paths']}).encode()) for b in briefs)
            buckets.append({'domain_id': domain['id'], 'role': domain['role'], 'specialty': domain['specialty'],
                            'capability': domain['capability'], 'language': domain['language'],
                            'complexity': difficulty, 'context_bucket': context, 'max_input_bytes': size,
                            'counts': counts, 'planned': len(tasks), 'recommendation': recommendation,
                            'first_cycle_passed': sum(r['disposition'] == 'passed' and r['cycles'] == 1 for r in selected)})
    return {'scope_results': buckets, 'families': families,
            'workload_coverage': None if coverage is None else {
                'share': coverage, 'denominator': 'recurring_task_count', 'provisional': True,
                'basis': record['pack']['workload']['basis'],
                'owner_reference': record['pack']['workload']['owner_reference'],
                'meaning': 'Potentially suitable share of the confirmed task mix, subject to native verification; not reliability or time saved.'},
            'unassessed_workload_share': record['pack']['workload']['unassessed_weight'],
            'native_comparison': {'status': 'reported_separately', **record['preview']['comparison_protocol'],
                                  'cases': comparison_inputs(record),
                                  'results_location': 'Private metrics report; comparison receipts do not alter capability outcomes.'}}


def comparison_inputs(record):
    """Export frozen first-cycle inputs for the existing private comparison ledger."""
    cases = []
    for domain in record['pack']['domains']:
        for task in domain['assignments']:
            if task['id'] not in record['preview']['comparison_protocol']['subset']:
                continue
            trial = next(t for t in record['trials'] if t['case_id'] == task['id'] and t['cycle'] == 1)
            brief = trial['brief']
            environment = {'assessment_id': record['assessment_id'], 'verification': record['preview']['verification'],
                           'protocol': record['preview']['comparison_protocol'], 'budget': task['execution']['budget']}
            cases.append({'case_id': task['id'], 'case_hash': digest(task), 'source_hash': digest(brief['files']),
                          'checks_hash': digest(brief['acceptance']), 'contract_hash': text_hash(brief['behavior_contract']),
                          'environment_manifest': environment, 'environment_digest': digest(environment),
                          'trial_id': trial['trial_id'], 'brief_hash': trial['brief_hash']})
    return cases
