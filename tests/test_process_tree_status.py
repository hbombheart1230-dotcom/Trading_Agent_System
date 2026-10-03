from __future__ import annotations

from libs.runtime.process_tree_status import summarize_process_tree


def test_parent_child_pair_is_one_logical_session() -> None:
    result = summarize_process_tree(
        [
            {"pid": 100, "parent_pid": 1},
            {"pid": 101, "parent_pid": 100},
        ],
        owner_pid=101,
    )

    assert result["raw_process_count"] == 2
    assert result["logical_session_count"] == 1
    assert result["root_pids"] == [100]
    assert result["tree_state"] == "NORMAL_PROCESS_TREE"


def test_two_parent_child_trees_are_duplicate_sessions() -> None:
    result = summarize_process_tree(
        [
            {"pid": 100, "parent_pid": 1},
            {"pid": 101, "parent_pid": 100},
            {"pid": 200, "parent_pid": 1},
            {"pid": 201, "parent_pid": 200},
        ],
        owner_pid=101,
    )

    assert result["raw_process_count"] == 4
    assert result["logical_session_count"] == 2
    assert result["tree_state"] == "DUPLICATE_SESSION"


def test_missing_lock_owner_is_inconsistent() -> None:
    result = summarize_process_tree(
        [{"pid": 100, "parent_pid": 1}],
        owner_pid=999,
    )

    assert result["tree_state"] == "OWNER_MISSING"


def test_empty_process_set_is_not_a_session() -> None:
    result = summarize_process_tree([], owner_pid=0)

    assert result["raw_process_count"] == 0
    assert result["logical_session_count"] == 0
    assert result["tree_state"] == "NO_PROCESS"
