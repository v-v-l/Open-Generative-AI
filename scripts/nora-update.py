#!/usr/bin/env python3
"""Merge a pinned upstream revision in a disposable worktree, never in production."""
from __future__ import annotations
import argparse
import datetime
import json
from pathlib import Path
import re
import subprocess
import sys

REPOSITORY = Path(__file__).resolve().parents[1]
UPSTREAM = 'https://github.com/Anil-matcha/Open-Generative-AI.git'


def git(*args, cwd=REPOSITORY, capture=False):
    return subprocess.run(['git', *args], cwd=cwd, text=True, check=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def prepare(repository, target, destination, verify=False):
    if not re.fullmatch(r'[0-9a-f]{40}', target):
        raise ValueError('Use an explicit full upstream commit SHA after reviewing the release')
    if git('status', '--porcelain', cwd=repository, capture=True).strip():
        raise ValueError('Commit or stash local changes before preparing an update')
    remote = git('remote', 'get-url', 'upstream', cwd=repository, capture=True).strip()
    if remote != UPSTREAM:
        raise ValueError('The upstream remote does not match the selected original repository')
    if destination.exists():
        raise ValueError('Candidate path already exists; choose a new destination')
    baseline = git('rev-parse', 'HEAD', cwd=repository, capture=True).strip()
    git('fetch', '--no-tags', 'upstream', target, cwd=repository)
    fetched = git('rev-parse', 'FETCH_HEAD', cwd=repository, capture=True).strip()
    if fetched != target:
        raise ValueError('Fetched commit does not match requested revision')
    git('worktree', 'add', '--detach', str(destination), baseline, cwd=repository)
    # No hooks from a local checkout are executed during update preparation.
    git('-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
        'merge', '--no-edit', '--no-ff', target, cwd=destination)
    report = {'baseline': baseline, 'upstream': target,
              'candidate_commit': git('rev-parse', 'HEAD', cwd=destination, capture=True).strip(),
              'candidate': str(destination), 'verification': 'not_run',
              'promoted': False}
    if verify:
        for command in (['npm', 'ci', '--ignore-scripts', '--workspaces=false'], ['npm', 'run', 'check'],
                        ['npm', 'test'], ['npm', 'run', 'build']):
            subprocess.run(command, cwd=destination / 'nora', check=True)
        subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'nora/backend_tests'], cwd=destination, check=True)
        subprocess.run([sys.executable, 'scripts/test_nora_update.py'], cwd=destination, check=True)
        report['verification'] = 'passed'
    # Evidence stays outside the tracked candidate, so it cannot dirty a release.
    destination.with_suffix('.update-report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, help='Full upstream commit SHA')
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination = (args.destination or REPOSITORY.parent / ('open-generative-ai-update-' + stamp)).resolve()
    try:
        print(json.dumps(prepare(REPOSITORY, args.target, destination, args.verify), indent=2))
    except (ValueError, subprocess.CalledProcessError) as error:
        print(f'Update not promoted: {error}. Any candidate/conflict evidence remains at {destination}.', file=sys.stderr)
        return 1
    print('Review this candidate before promotion. The working branch and live service were not changed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
