#!/usr/bin/env python3
"""Re-run the check suite on the LOWEST Python this package claims to support.

Why this exists. Until 2026-08-15 this package carried two different
Requires-Python values in two different trees (>=3.8 and >=3.9) and had never
once been executed below 3.13. Both numbers were assertions. A floor nobody
runs is not a supported version, it is a hope printed in metadata - and it is
the kind of claim `neosignal-check` itself exists to catch in other people's
software, so shipping one here would be the tool failing its own test.

This job closes that loop mechanically: it reads the floor out of
pyproject.toml rather than taking it as an argument, so it cannot drift from
what the package actually advertises, then runs the real suite on that exact
interpreter and fails loudly if it does not pass.

    python ops/min_python_job.py

Exit 0 = the advertised floor genuinely runs the suite.
Exit 1 = the floor is not supported; either fix the code or raise the floor.
Exit 2 = the job could not run the check at all (missing uv, unparseable
         metadata). NOT a pass - an unrun check is never a passing check, which
         is the same rule the suite enforces on itself with EXPECTED_CHECKS.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
SUITE = ROOT / "test_neosignal_check.py"


def advertised_floor():
    """Lowest Python version named in requires-python, e.g. '3.8'.

    Parsed with a regex rather than tomllib on purpose: tomllib is 3.11+, and a
    job whose whole subject is old-interpreter support should not itself refuse
    to start on one.
    """
    if not PYPROJECT.is_file():
        return None, "pyproject.toml not found at %s" % PYPROJECT
    text = PYPROJECT.read_text(encoding="utf-8")
    # Only the real key, never a mention inside a comment or a docstring.
    m = re.search(r"""^\s*requires-python\s*=\s*["']([^"']+)["']""",
                  text, re.MULTILINE)
    if not m:
        return None, "no requires-python key in pyproject.toml"
    spec = m.group(1)
    got = re.search(r">=\s*(\d+\.\d+)", spec)
    if not got:
        return None, "requires-python %r has no >= lower bound to test" % spec
    return got.group(1), None


def main():
    floor, err = advertised_floor()
    if err:
        print("CANNOT RUN - %s" % err)
        return 2
    if not SUITE.is_file():
        print("CANNOT RUN - suite not found at %s" % SUITE)
        return 2
    if not shutil.which("uv"):
        print("CANNOT RUN - uv is not on PATH, so the %s interpreter cannot be "
              "provisioned. Install uv, or run the suite on a real %s yourself."
              % (floor, floor))
        return 2

    print("advertised floor: Python %s (from requires-python)" % floor)
    cmd = ["uv", "run", "--no-project", "-p", floor, "python", str(SUITE)]
    print("running: %s" % " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(ROOT))

    if proc.returncode != 0:
        print("\nFAILED - the suite does not pass on Python %s, which this "
              "package advertises as supported. Either fix the code or raise "
              "requires-python. Do not ship the claim unbacked." % floor)
        return 1
    print("\nOK - Python %s is a supported floor and the suite proves it."
          % floor)
    return 0


if __name__ == "__main__":
    sys.exit(main())
