#!/usr/bin/env python3
"""Run the kit's unittest modules in parallel, longest first.

Each tests/test_*.py file is its own process. The pool size follows free memory,
and a timing file makes the next run (and --print-shards) start the slow modules
first.
"""

import argparse
import ctypes
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone


# reserve_mb = max(1536, total_mb // 10); each job is assumed to need this much RAM.
DEFAULT_PER_JOB_MB = 400
DEFAULT_TIMEOUT = 1800
TIMES_VERSION = 1

_STOP = threading.Event()
_LIVE = {}
_LIVE_LOCK = threading.Lock()
_TRACK = threading.local()

_WINDOWS_MARKERS = (
    'os.name == "nt"',
    "os.name == 'nt'",
    'sys.platform == "win32"',
    "sys.platform == 'win32'",
    'sys.platform.startswith("win")',
    "sys.platform.startswith('win')",
    'skipUnless(os.name == "nt"',
    "skipUnless(os.name == 'nt'",
)

_RAN_RE = re.compile(r"^Ran (\d+) tests?\b", re.MULTILINE)
_STATUS_RE = re.compile(r"^(OK|FAILED)(?: \(([^)]*)\))?\s*$", re.MULTILINE)
_BLOCK_HEAD_RE = re.compile(r"^(FAIL|ERROR):")


