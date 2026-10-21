# Repair brief contract

Write private JSON with exactly these fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1`. |
| `origin_chat_id`, `task_key` | Stable origin and unique task key, reused after compaction. |
| `capability` | `bounded_python_repair`. |
| `source_root` | Absolute real directory, no symlink alias. |
| `files` | At most eight relative `.py` names mapped to `{content, sha256}`. Hash UTF-8 bytes. |
| `editable_paths` | Explicit relative `.py` allowlist, including any new regression files. |
| `supplied_tests` | Nonempty list of existing test files to preserve. Use `test_*.py` names. |
| `behavior_contract` | Known defect, expected behavior and constraints. |
| `independent_tests` | Separate trusted test source by relative `test_*.py` name; never editable or supplied to either repair model. |
| `checks` | Nonempty trusted argv arrays, each `["unittest", "test_oracle"]` or a specific dotted test under an independent module. |

Candidate output is one plain JSON object: `{"files":{"helper.py":"complete source","test_helper.py":"complete tests"},"summary":"explanation"}`. Do not accept Markdown fences or execution claims. Preserve supplied test methods and imports; add a regression that fails on the buggy source and passes on the repair. Independent checks must reproduce the defect on the baseline and pass on the candidate. Untouched supplied tests also run against the candidate source in a separate interpreter, so added setup code cannot weaken the protected checks. Approval must still match when checking finishes. Add regressions to supplied test files in this initial version.

The first execution contract accepts pure helpers using `re`, `hashlib`, `math`, `string`, `collections`, `itertools`, `functools`, `decimal` or `fractions`; tests may import `unittest` and supplied source modules. Public import members and attributes must also appear in the explicit allowlists in `scripts/local_repair/validation.py`; importing one of these modules does not permit every public namespace it exposes. Dynamic execution/introspection, private attributes, decorators, custom classes and attribute mutation (including nested assignment targets) are outside this capability. Test instance fields on `self` are allowed. Unsupported source stays on the ordinary OpenAI workflow. This structural guard is additional to macOS filesystem/network isolation.

No source file is applied by the helper. Obtain the private candidate wrapper from `result_path`, verify its hash, parse `text`, and apply only after `accepted` and a fresh source-hash comparison. Keep job/attempt IDs and native fallback IDs in the normal task record. Do not store credentials in a brief. Full reasoning is not retained.

Model identity additionally requires a private profile's `runtime_catalog` absolute path to the supported owner-trusted LM Studio/Bionic index. Approval binds the runtime key, endpoint, adapter, indexed identifier, root, exact file inventory and discovery metadata as well as the artifact hashes. Missing or mismatched proof never makes an instance ready. This is a trusted local index binding, not in-memory weight attestation. Runtime communication remains HTTP only.
