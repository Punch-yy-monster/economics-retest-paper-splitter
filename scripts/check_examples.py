#!/usr/bin/env python3
"""Run regression checks against example fixtures."""

from __future__ import annotations

import filecmp
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_retest_json.py"
EXAMPLES = ROOT / "examples"


def run_example(example_dir: Path) -> None:
    input_file = example_dir / "input.txt"
    expected_dir = example_dir / "expected"
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--input-file", str(input_file)],
            cwd=tmpdir,
            check=True,
            capture_output=True,
            text=True,
        )
        lines = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        if len(lines) != 3:
            raise RuntimeError(f"{example_dir.name}: expected 3 output paths, got {lines!r}")
        generated_dir = lines[0].parent
        for filename in ["full.json", "interview.json", "written_exam.json"]:
            generated = generated_dir / filename
            expected = expected_dir / filename
            if not filecmp.cmp(generated, expected, shallow=False):
                raise RuntimeError(f"{example_dir.name}: output mismatch for {filename}")


def main() -> int:
    for example_dir in sorted(path for path in EXAMPLES.iterdir() if path.is_dir()):
        run_example(example_dir)
        print(f"{example_dir.name}: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
