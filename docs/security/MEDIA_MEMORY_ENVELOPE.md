# Memory-bounded offline preparation and publication

`scripts/home_memory_envelope.py` launches one command on Windows inside a Job
Object. The supervisor joins the job before spawning its child; descendants
inherit membership, including Python redirectors and FFmpeg. Breakaway is not
enabled. The default and maximum allowed job-wide committed-memory limit is
2 GiB. This is an allocation limit, not a promise about total machine RAM, GPU
VRAM, the Windows filesystem cache, or unrelated processes.

Before launch and once per second during execution, the supervisor requires
8 GiB available physical memory. A pressure/observation failure records the
reason and terminates only this job's process tree. An interrupted preparation
item remains unverified and can resume from its checkpoint. Publication can
leave a disabled partial bundle; it must be resumed/reviewed using its owner pin,
not activated merely because an output directory exists.

The existing sampled 1 GiB owned-RSS, GPU-VRAM, disk-space and time guards remain
inside the preparer. Publication copies and hashes bounded chunks and keeps
only catalog metadata in memory. Give publication its own envelope and run it
serially with expensive preparation for predictable resource use.

The Windows sampler caches its ctypes API bindings and structure types once per
process. Creating fresh structure/pointer types on every poll retained their type
graphs in ctypes: a native 2,000-call reproduction grew the pointer cache by 4,000
entries and RSS by about 30 MB despite garbage collection. A regression checks
4,000 parent/child samples without new retained pointer types. Mutable sample
buffers are still allocated separately for each call. The sampler must remain
bounded as well as the media workload it observes.

Example, with actual paths supplied by the operator:

```powershell
python.exe -B scripts/home_memory_envelope.py --report C:\private\new-run.json -- `
  python.exe -B C:\private\reviewed-operator.py
```

The report path must be new. The wrapped operator must retain bounded diagnostics
and record its result; stdout/stderr are discarded instead of being buffered in a
terminal or parent pipe. Check the report's return code and the operator's own
checkpoint/result, not only the supervisor's `finished` state. Use a detached
launcher for long jobs; this module does not install tasks, configure services,
retry failures, publish data or grant authority for its child command.

Native tests deliberately attempt a 256 MiB allocation under a 128 MiB limit,
and two 64 MiB allocations in related processes under the same 128 MiB limit.
They verify allocation refusal in a grandchild and the aggregate limit, while
ordinary work and child exit codes remain functional. Kernel peak-memory counters
were observed to include a refused allocation; those counters must not be
presented as measured resident RAM or as a test that the ceiling was bypassed.
The allocation results and separately sampled working sets are distinct evidence.

Windows Job Objects retain membership/limits for surviving descendants after the
last controller handle closes; this launcher does not set kill-on-handle-close.
For an intentional graceful pause, use the preparer's stop.flag. If a supervisor
or machine dies, inspect process identities and checkpoints before resuming.
Never start a second encoder because a receipt is stale.

For NVENC, bind the desired GPU by UUID using CUDA_VISIBLE_DEVICES and verify
FFmpeg's resulting device list. Its unmasked CUDA numbering need not match
nvidia-smi. A numeric index alone is insufficient device identity evidence.

Microsoft's [job-wide committed-memory limit](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information)
documents allocation refusal above the aggregate limit. See also
[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
for inheritance and lifecycle semantics.
