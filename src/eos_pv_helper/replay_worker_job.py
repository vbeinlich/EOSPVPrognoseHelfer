"""One resource-limited native replay. No optimizer search or external I/O."""

import argparse
import os
import resource
import signal
import sys
import time

from . import economics, economics_native, replay_contract, replay_export
from .replay_worker_io import read, sha, write


def deny_external_actions(event, arguments):
    if event.startswith("socket.") or event in (
        "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"
    ):
        # Behave like an OS denial: platform/h5py can handle denied uname probes
        # without executing a process. Never return fabricated model inputs.
        raise PermissionError("offline_replay_external_action_denied")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--timeout", type=int, required=True)
    parser.add_argument("--cpu-seconds", type=int, required=True)
    parser.add_argument("--address-space-mb", type=int, required=True)
    args = parser.parse_args()
    from pathlib import Path

    folder = Path(args.directory)
    if not __import__("re").fullmatch(r"[0-9a-f]{64}", args.sha256):
        return 2
    os.nice(10)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (args.cpu_seconds, args.cpu_seconds))
    budget = args.address_space_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (budget, budget))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32_000_000, 32_000_000))
    signal.setitimer(signal.ITIMER_REAL, args.timeout)

    sys.addaudithook(deny_external_actions)
    start, cpu = time.monotonic(), time.process_time()
    reason = "native_dependency_unavailable"
    try:
        import akkudoktoreos

        reason = "native_source_mismatch"
        economics_native.fingerprint(Path(akkudoktoreos.__path__[0]))
        raw = read(folder / (args.sha256 + ".solution"), 8_000_000)
        if sha(raw) != args.sha256:
            raise ValueError()
        reason = "native_result_or_flow_mismatch"
        plan = replay_export.create_plan(raw)
        value = replay_contract.catalog([plan])
        candidate = replay_contract.canonical(value)
        replay_contract.decode(candidate)
        reason = "verified"
    except ImportError:
        reason = "native_dependency_unavailable"
    except MemoryError:
        reason = "native_memory_limit"
    except OSError:
        reason = "native_io_or_resource_failure"
    except (economics.ComparisonError, replay_contract.ReplayError, ValueError, KeyError, TypeError):
        pass
    metrics = {
        "reason": reason,
        "source_solution_sha256": args.sha256,
        "eos_revision": economics_native.EOS_REVISION,
        "wall_seconds": round(time.monotonic() - start, 6),
        "cpu_seconds": round(time.process_time() - cpu, 6),
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    write(folder / (args.sha256 + ".metrics.json"), replay_contract.canonical(metrics))
    if reason == "verified":
        write(folder / (args.sha256 + ".json"), candidate, immutable=True)
    return 0 if reason == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
