"""会话持久化：单文件 JSON，保存在 DATA_DIR（容器卷挂载点）。

不使用任何外部数据库；清空会话即删除状态文件。
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Optional

DATA_DIR = os.environ.get("DATA_DIR", "/data")
STATE_FILE = os.path.join(DATA_DIR, "session.json")

_lock = threading.RLock()


def _empty_state() -> dict:
    return {"records": [], "decisions": {}, "uploaded_at": None, "filename": None}


def load_state() -> dict:
    with _lock:
        if not os.path.exists(STATE_FILE):
            return _empty_state()
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            state.setdefault("records", [])
            state.setdefault("decisions", {})
            return state
        except (json.JSONDecodeError, OSError):
            return _empty_state()


def save_state(state: dict) -> None:
    with _lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)


def replace_records(records: list, filename: Optional[str], keep_decisions: bool = True) -> dict:
    """上传新数据：替换记录；默认沿用键值仍存在的旧裁决。"""
    with _lock:
        old = load_state() if keep_decisions else _empty_state()
        valid_keys = {
            f"{r['contestant']}|{r['project']}|{r['judge']}" for r in records
        }
        decisions = {k: v for k, v in old.get("decisions", {}).items() if k in valid_keys}
        state = {
            "records": records,
            "decisions": decisions,
            "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "filename": filename,
        }
        save_state(state)
        return state


def update_decisions(patch: dict) -> dict:
    with _lock:
        state = load_state()
        valid_keys = {
            f"{r['contestant']}|{r['project']}|{r['judge']}" for r in state["records"]
        }
        for key, value in patch.items():
            if key not in valid_keys:
                continue
            mode = (value or {}).get("mode", "calibrated")
            if mode not in ("raw", "calibrated"):
                mode = "calibrated"
            state["decisions"][key] = {
                "mode": mode,
                "reason": str((value or {}).get("reason", "") or ""),
            }
        save_state(state)
        return state


def bulk_set_mode(mode: str) -> dict:
    with _lock:
        state = load_state()
        for r in state["records"]:
            key = f"{r['contestant']}|{r['project']}|{r['judge']}"
            cur = state["decisions"].get(key, {})
            state["decisions"][key] = {"mode": mode, "reason": cur.get("reason", "")}
        save_state(state)
        return state


def clear() -> None:
    with _lock:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
