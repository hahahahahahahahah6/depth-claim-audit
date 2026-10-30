"""Offline documentation and Python source inspection."""
import ast
import fnmatch
import os
import re
from pathlib import Path
from .phrases import DEPTH, NODEPTH


def claims(text):
    lines = []
    fence = None
    for line in text.splitlines():
        if fence:
            if re.match(r'^ {0,3}' + re.escape(fence[0]) + '{' + str(fence[1]) + r',}\s*$', line):
                fence = None
            continue
        match = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if match:
            fence = (match[1][0], len(match[1]))
            lines.append('')
        else:
            lines.append(line)
    positive = negative = False
    for paragraph in re.split(r'\n\s*\n', '\n'.join(lines)):
        paragraph = ' '.join(paragraph.lower().replace('’', "'").replace("n't", ' not').replace('-', ' ').split())
        for phrase in sorted(NODEPTH, key=len, reverse=True):
            paragraph, count = re.subn(r'\b' + re.escape(phrase) + r'\b', ' ', paragraph)
            negative |= bool(count)
        for phrase in sorted(DEPTH, key=len, reverse=True):
            if re.search(r'\b' + re.escape(phrase) + r'\b', paragraph):
                positive = True
    return positive, negative


def evidence(source):
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    aliases = {}
    shadowed = set()
    # Resolve imports only within this module; never inspect other source modules.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            shadowed.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            shadowed.add(node.id)
        elif isinstance(node, ast.arg):
            shadowed.add(node.arg)
    for node in tree.body:
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for item in node.names:
                if item.name != '*':
                    aliases[item.asname or item.name] = node.module + '.' + item.name
    def resolve(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, '') if node.id not in shadowed else ''
        if isinstance(node, ast.Attribute):
            base = resolve(node.value)
            return base + '.' + node.attr if base else ''
        return ''
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        path = resolve(node.func)
        parts = path.split('.')
        provider = parts[0]
        last = parts[-1]
        arg = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
        if provider == 'transformers':
            if last == 'pipeline' and arg == 'depth-estimation':
                return True
            models = {'DPTForDepthEstimation', 'DepthAnythingForDepthEstimation', 'DepthAnythingV2ForDepthEstimation'}
            if last in models or (last == 'from_pretrained' and len(parts) > 1 and parts[-2] in models):
                return True
        if provider == 'torch' and path.endswith('.hub.load') and isinstance(arg, str) and ('MiDaS' in arg or 'ZoeDepth' in arg):
            return True
        if last == 'DepthAnythingV2' and 'depth_anything' in '.'.join(parts[:-1]):
            return True
        if provider == 'diffusers' and last == 'MarigoldDepthPipeline':
            return True
        if provider == 'cv2' and last in {'StereoBM_create', 'StereoSGBM_create'}:
            return True
    return False


def audit(root, ignore=(), fail_on='HIGH'):
    root = Path(root)
    if not root.is_dir():
        raise ValueError('Root must be a readable directory')
    positive = negative = production = testing = False
    count = 0
    def walk_error(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
        for filename in sorted(files):
            path = Path(directory) / filename
            rel = path.relative_to(root)
            if path.is_symlink() or any(fnmatch.fnmatchcase(rel.as_posix(), pattern) for pattern in ignore):
                continue
            doc = rel.as_posix() == 'README.md' or (path.suffix == '.md' and 'docs' in rel.parts[:-1])
            source = path.suffix == '.py' and not {'fixtures', 'docs', 'examples'}.intersection(rel.parts[:-1])
            if not (doc or source):
                continue
            content = path.read_text(encoding='utf-8', errors='replace')
            count += 1
            if doc:
                yes, no = claims(content)
                positive |= yes
                negative |= no
            if source and evidence(content):
                test = 'tests' in rel.parts[:-1] or filename.startswith('test_') or filename.endswith('_test.py')
                if test:
                    testing = True
                else:
                    production = True
    findings = []
    if positive and not production:
        findings.append(dict(rule='documented-depth-claim-false', severity='MEDIUM' if testing else 'HIGH', message='Documentation promises distance prediction without production source evidence.'))
    if negative and production:
        findings.append(dict(rule='documented-no-depth-claim-false', severity='HIGH', message='Documentation denies distance prediction but production source evidence exists.'))
    failed = any(f['severity'] == 'HIGH' or fail_on == 'MEDIUM' for f in findings)
    return dict(verdict='FAIL' if failed else 'PASS', findings=findings, files_scanned=count)
