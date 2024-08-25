#!/usr/bin/env python3
# MIT License
#
# Copyright (c) 2024 Armando Montanez
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""An opinionated wrapper for rsync that is conservative about file conflicts."""

import argparse
import logging
from pathlib import Path
import subprocess
import sys
from typing import Sequence, Optional

_RSYNC_FLAGS = (
    '-rptgo',
    '-i',
    '--out-format=(%i) %n',
)

_LOG = logging.getLogger(__name__)


def _log_and_abort(*args):
    _LOG.critical(*args)
    raise ValueError(args[0] % args[1:])


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--verify-integrity', action='store_true')
    parser.add_argument('--force', '-f', action='store_true')
    parser.add_argument('src', type=Path)
    parser.add_argument('dest', type=Path)
    parser.add_argument(
        '--logfile',
        '-l',
        type=Path,
    )
    parser.add_argument(
        '--conflict-file',
        type=Path,
        default=None,
    )
    parser.add_argument(
        '--modified-file',
        type=Path,
        default=None,
    )

    return parser.parse_args()


def _sanitize_path(p: Path):
    if not p.is_dir():
        _log_and_abort('Path `%s` is not a directory', p)
    return str(p) + '/'


def _strip_action_prefix(s: str) -> str:
    return s[s.index(') ') + 2:]


def _run_rsync(args: Sequence[str], src: Path, dest: Path, dry_run: bool):
    cmd = ['rsync', *_RSYNC_FLAGS]
    cmd.extend(args)
    if dry_run:
        cmd.append('--dry-run')
    cmd.append(_sanitize_path(src))
    cmd.append(_sanitize_path(dest))
    _LOG.debug('Running rsync: %s', ' '.join(cmd))
    result = subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        _LOG.debug(result.stdout)
    return result.stdout


def _sync_new_files(src: Path, dest: Path, dry_run: bool):
    _run_rsync(['--ignore-existing'], src, dest, dry_run)

def _update_all_files(src: Path, dest: Path, dry_run: bool):
    _run_rsync([], src, dest, dry_run)

def _check_modified(src: Path, dest: Path, modified_file: Optional[Path]):
    conflicts = _run_rsync([], src, dest, True)
    if conflicts:
        _LOG.warning('Found %d files that have been modified', len(conflicts.splitlines()))
    for d in [src, dest]:
        logfile = d / 'easy-rsync_modified.txt' if not modified_file else modified_file
        with open(logfile, 'w') as f:
            f.write(conflicts)
    return conflicts.splitlines()


def _verify_integrity(src: Path, dest: Path, modified: Sequence[str], conflict_file: Optional[Path]):
    conflicts = _run_rsync(['-c'], src, dest, True).splitlines()
    modmap = {_strip_action_prefix(m): True for m in modified}
    conflicting_items = [c for c in conflicts if _strip_action_prefix(c) not in modmap]
    if conflicting_items:
        _LOG.warning('Found %d files that have bitrot', len(conflicting_items))
    for d in [src, dest]:
        logfile = d / 'easy-rsync_conflicts.txt' if not conflict_file else conflict_file
        with open(logfile, 'w') as f:
            f.write('\n'.join(conflicting_items))
    

def main(
        src: Path,
        dest: Path,
        dry_run: bool,
        force: bool,
        logfile: Optional[Path],
        conflict_file: Optional[Path],
        modified_file: Optional[Path],
        verify_integrity: bool
    ) -> int:
    logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(levelname)s: %(message)s')
    if logfile:
        _LOG.addHandler(logging.FileHandler(filename=logfile))

    if verify_integrity:
        modified = _check_modified(src, dest, modified_file)
        _verify_integrity(src, dest, modified, conflict_file)
    else:
        if force:
            _update_all_files(src, dest, dry_run)
        else:
            _sync_new_files(src, dest, dry_run)
        _check_modified(src, dest, modified_file)
    return 0


if __name__ == "__main__":
    sys.exit(main(**vars(_parse_args())))
