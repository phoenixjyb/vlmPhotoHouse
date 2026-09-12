"""Sample only the coordinator/owned child. Never manage unrelated processes."""
import ctypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


class JobStopped(Exception):
    pass


def memory(process=None):
    """Available physical memory and owned RSS. Sampling is not a hard OS quota."""
    if sys.platform == 'win32':
        from ctypes import wintypes as w
        class Status(ctypes.Structure):
            _fields_ = [('length',w.DWORD),('load',w.DWORD)]+[(n,ctypes.c_ulonglong) for n in
                ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        class Counters(ctypes.Structure):
            _fields_ = [('cb',w.DWORD),('faults',w.DWORD)]+[(n,ctypes.c_size_t) for n in
                ('peak','rss','quota_peak_paged','quota_paged','quota_peak_nonpaged','quota_nonpaged','page','peak_page')]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GlobalMemoryStatusEx.argtypes=[ctypes.POINTER(Status)]
        kernel.GetCurrentProcess.restype=w.HANDLE
        kernel.K32GetProcessMemoryInfo.argtypes=[w.HANDLE,ctypes.POINTER(Counters),w.DWORD]
        status=Status();status.length=ctypes.sizeof(status)
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        handle=int(process._handle) if process is not None else kernel.GetCurrentProcess()
        if not kernel.GlobalMemoryStatusEx(ctypes.byref(status)) or not kernel.K32GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb):
            if process is not None and process.poll() is not None:return status.available,0
            raise OSError(ctypes.get_last_error(),'Cannot measure owned memory')
        return status.available,counters.rss
    pid=process.pid if process is not None else os.getpid()
    if sys.platform.startswith('linux'):
        values=dict(re.findall(r'^(\w+):\s+(\d+)',Path('/proc/meminfo').read_text(),re.M))
        try:status=Path(f'/proc/{pid}/status').read_text()
        except FileNotFoundError:
            if process is not None and process.poll() is not None:return int(values['MemAvailable'])*1024,0
            raise
        return int(values['MemAvailable'])*1024,int(re.search(r'^VmRSS:\s+(\d+)',status,re.M)[1])*1024
    if sys.platform == 'darwin':
        raw=subprocess.check_output(['/usr/bin/vm_stat'],text=True,timeout=2)
        page=int(re.search(r'page size of (\d+) bytes',raw)[1])
        values=dict(re.findall(r'^([^:]+):\s+(\d+)\.',raw,re.M))
        available=sum(int(values[k]) for k in ('Pages free','Pages inactive','Pages speculative'))*page
        result=subprocess.run(['/bin/ps','-o','rss=','-p',str(pid)],capture_output=True,text=True,timeout=2)
        if result.returncode and process is not None and process.poll() is not None:return available,0
        result.check_returncode()
        return available,int(result.stdout.strip())*1024
    raise OSError('Memory observation is unavailable on this platform')


class Guard:
    def __init__(self, workspace, reserve_bytes, minimum_ram=4*1024**3, maximum_rss=1024**3,
                 max_seconds=None, observe=memory):
        self.workspace=workspace;self.reserve=reserve_bytes;self.minimum_ram=minimum_ram
        self.maximum_rss=maximum_rss;self.observe=observe;self.started=time.monotonic()
        self.max_seconds=max_seconds;self.last=-float('inf');self.peak=0;self.ram_floor=None;self.samples=0
        self.last_child=None

    def __call__(self, process=None, force=False, extra_disk=0):
        now=time.monotonic()
        if (self.workspace/'stop.flag').exists():raise JobStopped('operator_stop')
        if self.max_seconds is not None and now-self.started>=self.max_seconds:raise JobStopped('run_time_limit')
        if shutil.disk_usage(self.workspace).free < self.reserve+extra_disk:raise JobStopped('disk_pressure')
        new_child=process is not None and process is not self.last_child
        if not force and not new_child and now-self.last<1:return
        self.last=now
        if process is not None:self.last_child=process
        try:
            available,parent_rss=self.observe(None)
            child_rss=0
            if process is not None:
                child_available,child_rss=self.observe(process);available=min(available,child_available)
        except (OSError,ValueError,KeyError,AttributeError) as error:
            raise JobStopped('resource_observation_failed') from error
        self.peak=max(self.peak,parent_rss,child_rss);self.samples+=1
        self.ram_floor=available if self.ram_floor is None else min(available,self.ram_floor)
        if available<self.minimum_ram:raise JobStopped('memory_pressure')
        if max(parent_rss,child_rss)>self.maximum_rss:raise JobStopped('owned_memory_limit')

    def summary(self):
        return {'samples':self.samples,'observed_peak_rss':self.peak,'observed_minimum_available_ram':self.ram_floor}
