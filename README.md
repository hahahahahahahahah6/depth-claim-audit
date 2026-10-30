# Audit of per-pixel distance prediction

An offline static checker comparing documentation promises about distance maps
from a single picture or stereo pairs against Python source fingerprints.
Version 0.1.0 requires Python 3.9 or later and has no runtime dependencies.

Install and run:

```sh
python3 -m pip install .
depth-claim-audit ./project
python3 -m depth_claim_audit ./project --json
 depth-claim-audit ./project --verbose --ignore 'vendor/*' --fail-on MEDIUM
depth-claim-audit --version
```

The checker reads root README.md and Markdown files with a docs directory
component. It excludes backtick and tilde fenced blocks, counts inline code,
joins paragraph lines, expands negative contractions, and normalizes hyphens
and whitespace. Exact word-boundary templates are matched longest first;
negative spans are removed before positive matching. Unrelated wording does
not constitute a claim.

Python files are parsed with ast and never executed. Supported evidence comes
from transformers task pipelines and DPT or DepthAnything model construction,
torch.hub MiDaS or ZoeDepth loads, standalone DepthAnythingV2 construction,
diffusers MarigoldDepthPipeline construction, and OpenCV stereo matcher
construction, including imported aliases. The pipeline requires its exact task
as a first positional literal. Model construction alone counts; inference and
output quality are not verified. Bare imports, picture loading, capture,
detection, segmentation, classification, OCR, tracking, flow, strings and
shell helpers provide no evidence. Local definitions shadow imports.

Only imports in the same module are resolved. Dynamic imports, re-exports,
computed task names, indirect factories and runtime behavior are outside scope.
Name shadowing is conservative across a module, including nested definitions;
conditional execution and reachability are not evaluated. Symlink files and
directories are skipped. Source under fixtures, docs and examples is excluded.
Source under tests or named test_*.py or *_test.py is counted only as test
evidence. Invalid syntax supplies no evidence. Repeatable --ignore patterns
use fnmatch against relative POSIX paths. Scanned count includes selected
Markdown and eligible Python files, including tests and invalid source files.

Rules:

```text
documented-depth-claim-false: HIGH when a positive claim lacks production evidence;
                            MEDIUM when evidence exists only in tests.
documented-no-depth-claim-false: HIGH when a negative claim conflicts with production evidence.
```

At most one finding per rule is emitted. Without a claim, the result is PASS.
The default threshold is HIGH; --fail-on MEDIUM also fails on test-only evidence.
Exit 0 means PASS at the chosen threshold, 2 means FAIL, and 1 means an invalid
or unreadable root or CLI usage error. Human output prints verdict and findings;
--verbose adds the scanned count. JSON contains verdict, findings (rule,
severity, message), and files_scanned. A PASS can still contain a MEDIUM finding.

Development:

```sh
python3 -m unittest discover
python3 -m build
```

The source distribution includes the tests and fixtures. This checker provides
source-level hints, not proof that a model runs, produces accurate distances,
or meets any performance or hardware requirements. Licensed under MIT.
