"""FastAPI 入口：上传 / 裁决 / 实时结果 / 导出 / 样例 / 清空。"""
from __future__ import annotations

import os
from typing import Dict, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import storage
from .calibration import ValidationError, build_result, calibrate, parse_csv
from .export import export_audit_csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
SAMPLE_PATH = os.path.join(BASE_DIR, "sample_data.csv")

app = FastAPI(title="多评委评分校准", version="1.0.0")


def _current_result():
    state = storage.load_state()
    if not state["records"]:
        return None, state
    records, judge_stats = calibrate([dict(r) for r in state["records"]])
    return build_result(records, judge_stats, state.get("decisions", {})), state


class DecisionIn(BaseModel):
    mode: str = Field(pattern="^(raw|calibrated)$")
    reason: str = ""


class DecisionsIn(BaseModel):
    decisions: Dict[str, DecisionIn]


class BulkIn(BaseModel):
    mode: str = Field(pattern="^(raw|calibrated)$")


@app.get("/api/state")
def get_state():
    result, state = _current_result()
    return {
        "has_data": bool(state["records"]),
        "filename": state.get("filename"),
        "uploaded_at": state.get("uploaded_at"),
        "result": result,
    }


@app.post("/api/upload")
async def upload_csv(file: UploadFile = File(...)):
    content = await file.read()
    if not content.strip():
        raise HTTPException(status_code=400, detail="上传文件为空。")
    try:
        records = parse_csv(content)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    state = storage.replace_records(records, file.filename)
    recs, stats = calibrate([dict(r) for r in state["records"]])
    return {"ok": True, "result": build_result(recs, stats, state["decisions"])}


@app.put("/api/decisions")
def put_decisions(payload: DecisionsIn):
    patch = {k: v.model_dump() for k, v in payload.decisions.items()}
    state = storage.update_decisions(patch)
    recs, stats = calibrate([dict(r) for r in state["records"]])
    return {"ok": True, "result": build_result(recs, stats, state["decisions"])}


@app.put("/api/decisions/bulk")
def bulk_decisions(payload: BulkIn):
    state = storage.bulk_set_mode(payload.mode)
    recs, stats = calibrate([dict(r) for r in state["records"]])
    return {"ok": True, "result": build_result(recs, stats, state["decisions"])}


@app.get("/api/export")
def export_csv():
    result, _ = _current_result()
    if result is None:
        raise HTTPException(status_code=400, detail="暂无数据可导出，请先上传 CSV。")
    data, filename = export_audit_csv(result)
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/sample")
def download_sample():
    return FileResponse(
        SAMPLE_PATH,
        media_type="text/csv; charset=utf-8",
        filename="sample_scores.csv",
    )


@app.delete("/api/session")
def clear_session():
    storage.clear()
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()
