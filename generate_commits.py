"""Utility to generate many small commits for testing repository history analysis.

WARNING: This script will create and commit files in the current git repo.
Run only in a disposable repository or after making a backup.
"""
import subprocess
from pathlib import Path
import time

ROOT = Path(__file__).parent


def run(cmd):
    subprocess.run(cmd, shell=True, check=True)


def main(num=50):
    for i in range(1, num + 1):
        p = ROOT / f'commit_file_{i}.txt'
        p.write_text(f'Commit number {i}\n')
        run(f'git add {p}')
        run(f'git commit -m "chore: add file {p.name}"')
        time.sleep(0.05)


if __name__ == '__main__':
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    print(f'Generating {n} commits (ensure you run this in a disposable repo)')
    main(n)
