"""Start a lesson process so that everything it spawns can be killed together.

Why this is harder than proc.kill():
- Killing the lesson process leaves its children running. A child that inherited the
  stdout pipe also keeps it open, so the console reader never sees end-of-file and the
  run never finishes.
- "Kill the tree by walking parent ids" (taskkill /T) misses orphans: a child whose parent
  already exited no longer has a parent link to follow.

Windows answer: a Job Object. A process assigned to a job keeps every process it later
spawns inside that job, orphans included, so TerminateJobObject kills them all.
KILL_ON_JOB_CLOSE also kills them if the server itself dies, because closing the last
handle to the job ends everything in it.
POSIX answer: start the lesson in a new session (its own process group) and killpg it.

Assigning the job happens just after the process starts. A lesson can't spawn anything
in that window: Python interpreter startup alone takes tens of milliseconds.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"

if WINDOWS:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _k32.TerminateJobObject.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _k32.CloseHandle.restype = wintypes.BOOL
    _k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    _k32.GetExitCodeProcess.restype = wintypes.BOOL

    _JOB_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259
    _CREATE_NO_WINDOW = 0x08000000

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    def _new_job() -> int | None:
        job = _k32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = _JOB_LIMIT_KILL_ON_JOB_CLOSE
        if not _k32.SetInformationJobObject(job, _JOB_EXTENDED_LIMIT_INFORMATION,
                                            ctypes.byref(info), ctypes.sizeof(info)):
            _k32.CloseHandle(job)
            return None
        return job


class ProcessTree:
    """One lesson process, its pipes, and the means to kill everything it started."""

    def __init__(self, argv: list[str], *, cwd: Path, env: dict[str, str]):
        kwargs: dict = {}
        if WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        self.proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
        self._job = None
        if WINDOWS:
            job = _new_job()
            if job and _k32.AssignProcessToJobObject(job, int(self.proc._handle)):
                self._job = job
            elif job:
                _k32.CloseHandle(job)   # fall back to taskkill /T, which can miss orphans

    @property
    def uses_job_object(self) -> bool:
        return self._job is not None

    def kill_tree(self) -> None:
        """Kill the lesson process and everything it spawned. Safe to call more than once."""
        if WINDOWS:
            if self._job is not None:
                _k32.TerminateJobObject(self._job, 1)
            elif self.proc.poll() is None:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True)
        else:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def close(self) -> None:
        if WINDOWS and self._job is not None:
            _k32.CloseHandle(self._job)   # KILL_ON_JOB_CLOSE: anything still inside dies here too
            self._job = None


def pid_alive(pid: int) -> bool:
    """Is this process still running? (On Windows, os.kill(pid, 0) would *terminate* it.)"""
    if WINDOWS:
        handle = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        code = wintypes.DWORD()
        ok = _k32.GetExitCodeProcess(handle, ctypes.byref(code))
        _k32.CloseHandle(handle)
        return bool(ok) and code.value == _STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
