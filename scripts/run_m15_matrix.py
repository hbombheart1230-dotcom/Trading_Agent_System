# scripts/run_m15_matrix.py
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "scripts" / "demo_m15_smoke.py"


def _run(cmd: list[str], env: dict) -> Tuple[int, str]:
    p = subprocess.run(
        cmd,
        env=env,
        text=True,
        capture_output=True,
    )
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    return p.returncode, out


def _apply_env_overrides(base_env: Dict[str, str], overrides: Dict[str, Any]) -> Dict[str, str]:
    """
    Make scenario env deterministic.

    Rules:
      - value is None  -> remove key from env (unset)
      - value is str   -> set env[key] = value (can be empty string "")
      - other types    -> cast to str and set
    """
    env = dict(base_env)
    for k, v in overrides.items():
        if v is None:
            env.pop(k, None)  # hard-unset (prevents host env leakage)
        else:
            env[k] = str(v)
    return env


def run_scenario(
    name: str,
    env_overrides: Dict[str, Any],
    *,
    expected_block_substr: Optional[str] = None,
    expected_contains: Optional[str] = None,
) -> int:
    env = _apply_env_overrides(os.environ.copy(), env_overrides)

    print(f"\n--- {name} ---")
    print(
        "ENV:",
        f"APPROVAL_MODE={env.get('APPROVAL_MODE')}",
        f"AUTO_APPROVE={env.get('AUTO_APPROVE')}",
        f"EXECUTION_ENABLED={env.get('EXECUTION_ENABLED')}",
        f"KIWOOM_MODE={env.get('KIWOOM_MODE')}",
        f"ALLOW_REAL_EXECUTION={env.get('ALLOW_REAL_EXECUTION')}",
        f"SYMBOL_ALLOWLIST={env.get('SYMBOL_ALLOWLIST')}",
        f"MAX_ORDER_QTY={env.get('MAX_ORDER_QTY')}",
        f"MAX_ORDER_NOTIONAL={env.get('MAX_ORDER_NOTIONAL')}",
        f"DEMO_SYMBOL={env.get('DEMO_SYMBOL')}",
        f"DEMO_QTY={env.get('DEMO_QTY')}",
        f"DEMO_PRICE={env.get('DEMO_PRICE')}",
        f"DEMO_DO_APPROVE={env.get('DEMO_DO_APPROVE')}",
    )

    cmd = [sys.executable, str(DEMO), "--clear"]
    code, out = _run(cmd, env)

    # Block-expected scenarios: treat as PASS if substring matched
    if expected_block_substr:
        if expected_block_substr in out:
            print(f"[PASS-BLOCK] matched: {expected_block_substr}")
            return 0
        print("[FAIL] expected block not detected.")
        print(out)
        return 1

    # Normal scenarios must exit cleanly
    if code != 0:
        print("[FAIL] non-zero exit")
        print(out)
        return code

    # Optional content assertion
    if expected_contains and expected_contains not in out:
        print("[FAIL] expected output not detected.")
        print(f"expected_contains: {expected_contains}")
        print(out)
        return 1

    return 0


