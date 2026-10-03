from __future__ import annotations

from typing import Any, Iterable

from libs.runtime.entrypoint_common import to_int


def summarize_process_tree(
    rows: Iterable[dict[str, Any]],
    *,
    owner_pid: int = 0,
) -> dict[str, Any]:
    """Collapse a Windows launcher/child process tree into logical sessions."""
    processes: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        pid = to_int(row.get("pid") or row.get("ProcessId"), 0)
        if pid <= 0 or pid in seen:
            continue
        seen.add(pid)
        processes.append(
            {
                "pid": pid,
                "parent_pid": to_int(
                    row.get("parent_pid") or row.get("ParentProcessId"),
                    0,
                ),
            }
        )

    process_ids = {row["pid"] for row in processes}
    roots = [
        row["pid"]
        for row in processes
        if row["parent_pid"] not in process_ids
    ]
    owner = to_int(owner_pid, 0)
    if not processes:
        tree_state = "NO_PROCESS"
    elif owner > 0 and owner not in process_ids:
        tree_state = "OWNER_MISSING"
    elif len(roots) > 1:
        tree_state = "DUPLICATE_SESSION"
    else:
        tree_state = "NORMAL_PROCESS_TREE"

    return {
        "raw_process_count": len(processes),
        "logical_session_count": len(roots),
        "root_pids": sorted(roots),
        "processes": [
            {
                **row,
                "is_owner": owner > 0 and row["pid"] == owner,
            }
            for row in sorted(processes, key=lambda item: item["pid"])
        ],
        "tree_state": tree_state,
    }
