from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StepResult:
    name: str
    command: list[str]
    duration_s: float
    return_code: int

    @property
    def ok(self) -> bool:
        return self.return_code == 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_python() -> str:
    root = _repo_root()
    candidate = root / ".venv311" / "Scripts" / "python.exe"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def _default_flutter() -> str:
    preferred = Path(r"C:\src\flutter\flutter\bin\flutter.bat")
    if preferred.exists():
        return str(preferred)
    return "flutter"


def _resolve_executable(command: str) -> str:
    if os.path.isabs(command) or os.path.sep in command:
        return command
    resolved = shutil.which(command)
    return resolved or command


def _run_step(name: str, command: list[str], *, cwd: Path) -> StepResult:
    print(f"\n==> {name}")
    print(" ".join(command))
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=str(cwd), check=False)
    duration_s = time.perf_counter() - started
    result = StepResult(
        name=name,
        command=command,
        duration_s=duration_s,
        return_code=completed.returncode,
    )
    print(
        f"<== {name}: {'PASS' if result.ok else 'FAIL'} "
        f"({duration_s:.1f}s, code={completed.returncode})"
    )
    return result


def _print_summary(results: list[StepResult]) -> None:
    print("\nDay-45 Gate Summary")
    print("-" * 72)
    for row in results:
        status = "PASS" if row.ok else "FAIL"
        print(f"{status:>4}  {row.name:<34} {row.duration_s:>8.1f}s")
    print("-" * 72)
    passed = sum(1 for row in results if row.ok)
    print(f"Passed {passed}/{len(results)} step(s)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Runs the Smart Bed Day-45 execution gate: backend mobile tests, "
            "admin beta tests, Flutter quality checks, and optional smoke flow."
        ),
    )
    parser.add_argument(
        "--python-cmd",
        default=_default_python(),
        help="Python executable for backend checks (default: .venv311 if present).",
    )
    parser.add_argument(
        "--flutter-cmd",
        default=_default_flutter(),
        help="Flutter executable (default: C:\\src\\flutter\\flutter\\bin\\flutter.bat if present).",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8001",
        help="Base URL for mobile smoke flow.",
    )
    parser.add_argument(
        "--skip-flutter",
        action="store_true",
        help="Skip flutter analyze and flutter test.",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip manual smoke flow script (useful if backend is not running).",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    mobile_root = repo_root / "mobile_app"
    python_cmd = _resolve_executable(str(args.python_cmd))
    flutter_cmd = _resolve_executable(str(args.flutter_cmd))

    results: list[StepResult] = []

    results.append(
        _run_step(
            "Backend mobile tests",
            [
                python_cmd,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_mobile*.py",
            ],
            cwd=repo_root,
        )
    )
    if not results[-1].ok:
        _print_summary(results)
        return 2

    results.append(
        _run_step(
            "Backend admin beta tests",
            [
                python_cmd,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_admin_mobile*.py",
            ],
            cwd=repo_root,
        )
    )
    if not results[-1].ok:
        _print_summary(results)
        return 2

    if not args.skip_flutter:
        results.append(
            _run_step(
                "Flutter analyze",
                [flutter_cmd, "analyze"],
                cwd=mobile_root,
            )
        )
        if not results[-1].ok:
            _print_summary(results)
            return 2

        results.append(
            _run_step(
                "Flutter test",
                [flutter_cmd, "test"],
                cwd=mobile_root,
            )
        )
        if not results[-1].ok:
            _print_summary(results)
            return 2

    if not args.skip_smoke:
        results.append(
            _run_step(
                "Mobile smoke flow",
                [
                    python_cmd,
                    "scripts/mobile_smoke.py",
                    "--base-url",
                    str(args.base_url),
                ],
                cwd=repo_root,
            )
        )
        if not results[-1].ok:
            _print_summary(results)
            return 2

    _print_summary(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
