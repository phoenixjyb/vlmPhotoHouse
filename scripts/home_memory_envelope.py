#!/usr/bin/env python3
"""Windows-only committed-memory ceiling for one offline media process tree.

This supervisor joins a fresh Job Object before creating its child. Descendants
inherit the job; breakaway is not enabled. It neither starts services nor changes
media policy. Run under a detached launcher, not an interactive terminal.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def limits(memory_mib, minimum_free_mib):
    if type(memory_mib) is not int or not 64 <= memory_mib <= 2048:
        raise ValueError('memory_mib must be between 64 and 2048')
    if type(minimum_free_mib) is not int or minimum_free_mib < 8192:
        raise ValueError('minimum_free_mib must be at least 8192')


class WindowsJob:
    def __init__(self, memory_mib):
        if sys.platform != 'win32':
            raise OSError('Windows Job Objects are required; no unbounded fallback')
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', w.DWORD), ('minimum_ws', ctypes.c_size_t),
                        ('maximum_ws', ctypes.c_size_t), ('active_processes', w.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', w.DWORD),
                        ('scheduling', w.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]

        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]

        self.Info = Extended
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.k.CreateJobObjectW.restype = w.HANDLE
        self.k.GetCurrentProcess.restype = w.HANDLE
        self.k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.k.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
        self.k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.k.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.k.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.k.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = Extended()
        info.basic.flags = 0x200  # JOB_OBJECT_LIMIT_JOB_MEMORY; no breakaway flags.
        info.job_memory = memory_mib * 1024**2
        try:
            if not self.k.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.k.AssignProcessToJobObject(self.handle, self.k.GetCurrentProcess()):
                raise ctypes.WinError(ctypes.get_last_error())
            observed = self.summary()
            if observed['limit_bytes'] != info.job_memory or observed['limit_flags'] != 0x200:
                raise OSError('Job memory policy did not round-trip')
        except BaseException:
            self.close()
            raise

    def summary(self):
        info = self.Info()
        if not self.k.QueryInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return {'limit_bytes': info.job_memory, 'limit_flags': info.basic.flags,
                # Windows can include a refused allocation in these high-water
                # counters. They are not measurements of resident/usable RAM.
                'kernel_peak_job_memory_bytes': info.peak_job_memory,
                'kernel_peak_process_memory_bytes': info.peak_process_memory}

    def terminate(self):
        # This also terminates this supervisor. Persist the reason first.
        if not self.k.TerminateJobObject(self.handle, 125):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle)
            self.handle = None
        # No KILL_ON_JOB_CLOSE: surviving descendants retain job membership and
        # its memory ceiling if a supervisor exits unexpectedly. Windows keeps
        # the job alive until all associated processes have exited.


def save(path, value):
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, separators=(',', ':'))
    os.replace(temporary, path)


def run(command, report, memory_mib=2048, minimum_free_mib=8192):
    limits(memory_mib, minimum_free_mib)
    if sys.platform != 'win32':
        raise OSError('Windows Job Objects are required; no unbounded fallback')
    if not command or report.exists() or not report.parent.is_dir():
        raise ValueError('Provide a command and a fresh report path')
    from home_preparation_resources import memory
    if memory()[0] < minimum_free_mib * 1024**2:
        raise OSError('Insufficient available RAM before launch')
    job = WindowsJob(memory_mib)
    value = {'state': 'starting', 'pid': os.getpid(), 'started_at': time.time(),
             'minimum_free_mib': minimum_free_mib, **job.summary()}
    child = None
    try:
        save(report, value)
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        value.update(state='running', child_pid=child.pid)
        save(report, value)
        last_report = time.monotonic()
        while child.poll() is None:
            try:
                available = memory()[0]
                if available < minimum_free_mib * 1024**2:
                    value.update(state='stopped_memory_pressure', available_bytes=available,
                                 finished_at=time.time(), **job.summary())
                    save(report, value)
                    job.terminate()
                if time.monotonic() - last_report >= 15:
                    value.update(observed_at=time.time(), available_bytes=available, **job.summary())
                    save(report, value)
                    last_report = time.monotonic()
            except (OSError, ValueError):
                value.update(state='stopped_observation_failed', finished_at=time.time())
                save(report, value)
                job.terminate()
            time.sleep(1)
        value.update(state='finished', returncode=child.returncode,
                     finished_at=time.time(), **job.summary())
        save(report, value)
        return child.returncode
    except BaseException:
        if child is not None and child.poll() is None:
            value.update(state='stopped_supervisor_failure', finished_at=time.time())
            try:
                save(report, value)
            finally:
                job.terminate()
        raise
    finally:
        job.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--memory-mib', type=int, default=2048)
    parser.add_argument('--minimum-free-mib', type=int, default=8192)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    return run(command, args.report, args.memory_mib, args.minimum_free_mib)


if __name__ == '__main__':
    raise SystemExit(main())
