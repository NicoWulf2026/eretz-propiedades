"""Reproducible Git/component inventory; never opens environment files or databases."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ['git', '-c', f'safe.directory={root.as_posix()}', '-c', 'core.quotepath=false',
         '-C', str(root), *args],
        text=True, encoding='utf-8', errors='replace',
    ).strip()


def component(path: str) -> str:
    prefix = path.split('/')[0]
    return prefix if '/' in path else 'root'


def inspect_module(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    imports = set()
    symbols = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or '')
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
    return {'imports': sorted(imports), 'symbols': sorted(symbols)}


def audit(root: Path, worktrees: list[Path]) -> dict:
    refs = git(root, 'for-each-ref', '--format=%(refname)', 'refs/heads', 'refs/remotes', 'refs/tags').splitlines()
    lineage = []
    for ref in refs:
        counts = git(root, 'rev-list', '--left-right', '--count', f'{ref}...HEAD').split()
        paths = git(root, 'ls-tree', '-r', '--name-only', ref).splitlines()
        lineage.append({'ref': ref, 'head': git(root, 'rev-parse', ref),
                        'ref_exclusive_commits': int(counts[0]), 'candidate_exclusive_commits': int(counts[1]),
                        'tracked_components': dict(Counter(map(component, paths)))})
    inventories = []
    for worktree in worktrees:
        tracked = git(worktree, 'ls-files').splitlines()
        extra = git(worktree, 'ls-files', '--others', '--exclude-standard').splitlines()
        code = []
        for name in tracked + extra:
            if Path(name).name.startswith('.env'):
                continue
            if Path(name).suffix not in ('.py', '.ts', '.tsx', '.sql', '.mjs'):
                continue
            path = worktree / name
            if not path.is_file():
                continue
            row = {'path': name, 'tracked': name in tracked,
                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            if path.suffix == '.py':
                try:
                    row.update(inspect_module(path))
                except (SyntaxError, UnicodeError) as exc:
                    row['parse_issue'] = type(exc).__name__
            code.append(row)
        inventories.append({'path': str(worktree), 'head': git(worktree, 'rev-parse', 'HEAD'),
                            'status': git(worktree, 'status', '--porcelain'),
                            'tracked_components': dict(Counter(map(component, tracked))), 'code': code})
    return {'schema': 'eretz_lineage_audit_v1', 'candidate_head': git(root, 'rev-parse', 'HEAD'),
            'refs': lineage, 'worktrees': inventories,
            'scope_limit': 'Source inventory and lineage, not proof of behavioral equivalence. Ignored operational datasets are separately audited.'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worktree', action='append', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = audit(root, args.worktree)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'refs': len(result['refs']), 'worktrees': len(result['worktrees']),
                      'code_files': sum(len(w['code']) for w in result['worktrees'])}))


if __name__ == '__main__':
    main()