def choose_jobs(available_mb, total_mb, cpus, per_job_mb):
    """Return how many modules to run at once.

    min(cpus, max(1, (available_mb - reserve_mb) // per_job_mb)) with
    reserve_mb = max(1536, total_mb // 10). When memory is unknown, return the
    CPU count (at least 1).
    """
    cpu_cap = int(cpus) if cpus else 0
    per = int(per_job_mb) if per_job_mb else 0
    if per < 1:
        per = DEFAULT_PER_JOB_MB
    if available_mb is None or total_mb is None:
        return cpu_cap if cpu_cap > 0 else 1
    reserve_mb = max(1536, int(total_mb) // 10)
    by_mem = max(1, (int(available_mb) - reserve_mb) // per)
    if cpu_cap < 1:
        return by_mem
    return min(cpu_cap, by_mem)


def _module_time_map(times):
    if not isinstance(times, dict):
        return {}
    modules = times.get("modules")
    if isinstance(modules, dict) and "version" in times:
        return modules
    return times


def _lookup(mapping, name):
    if not isinstance(mapping, dict) or not isinstance(name, str):
        return None
    if name in mapping:
        return mapping[name]
    alternate = name[:-3] if name.endswith(".py") else name + ".py"
    if alternate in mapping:
        return mapping[alternate]
    return None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def estimate_seconds(name, times, sizes):
    """Recorded seconds, or file size / 2000 when the module has no record."""
    record = _lookup(_module_time_map(times), name)
    measured = _number(record)
    if measured is None and isinstance(record, dict):
        measured = _number(record.get("seconds"))
    if measured is not None:
        return measured
    size = _number(_lookup(sizes, name))
    if size is None or size < 0:
        return 0.0
    return size / 2000.0


def order_modules(modules, times, sizes):
    """Longest expected runtime first. Equal times break by module name."""
    return sorted(modules, key=lambda name: (-estimate_seconds(name, times, sizes), name))


def shards(modules, times, sizes, k):
    """Greedy longest-processing-time packing.

    Returns (total_seconds, [module, ...]) for each non-empty shard. The next
    module goes to the shard with the smallest total; ties take the lower index.
    """
    count = int(k)
    if count < 1:
        raise ValueError("k must be positive")
    totals = [0.0] * count
    groups = [[] for _ in range(count)]
    for name in order_modules(list(modules), times, sizes):
        seconds = estimate_seconds(name, times, sizes)
        index = min(range(count), key=lambda i: (round(totals[i], 6), i))
        groups[index].append(name)
        totals[index] += seconds
    return [(totals[i], groups[i]) for i in range(count) if groups[i]]


def _detail_counts(detail):
    counts = {"failures": 0, "errors": 0, "skipped": 0}
    if not detail:
        return counts
    for part in detail.split(","):
        match = re.fullmatch(r"(failures|errors|skipped)=(\d+)", part.strip())
        if match:
            counts[match.group(1)] = int(match.group(2))
    return counts


def parse_result(log_text):
    """Parse unittest's Ran / OK / FAILED summary.

    A log with no Ran line is a crash and counts as one error. Keys: ok, tests,
    failures, errors, skipped.
    """
    text = log_text or ""
    ran_matches = list(_RAN_RE.finditer(text))
    if not ran_matches:
        return {"ok": False, "tests": 0, "failures": 0, "errors": 1, "skipped": 0}
    tests = int(ran_matches[-1].group(1))
    tail = text[ran_matches[-1].end():]
    status_matches = list(_STATUS_RE.finditer(tail))
    if not status_matches:
        return {"ok": False, "tests": tests, "failures": 0, "errors": 1, "skipped": 0}
    kind = status_matches[-1].group(1)
    counts = _detail_counts(status_matches[-1].group(2))
    ok = kind == "OK"
    if ok:
        counts["failures"] = 0
        counts["errors"] = 0
    elif counts["failures"] == 0 and counts["errors"] == 0:
        counts["errors"] = 1
    counts["ok"] = ok
    counts["tests"] = tests
    return counts


def failure_blocks(log_text):
    """Return the FAIL: and ERROR: sections of a unittest log."""
    lines = (log_text or "").splitlines()
    blocks = []
    index = 0
    while index < len(lines):
        if not _BLOCK_HEAD_RE.match(lines[index].strip()):
            index += 1
            continue
        start = index
        if index > 0 and lines[index - 1].startswith("===="):
            start = index - 1
        end = index + 1
        while end < len(lines):
            if lines[end].startswith("====") or lines[end].startswith("Ran "):
                break
            if (lines[end].startswith("----") and end + 1 < len(lines)
                    and lines[end + 1].startswith("Ran ")):
                break
            end += 1
        block = "\n".join(lines[start:end]).strip()
        if block:
            blocks.append(block)
        index = end
    return blocks


def _format_timestamp(now):
    if isinstance(now, str):
        return now
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime or an ISO string")
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _timed_out(result):
    if result.get("timed_out") or result.get("timeout"):
        return True
    return result.get("status") in ("timeout", "TIMEOUT")


def update_times(record, results, now):
    """Exponential moving average of module seconds. Timeouts are left unchanged.

    new = 0.5 * old + 0.5 * measured. The returned record is {"version": 1,
    "modules": {name.py: {"seconds", "runs", "at"}}}. `record` is not mutated.
    """
    modules = {}
    if isinstance(record, dict) and isinstance(record.get("modules"), dict):
        for key, value in record["modules"].items():
            if isinstance(value, dict):
                modules[str(key)] = dict(value)
    stamp = _format_timestamp(now)
    for result in results or []:
        if not isinstance(result, dict) or _timed_out(result) or result.get("finished") is False:
            continue
        name = result.get("name")
        if not name or "seconds" not in result:
            continue
        try:
            measured = float(result["seconds"])
        except (TypeError, ValueError):
            continue
        name = str(name)
        if not name.endswith(".py"):
            name += ".py"
        old = modules.get(name)
        old_seconds = _number(old.get("seconds")) if isinstance(old, dict) else None
        if old_seconds is None:
            seconds = measured
            runs = 1
        else:
            seconds = 0.5 * old_seconds + 0.5 * measured
            try:
                runs = int(old.get("runs")) + 1
            except (TypeError, ValueError, AttributeError):
                runs = 2
        modules[name] = {"seconds": seconds, "runs": runs, "at": stamp}
    return {"version": TIMES_VERSION, "modules": modules}


def windows_modules(sources):
    """Names whose source mentions a Windows-only check. `sources` maps name to text."""
    items = sources.items() if isinstance(sources, dict) else sources
    found = []
    for name, text in items:
        if text and any(marker in text for marker in _WINDOWS_MARKERS):
            found.append(name)
    return found


def default_times_path():
    override = os.environ.get("RUN_TESTS_TIMES")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".local", "state", "lanes", "test-times.json")


def per_job_mb():
    raw = os.environ.get("RUN_TESTS_JOB_MB")
    if not raw:
        return DEFAULT_PER_JOB_MB
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_PER_JOB_MB
    if value < 1:
        return DEFAULT_PER_JOB_MB
    return value


def load_times(path):
    """Load a timing record. A missing or unreadable file is an empty record."""
    empty = {"version": TIMES_VERSION, "modules": {}}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return empty
    if not isinstance(data, dict) or not isinstance(data.get("modules"), dict):
        modules = {}
    else:
        modules = {}
        for key, value in data["modules"].items():
            if isinstance(value, dict):
                modules[str(key)] = dict(value)
    return {"version": TIMES_VERSION, "modules": modules}


def write_times(path, record):
    """Atomically replace `path` with the JSON record (temp file, then os.replace)."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".test-times-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def memory_mb():
    """Return (available_mb, total_mb), or (None, None) when it cannot be read."""
    if os.name == "nt":
        return _windows_memory_mb()
    return _linux_memory_mb()


def _windows_memory_mb():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMORYSTATUSEX)]
        kernel32.GlobalMemoryStatusEx.restype = ctypes.c_int
        ok = kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    except (AttributeError, OSError):
        return None, None
    if not ok:
        return None, None
    megabyte = 1024 * 1024
    return int(status.ullAvailPhys // megabyte), int(status.ullTotalPhys // megabyte)


def _linux_memory_mb():
    path = "/proc/meminfo"
    if not os.path.exists(path):
        return None, None
    available_kb = None
    total_kb = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) < 2:
                    continue
                if parts[0] == "MemAvailable:":
                    available_kb = int(parts[1])
                elif parts[0] == "MemTotal:":
                    total_kb = int(parts[1])
    except (OSError, ValueError):
        return None, None
    if available_kb is None or total_kb is None:
        return None, None
    return available_kb // 1024, total_kb // 1024


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_modules(root, requested):
    """Filenames under tests/. None means the caller should exit with an error."""
    tests_dir = os.path.join(root, "tests")
    if not requested:
        try:
            entries = os.listdir(tests_dir)
        except OSError as error:
            sys.stderr.write("run-tests: cannot read {}: {}\n".format(tests_dir, error))
            return None
        return sorted(entry for entry in entries if entry.startswith("test_") and entry.endswith(".py"))
    names = []
    missing = []
    seen = set()
    for raw in requested:
        filename = os.path.basename(raw)
        if not filename.endswith(".py"):
            filename += ".py"
        if not os.path.isfile(os.path.join(tests_dir, filename)):
            missing.append(raw)
            continue
        if filename not in seen:
            seen.add(filename)
            names.append(filename)
    if missing:
        sys.stderr.write("run-tests: unknown module(s): {}\n".format(", ".join(missing)))
        return None
    return names


def read_sources(root, names):
    sources = {}
    for name in names:
        path = os.path.join(root, "tests", name)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                sources[name] = handle.read()
        except OSError:
            sources[name] = ""
    return sources


def module_sizes(root, names):
    sizes = {}
    for name in names:
        path = os.path.join(root, "tests", name)
        try:
            sizes[name] = os.path.getsize(path)
        except OSError:
            sizes[name] = 0
    return sizes


def format_total(seconds):
    value = round(float(seconds), 3)
    nearest = round(value)
    if abs(value - nearest) < 1e-9:
        return str(int(nearest))
    return "{:.3f}".format(value).rstrip("0").rstrip(".")


def format_module_line(result):
    name = result.get("name") or "?"
    if name.endswith(".py"):
        name = name[:-3]
    if _timed_out(result):
        return "TIMEOUT {}".format(name)
    parsed = result.get("parsed") or {}
    status = "ok" if parsed.get("ok") else "FAIL"
    tests = int(parsed.get("tests") or 0)
    word = "test" if tests == 1 else "tests"
    line = "{:<4} {}  {:.1f}s  {} {}".format(status, name, float(result.get("seconds") or 0), tests, word)
    if parsed.get("ok"):
        skipped = int(parsed.get("skipped") or 0)
        if skipped:
            line = "{} ({} skipped)".format(line, skipped)
        return line
    details = []
    failures = int(parsed.get("failures") or 0)
    errors = int(parsed.get("errors") or 0)
    skipped = int(parsed.get("skipped") or 0)
    if failures:
        details.append("{} {}".format(failures, "failure" if failures == 1 else "failures"))
    if errors:
        details.append("{} {}".format(errors, "error" if errors == 1 else "errors"))
    if skipped:
        details.append("{} skipped".format(skipped))
    if not details:
        details.append("1 error")
    return "{} ({})".format(line, ", ".join(details))


def format_summary(results, wall_seconds, jobs):
    tests = failures = errors = skipped = 0
    occupied = 0.0
    for result in results:
        occupied += float(result.get("seconds") or 0.0)
        if _timed_out(result):
            errors += 1
            continue
        parsed = result.get("parsed") or {}
        tests += int(parsed.get("tests") or 0)
        failures += int(parsed.get("failures") or 0)
        errors += int(parsed.get("errors") or 0)
        skipped += int(parsed.get("skipped") or 0)
    return (
        "run-tests: {modules} modules, {tests} tests, {failures} failures, "
        "{errors} errors, {skipped} skipped in {wall} wall (sum {occupied}, jobs {jobs})"
    ).format(
        modules=len(results),
        tests=tests,
        failures=failures,
        errors=errors,
        skipped=skipped,
        wall="{:.1f}s".format(wall_seconds),
        occupied="{:.1f}s".format(occupied),
        jobs=jobs,
    )


def job_line(jobs, available_mb, total_mb, cpus, per_job_mb, forced):
    if forced:
        return "jobs {}: --jobs".format(jobs)
    if available_mb is None or total_mb is None:
        return "jobs {}: os.cpu_count() (memory unavailable)".format(jobs)
    reserve_mb = max(1536, int(total_mb) // 10)
    formula = "max(1, ({available}MB available - {reserve}MB reserve) // {per}MB)".format(
        available=int(available_mb), reserve=reserve_mb, per=int(per_job_mb))
    if cpus:
        formula = "min({} cpus, {})".format(int(cpus), formula)
    return "jobs {}: {}".format(jobs, formula)


def module_command(filename):
    return [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-p", filename]


def child_env():
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    return env


class TrackingPopen(subprocess.Popen):
    """A Popen that registers the child so Ctrl+C can kill only these pids."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if getattr(_TRACK, "off", False):
            return
        _TRACK.proc = self
        with _LIVE_LOCK:
            _LIVE[self.pid] = self
        if _STOP.is_set():
            kill_process(self)

    def wait(self, timeout=None):
        try:
            return super().wait(timeout=timeout)
        finally:
            if self.poll() is not None:
                with _LIVE_LOCK:
                    _LIVE.pop(self.pid, None)


def kill_process(proc):
    """Stop one child this run started, and that child's own children. By pid only."""
    if proc is None or proc.poll() is not None:
        return
    pid = proc.pid
    _TRACK.off = True
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            try:
                os.killpg(pid, signal.SIGKILL)
            except OSError:
                try:
                    proc.kill()
                except OSError:
                    pass
        try:
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass
    finally:
        _TRACK.off = False
        with _LIVE_LOCK:
            _LIVE.pop(pid, None)


def kill_live():
    with _LIVE_LOCK:
        procs = list(_LIVE.values())
    for proc in procs:
        kill_process(proc)


def _read_log(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _log_is_complete(log_text):
    match = None
    for match in _RAN_RE.finditer(log_text or ""):
        pass
    if match is None:
        return False
    return _STATUS_RE.search(log_text[match.end():]) is not None


def failure_text(log_text):
    blocks = failure_blocks(log_text)
    if blocks:
        return "\n\n".join(blocks)
    lines = (log_text or "").splitlines()
    if not lines:
        return ""
    if len(lines) > 80:
        lines = lines[-80:]
    return "\n".join(lines).strip()


def run_one(root, name, timeout, log_dir):
    """Run one module. None means the run was stopped before the module finished."""
    if _STOP.is_set():
        return None
    log_path = os.path.join(log_dir, name + ".log")
    started = time.monotonic()
    timed_out = False
    kwargs = {
        "cwd": root,
        "env": child_env(),
        "stdin": subprocess.DEVNULL,
        "stderr": subprocess.STDOUT,
        "timeout": timeout,
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        with open(log_path, "wb", buffering=0) as log_handle:
            kwargs["stdout"] = log_handle
            try:
                subprocess.run(module_command(name), **kwargs)
            except subprocess.TimeoutExpired:
                timed_out = True
    except Exception as error:
        if _STOP.is_set():
            return None
        return {
            "name": name,
            "seconds": time.monotonic() - started,
            "timed_out": False,
            "parsed": {"ok": False, "tests": 0, "failures": 0, "errors": 1, "skipped": 0},
            "log": "runner error: {}\n".format(error),
        }
    elapsed = time.monotonic() - started
    if timed_out:
        if _STOP.is_set():
            return None
        return {
            "name": name,
            "seconds": elapsed,
            "timed_out": True,
            "parsed": {"ok": False, "tests": 0, "failures": 0, "errors": 0, "skipped": 0},
            "log": "",
        }
    log_text = _read_log(log_path)
    if _STOP.is_set() and not _log_is_complete(log_text):
        return None
    parsed = parse_result(log_text)
    return {
        "name": name,
        "seconds": elapsed,
        "timed_out": False,
        "parsed": parsed,
        "log": "" if parsed["ok"] else log_text,
    }


def execute(root, ordered, jobs, timeout):
    """Run modules on a thread pool. Returns (results, interrupted, log_dir)."""
    _STOP.clear()
    with _LIVE_LOCK:
        _LIVE.clear()
    if not ordered:
        return [], False, None
    log_dir = tempfile.mkdtemp(prefix="run-tests-")
    old_popen = subprocess.Popen
    subprocess.Popen = TrackingPopen
    pool = ThreadPoolExecutor(max_workers=max(1, int(jobs)))
    futures = []
    names = {}
    seen = set()
    results = []
    interrupted = False

    def consume(future):
        if future in seen or not future.done():
            return
        seen.add(future)
        name = names.get(future, "?")
        try:
            result = future.result()
        except CancelledError:
            return
        except Exception as error:
            result = {
                "name": name,
                "seconds": 0.0,
                "timed_out": False,
                "parsed": {"ok": False, "tests": 0, "failures": 0, "errors": 1, "skipped": 0},
                "log": "runner error: {}\n".format(error),
            }
        if not result:
            return
        results.append(result)
        print(format_module_line(result), flush=True)

    try:
        try:
            for name in ordered:
                future = pool.submit(run_one, root, name, timeout, log_dir)
                futures.append(future)
                names[future] = name
            for future in as_completed(futures):
                consume(future)
        except KeyboardInterrupt:
            interrupted = True
            _STOP.set()
            for future in futures:
                future.cancel()
            kill_live()
    finally:
        _STOP.set()
        kill_live()
        pool.shutdown(wait=True)
        kill_live()
        subprocess.Popen = old_popen
        for future in futures:
            consume(future)
    return results, interrupted, log_dir


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="run-tests",
        description="Run unittest modules in parallel, longest first.",
    )
    parser.add_argument(
        "modules", nargs="*",
        help="module names, with or without .py (default: every tests/test_*.py)",
    )
    parser.add_argument("--jobs", type=int, help="parallel processes (default: from free memory)")
    parser.add_argument(
        "--windows-only", action="store_true",
        help="only modules whose source checks for Windows",
    )
    parser.add_argument(
        "--print-shards", type=int, metavar="K",
        help="print K balanced shards and run nothing",
    )
    parser.add_argument("--times", help="timing record (default: ~/.local/state/lanes/test-times.json)")
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT,
        help="seconds before a module is killed (default: {})".format(DEFAULT_TIMEOUT),
    )
    args = parser.parse_args(argv)
    if args.jobs is not None and args.jobs < 1:
        parser.error("--jobs N must be >= 1")
    if args.print_shards is not None and args.print_shards < 1:
        parser.error("--print-shards K must be >= 1")
    if args.timeout <= 0:
        parser.error("--timeout S must be positive")
    return args


def _print_failures(results):
    texts = []
    for result in results:
        if _timed_out(result) or (result.get("parsed") or {}).get("ok"):
            continue
        text = failure_text(result.get("log") or "")
        if text:
            texts.append(text)
    if texts:
        print()
        print("\n\n".join(texts))
        print()


def _passed(results, expected):
    if len(results) != len(expected):
        return False
    for result in results:
        if _timed_out(result) or not (result.get("parsed") or {}).get("ok"):
            return False
    return True


def main(argv=None):
    args = parse_args(argv)
    root = repo_root()
    names = resolve_modules(root, args.modules)
    if names is None:
        return 2
    if args.windows_only:
        names = windows_modules(read_sources(root, names))
    times_path = args.times or default_times_path()
    record = load_times(times_path)
    sizes = module_sizes(root, names)
    if args.print_shards is not None:
        for total, group in shards(names, record, sizes, args.print_shards):
            print("{} {}".format(format_total(total), " ".join(group)))
        return 0

    per = per_job_mb()
    cpus = os.cpu_count()
    if args.jobs is not None:
        jobs = args.jobs
        print(job_line(jobs, None, None, cpus, per, True), flush=True)
    else:
        available, total = memory_mb()
        jobs = choose_jobs(available, total, cpus, per)
        print(job_line(jobs, available, total, cpus, per, False), flush=True)

    ordered = order_modules(names, record, sizes)
    started = time.monotonic()
    try:
        results, interrupted, log_dir = execute(root, ordered, jobs, args.timeout)
    except KeyboardInterrupt:
        results, interrupted, log_dir = [], True, None
    if interrupted:
        sys.stderr.write("run-tests: interrupted\n")
    _print_failures(results)
    print(format_summary(results, time.monotonic() - started, jobs), flush=True)

    finished = [result for result in results if not _timed_out(result)]
    if finished:
        try:
            write_times(times_path, update_times(record, results, datetime.now(timezone.utc)))
        except OSError as error:
            sys.stderr.write("run-tests: could not write {}: {}\n".format(times_path, error))

    ok = (not interrupted) and _passed(results, ordered)
    if log_dir:
        if ok:
            shutil.rmtree(log_dir, ignore_errors=True)
        else:
            sys.stderr.write("run-tests: logs: {}\n".format(log_dir))
    if interrupted:
        return 130
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
