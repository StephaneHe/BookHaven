#!/usr/bin/env python3
"""BookHaven non-regression gate -- run before EVERY delivery.

Replays the whole automated suite that protects the user requirements listed in
docs/USER_REQUIREMENTS.md:
  1. pytest: server/unit tests, Playwright browser tests (desktop + mobile) and
     end-to-end tests (real app on a temporary database). The UI tests start
     their own server on a free port and never write to the library database.
  2. Android JVM unit tests (gradlew testDebugUnitTest), with a JDK 17.

Usage:
    python scripts/run_regression.py              # everything
    python scripts/run_regression.py --skip-android
    python scripts/run_regression.py -- -k webtoon    # extra args go to pytest

Exit code 0 only if every step passed.
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANDROID = os.path.join(ROOT, "android")

# JDK 17 is required by the Android Gradle plugin; the machine default may be older.
JDK_CANDIDATES = [
    os.environ.get("JAVA17_HOME", ""),
    r"C:\Program Files\Microsoft\jdk-17*",
    r"C:\Program Files\Eclipse Adoptium\jdk-17*",
    r"C:\Program Files\Java\jdk-17*",
    r"C:\Program Files\Android\Android Studio\jbr",
]


def java_major(jdk_home):
    """Major Java version from the JDK 'release' file ("1.8.0" -> 8, "17.0.2" -> 17)."""
    try:
        text = open(os.path.join(jdk_home, "release"), encoding="utf-8", errors="replace").read()
    except OSError:
        return 0
    m = re.search(r'JAVA_VERSION="(\d+)(?:\.(\d+))?', text)
    if not m:
        return 0
    major = int(m.group(1))
    return int(m.group(2) or 0) if major == 1 else major


def find_jdk17():
    for pattern in JDK_CANDIDATES:
        for path in sorted(glob.glob(pattern), reverse=True) if pattern else []:
            if os.path.isfile(os.path.join(path, "bin", "java.exe" if os.name == "nt" else "java")):
                if java_major(path) >= 17:
                    return path
    return None


def step(title, cmd, cwd, env=None):
    print(f"\n=== {title} ===\n$ {' '.join(cmd)}", flush=True)
    t0 = time.time()
    rc = subprocess.call(cmd, cwd=cwd, env=env, shell=(os.name == "nt" and cmd[0].endswith(".bat")))
    print(f"--- {title}: {'OK' if rc == 0 else f'FAILED (exit {rc})'} in {time.time() - t0:.0f}s", flush=True)
    return rc == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-android", action="store_true", help="do not run the Android JVM tests")
    ap.add_argument("pytest_args", nargs="*", help="extra pytest arguments (after --)")
    args = ap.parse_args()

    results = {}
    results["pytest (server + browser + e2e)"] = step(
        "pytest (server + browser + e2e)",
        [sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:logging", *args.pytest_args], ROOT)

    if not args.skip_android:
        jdk = find_jdk17()
        gradlew = os.path.join(ANDROID, "gradlew.bat" if os.name == "nt" else "gradlew")
        if not jdk:
            print("\n!!! Android JVM tests NOT run: no JDK 17 found (set JAVA17_HOME). Gate FAILED.")
            results["android JVM tests"] = False
        else:
            env = dict(os.environ, JAVA_HOME=jdk)
            results["android JVM tests"] = step(
                "android JVM tests", [gradlew, "testDebugUnitTest", "-q"], ANDROID, env)

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {'OK    ' if ok else 'FAILED'}  {name}")
    ok = all(results.values())
    print("GATE: PASSED" if ok else "GATE: FAILED -- do not deliver")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
