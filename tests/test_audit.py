import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from depth_claim_audit.audit import audit, claims, evidence
from depth_claim_audit.phrases import DEPTH, NODEPTH
from tests.cases import POSITIVE, NEGATIVE

FIXTURES = Path(__file__).parent / 'fixtures'


class ClaimsTests(unittest.TestCase):
    def test_fences(self):
        for fence in ('```', '~~~', '   ````'):
            self.assertEqual(claims(fence+'\ndepth estimation\n'+fence), (False, False))
    def test_inline(self):
        self.assertEqual(claims('Uses `depth estimation`.'), (True, False))
    def test_negative_removal(self):
        self.assertEqual(claims('does not estimate depth'), (False, True))
    def test_hyphens(self):
        self.assertEqual(claims('depth-estimation'), (True, False))
    def test_contractions(self):
        self.assertEqual(claims("doesn't estimate depth"), (False, True))
    def test_paragraph_join(self):
        self.assertEqual(claims('supports monocular\ndepth estimation'), (True, False))
        self.assertEqual(claims('depth\n\nestimation'), (False, False))
    def test_longest_first(self):
        self.assertEqual(claims('does not estimate depth from images'), (False, True))
        self.assertEqual(claims('no depth maps; estimates depth'), (True, True))
    def test_boundaries(self):
        self.assertEqual(claims('xdepth mapsx'), (False, False))
    def test_tuple_order(self):
        for values in (DEPTH, NODEPTH):
            self.assertEqual(list(values), sorted(values, key=len, reverse=True))
            self.assertEqual(len(values), len(set(values)))


class EvidenceTests(unittest.TestCase):
    pass


def make_case(source, expected):
    def test(self):
        self.assertEqual(evidence(source), expected, source)
    return test

for index, source in enumerate(POSITIVE):
    setattr(EvidenceTests, 'test_positive_%02d' % index, make_case(source, True))
for index, source in enumerate(NEGATIVE):
    setattr(EvidenceTests, 'test_negative_%02d' % index, make_case(source, False))
for index, phrase in enumerate(DEPTH):
    setattr(ClaimsTests, 'test_depth_%02d' % index, lambda self, phrase=phrase: self.assertEqual(claims(phrase), (True, False)))
for index, phrase in enumerate(NODEPTH):
    setattr(ClaimsTests, 'test_nodepth_%02d' % index, lambda self, phrase=phrase: self.assertEqual(claims(phrase), (False, True)))


class IntegrationTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'depth_claim_audit', *map(str, args)], capture_output=True, text=True)
    def test_good(self):
        self.assertEqual(audit(FIXTURES/'good')['findings'], [])
    def test_bad(self):
        result = self.cli(FIXTURES/'bad', '--json')
        self.assertEqual(result.returncode, 2)
        value = json.loads(result.stdout)
        self.assertEqual(set(value), {'verdict', 'findings', 'files_scanned'})
        self.assertEqual(value['verdict'], 'FAIL')
        self.assertEqual([(f['severity'], f['rule']) for f in value['findings']], [('HIGH', 'documented-depth-claim-false')])
        self.assertTrue(value['findings'][0]['message'])
    def test_testonly(self):
        for flags, code in [((), 0), (('--fail-on', 'MEDIUM'), 2)]:
            result = self.cli(FIXTURES/'testonly', '--json', *flags)
            self.assertEqual(result.returncode, code)
            self.assertEqual([(f['severity'], f['rule']) for f in json.loads(result.stdout)['findings']], [('MEDIUM', 'documented-depth-claim-false')])
    def test_no_depth(self):
        result = self.cli(FIXTURES/'no-depth', '--json')
        self.assertEqual(result.returncode, 2)
        self.assertEqual([(f['severity'], f['rule']) for f in json.loads(result.stdout)['findings']], [('HIGH', 'documented-no-depth-claim-false')])
    def test_no_claim(self):
        self.assertEqual(audit(FIXTURES/'no-claim')['verdict'], 'PASS')
    def test_ignore(self):
        self.assertEqual(audit(FIXTURES/'bad', ['README.*'])['findings'], [])
        self.assertEqual(audit(FIXTURES/'good', ['*.py'])['findings'][0]['severity'], 'HIGH')
    def test_verbose(self):
        result = self.cli(FIXTURES/'good', '--verbose')
        self.assertEqual(result.returncode, 0)
        self.assertIn('Files scanned: 2', result.stdout)
    def test_version(self):
        result = self.cli('--version')
        self.assertEqual((result.returncode, result.stdout.strip()), (0, '0.1.0'))
    def test_invalid_root(self):
        self.assertEqual(self.cli(FIXTURES/'missing').returncode, 1)
        self.assertEqual(self.cli(FIXTURES/'good/README.md').returncode, 1)
    def test_usage(self):
        for args in [(), ('--wrong',), (str(FIXTURES/'good'), '--fail-on', 'LOW')]:
            self.assertEqual(self.cli(*args).returncode, 1)
    def test_exclusions(self):
        for filename in ['fixtures/a.py', 'docs/a.py', 'examples/a.py', 'tests/a.py', 'test_a.py', 'a_test.py']:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root/'README.md').write_text('estimates depth')
                path = root/filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('import cv2\ncv2.StereoBM_create()')
                expected = 'MEDIUM' if filename.startswith(('tests/', 'test_')) or filename.endswith('_test.py') else 'HIGH'
                self.assertEqual(audit(root)['findings'][0]['severity'], expected)
    def test_nested_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'nested/docs').mkdir(parents=True)
            (root/'nested/docs/guide.md').write_text('estimates depth')
            (root/'other.md').write_text('does not estimate depth')
            self.assertEqual(len(audit(root)['findings']), 1)
            self.assertEqual(audit(root)['files_scanned'], 1)
    def test_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'README.md').write_text('estimates depth')
            (root/'fixtures').mkdir()
            (root/'fixtures/app.py').write_text('import cv2\ncv2.StereoBM_create()')
            (root/'app.py').symlink_to(root/'fixtures/app.py')
            (root/'linked').symlink_to(root/'fixtures', target_is_directory=True)
            self.assertEqual(audit(root)['findings'][0]['severity'], 'HIGH')
            self.assertEqual(audit(root)['files_scanned'], 1)


if __name__ == '__main__':
    unittest.main()
