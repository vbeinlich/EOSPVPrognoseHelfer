"""Append-only native sidecars and one atomic, backwards-compatible catalog."""

import json
from datetime import UTC, datetime

from . import economics_native
from . import replay_contract as contract
from .replay_worker_io import WorkerError, read, sha, write

CATALOG_CONTRACT = "eos-pv-helper/replay-worker-catalog-v1"
RECEIPT_CONTRACT = "eos-pv-helper/replay-worker-receipt-v1"


class Catalog:
    def __init__(self, root):
        self.root = root

    def load(self):
        path = self.root / "catalog.json"
        if not path.exists() and not path.is_symlink():
            return None
        raw = read(path, contract.MAX_BYTES)
        value = contract.decode(raw)
        index = value.get("worker_catalog", {})
        entries = index.get("entries", {})
        if index.get("contract") != CATALOG_CONTRACT or set(entries) != {
            p["source_solution_sha256"] for p in value["plans"]
        }:
            raise WorkerError("catalog_index_invalid")
        for plan in value["plans"]:
            source_hash = plan["source_solution_sha256"]
            entry = entries[source_hash]
            sidecar = read(self.root / "verified" / (source_hash + ".json"))
            receipt_raw = read(self.root / "receipts" / (source_hash + ".json"))
            receipt = json.loads(receipt_raw)
            contract.check_seal(receipt)
            if (sha(sidecar) != entry.get("sidecar_file_sha256")
                    or sha(receipt_raw) != entry.get("receipt_file_sha256")
                    or contract.decode(sidecar)["plans"] != [plan]
                    or receipt.get("contract") != RECEIPT_CONTRACT
                    or receipt.get("source_solution_sha256") != source_hash
                    or receipt.get("sidecar_file_sha256") != sha(sidecar)
                    or receipt.get("eos_revision") != economics_native.EOS_REVISION
                    or receipt.get("historical_execution_proven") is not False):
                raise WorkerError("catalog_immutable_binding_invalid")
        return value

    def add(self, candidate, binding, metrics):
        previous = self.load()
        parsed = contract.decode(candidate)
        if len(parsed["plans"]) != 1:
            raise WorkerError("candidate_not_single_plan")
        plan = parsed["plans"][0]
        source_hash = plan["source_solution_sha256"]
        if binding.get("source_solution_sha256") != source_hash:
            raise WorkerError("candidate_source_mismatch")
        entries = dict(previous["worker_catalog"]["entries"]) if previous else {}
        plans = list(previous["plans"]) if previous else []
        if source_hash in entries:
            if next(p for p in plans if p["source_solution_sha256"] == source_hash) != plan:
                raise WorkerError("immutable_conflict")
            return
        if len(plans) >= 4096:
            raise WorkerError("catalog_plan_budget_exceeded")
        sidecar_path = self.root / "verified" / (source_hash + ".json")
        receipt_path = self.root / "receipts" / (source_hash + ".json")
        write(sidecar_path, candidate, immutable=True)
        if receipt_path.exists():
            receipt_raw = read(receipt_path)
            receipt = json.loads(receipt_raw)
            contract.check_seal(receipt)
            if any(receipt.get(k) != v for k, v in binding.items()):
                raise WorkerError("immutable_receipt_conflict")
            if receipt.get("sidecar_file_sha256") != sha(candidate):
                raise WorkerError("immutable_receipt_conflict")
        else:
            receipt = contract.seal({
                **binding,
                "contract": RECEIPT_CONTRACT,
                "created_at_utc": datetime.now(UTC).isoformat(),
                "sidecar_file_sha256": sha(candidate),
                "eos_revision": economics_native.EOS_REVISION,
                "historical_execution_proven": False,
                "metrics": metrics,
            })
            receipt_raw = contract.canonical(receipt)
            write(receipt_path, receipt_raw, immutable=True)
        entries[source_hash] = {
            "sidecar_file_sha256": sha(candidate),
            "receipt_file_sha256": sha(receipt_raw),
        }
        value = contract.catalog(plans + [plan])
        value = contract.seal({
            **{k: v for k, v in value.items() if k != "sha256"},
            "worker_catalog": {"contract": CATALOG_CONTRACT, "entries": entries},
        })
        raw = contract.canonical(value)
        contract.decode(raw)
        if len(raw) > contract.MAX_BYTES:
            raise WorkerError("catalog_byte_budget_exceeded")
        write(self.root / "catalog.json", raw)