def main() -> int:
    print("=== M15 Scenario Matrix Runner ===")
    print(f"demo: {DEMO}")
    print("note: S6(real+exec+allow) is intentionally NOT run as a SUCCESS path (it could hit network).")
    print("      Instead we test real-mode guards that should BLOCK before token/HTTP.")
    print("      This runner hard-unsets env keys when overrides value is None.\n")

    scenarios: list[tuple[str, Dict[str, Any], Optional[str], Optional[str]]] = [
        # Base 4
        ("S1_mock_manual_execfalse", dict(
            KIWOOM_MODE="mock",
            APPROVAL_MODE="manual",
            AUTO_APPROVE=None,            # hard-unset
            EXECUTION_ENABLED="false",
        ), None, None),

        ("S2_mock_auto_execfalse", dict(
            KIWOOM_MODE="mock",
            APPROVAL_MODE="auto",
            AUTO_APPROVE=None,
            EXECUTION_ENABLED="false",
        ), None, None),

        ("S3_mock_auto_exectrue", dict(
            KIWOOM_MODE="mock",
            APPROVAL_MODE="auto",
            AUTO_APPROVE=None,
            EXECUTION_ENABLED="true",
        ), None, None),

        ("S4_real_manual_execfalse", dict(
            KIWOOM_MODE="real",
            APPROVAL_MODE="manual",
            AUTO_APPROVE=None,
            EXECUTION_ENABLED="false",
            ALLOW_REAL_EXECUTION=None,
        ), None, None),

        # Real allow gate
        ("S5_real_auto_exectrue_allowfalse", dict(
            KIWOOM_MODE="real",
            APPROVAL_MODE="auto",
            AUTO_APPROVE=None,
            EXECUTION_ENABLED="true",
            ALLOW_REAL_EXECUTION="false",
            SYMBOL_ALLOWLIST="000660",
            DEMO_SYMBOL="000660",
        ), "Real execution is not allowed. Set ALLOW_REAL_EXECUTION=true", None),

        # Allowlist block should happen BEFORE token/HTTP
        ("S6_real_allowtrue_allowlist_block", dict(
            KIWOOM_MODE="real",
            APPROVAL_MODE="auto",
            AUTO_APPROVE=None,
            EXECUTION_ENABLED="true",
            ALLOW_REAL_EXECUTION="true",
            SYMBOL_ALLOWLIST="000660",
            DEMO_SYMBOL="005930",
        ), "Symbol '005930' is not allowed by SYMBOL_ALLOWLIST", None),

        # Qty / Notional guards (mock)
        ("S7_mock_max_qty_block", dict(
            KIWOOM_MODE="mock",
            APPROVAL_MODE="auto",
            AUTO_APPROVE=None,
            EXECUTION_ENABLED="true",
            MAX_ORDER_QTY="1",
            DEMO_QTY="2",
            DEMO_SYMBOL="005930",
        ), "exceeds MAX_ORDER_QTY=1", None),

        ("S8_mock_max_notional_block", dict(
            KIWOOM_MODE="mock",
            APPROVAL_MODE="auto",
            AUTO_APPROVE=None,
            EXECUTION_ENABLED="true",
            MAX_ORDER_NOTIONAL="1000",
            DEMO_QTY="2",
            DEMO_PRICE="600",   # 2*600=1200 > 1000
            DEMO_SYMBOL="005930",
        ), "exceeds MAX_ORDER_NOTIONAL=1000", None),

        # Legacy AUTO_APPROVE compatibility:
        # - Remove APPROVAL_MODE completely so legacy fallback is deterministic
        ("S9_legacy_autoapprove_true", dict(
            KIWOOM_MODE="mock",
            APPROVAL_MODE="",     # <- None 말고 "" (키 존재 → .env가 덮어쓰지 못함)
            AUTO_APPROVE="true",
            EXECUTION_ENABLED="false",
        ), None, "APPROVAL_MODE=auto"),

        ("S10_legacy_autoapprove_false", dict(
            KIWOOM_MODE="mock",
            APPROVAL_MODE="",     # <- None 말고 ""
            AUTO_APPROVE="false",
            EXECUTION_ENABLED="false",
        ), None, "APPROVAL_MODE=manual"),

        # Manual -> approve path regression (mock only, safe)
        ("S11_mock_manual_then_approve_execfalse", dict(
            KIWOOM_MODE="mock",
            APPROVAL_MODE="manual",
            AUTO_APPROVE=None,
            EXECUTION_ENABLED="false",
            DEMO_DO_APPROVE="true",
        ), None, "DEMO_DO_APPROVE=True"),

        ("S12_mock_manual_then_approve_exectrue", dict(
            KIWOOM_MODE="mock",
            APPROVAL_MODE="manual",
            AUTO_APPROVE=None,
            EXECUTION_ENABLED="true",
            DEMO_DO_APPROVE="true",
        ), None, "[approve]"),
    ]

    for name, env_overrides, expected_block, expected_contains in scenarios:
        rc = run_scenario(
            name,
            env_overrides,
            expected_block_substr=expected_block,
            expected_contains=expected_contains,
        )
        if rc != 0:
            print(f"[FAIL] {name}")
            return rc
        print(f"[OK] {name}")

    print("\n=== DONE ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
