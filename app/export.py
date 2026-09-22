"""导出带审计明细的 CSV（UTF-8 BOM，Excel 直接可读）。

明细粒度为「选手 × 项目 × 评委」每一行，同时冗余项目分、总评分、
反转标记与评委分布参数，并在末尾附名次反转、评委参数两张审计附页。
"""
from __future__ import annotations

import csv
import io
from typing import Tuple


def _f(x, nd: int = 4) -> str:
    if x is None:
        return ""
    return f"{round(float(x), nd):.{nd}f}"


_SCALE_LABEL = {"mad": "MAD", "stdev": "标准差(MAD=0退化)", "none": "无差异"}


def export_audit_csv(result: dict) -> Tuple[bytes, str]:
    buf = io.StringIO()
    writer = csv.writer(buf)

    project_lookup = {}
    for p, rows in result["project_rows"].items():
        for row in rows:
            project_lookup[(row["contestant"], p)] = row
    overall_lookup = {row["contestant"]: row for row in result["overall_rows"]}
    stats_lookup = {s["judge"]: s for s in result["judge_stats"]}

    project_rev_members = {
        (r["project"], c)
        for r in result["reversals"] if r["scope"] == "project"
        for c in (r["contestant_a"], r["contestant_b"])
    }
    overall_rev_members = {
        c
        for r in result["reversals"] if r["scope"] == "overall"
        for c in (r["contestant_a"], r["contestant_b"])
    }

    writer.writerow(
        [
            "选手", "项目", "评委", "原始分", "稳健Z分", "校准分",
            "生效分", "采用", "调整理由", "与原分差",
            "项目-原始均分", "项目-校准均分", "项目-生效均分",
            "项目-原名次", "项目-校准名次", "项目-生效名次", "项目内名次反转",
            "总评-原始总分", "总评-校准总分", "总评-生效总分",
            "总评-原名次", "总评-校准名次", "总评-生效名次", "总评名次反转",
            "评委中位数", "评委MAD", "评委尺度", "尺度来源",
        ]
    )

    project_order = {p: i for i, p in enumerate(result["projects"])}
    items = sorted(
        result["items"],
        key=lambda it: (project_order[it["project"]], it["contestant"], it["judge"]),
    )
    for it in items:
        prow = project_lookup.get((it["contestant"], it["project"]), {})
        orow = overall_lookup.get(it["contestant"], {})
        s = stats_lookup.get(it["judge"], {})

        writer.writerow(
            [
                it["contestant"], it["project"], it["judge"],
                _f(it["raw_score"]), _f(it["robust_z"]), _f(it["calibrated_score"]),
                _f(it["effective_score"]),
                "保留原分" if it["mode"] == "raw" else "采用校准分",
                it["reason"], _f(it["delta"]),
                _f(prow.get("raw_score")), _f(prow.get("calibrated_score")),
                _f(prow.get("effective_score")),
                prow.get("raw_rank", ""), prow.get("calibrated_rank", ""),
                prow.get("effective_rank", ""),
                "是" if (it["project"], it["contestant"]) in project_rev_members else "否",
                _f(orow.get("raw_total")), _f(orow.get("calibrated_total")),
                _f(orow.get("effective_total")),
                orow.get("raw_rank", ""), orow.get("calibrated_rank", ""),
                orow.get("effective_rank", ""),
                "是" if it["contestant"] in overall_rev_members else "否",
                _f(s.get("median")), _f(s.get("mad")),
                _f(s.get("scale")), _SCALE_LABEL.get(s.get("scale_used"), ""),
            ]
        )

    # 审计附页 1：名次反转明细
    writer.writerow([])
    writer.writerow(["===== 名次反转审计 ====="])
    writer.writerow(
        ["范围", "项目", "原分领先选手", "校准后领先选手", "原始分差", "校准分差"]
    )
    for r in result["reversals"]:
        writer.writerow(
            [
                "项目内" if r["scope"] == "project" else "总评",
                r["project"], r["raw_leader"], r["calibrated_leader"],
                _f(r["raw_gap"]), _f(r["calibrated_gap"]),
            ]
        )

    # 审计附页 2：评委分布参数
    writer.writerow([])
    writer.writerow(["===== 评委分布参数 ====="])
    writer.writerow(["评委", "打分数", "中位数", "MAD", "均值", "标准差", "使用尺度", "尺度来源"])
    for s in result["judge_stats"]:
        writer.writerow(
            [
                s["judge"], s["n"], _f(s["median"]), _f(s["mad"]),
                _f(s["mean"]), _f(s["std"]), _f(s["scale"]),
                _SCALE_LABEL[s["scale_used"]],
            ]
        )

    return "﻿".encode("utf-8") + buf.getvalue().encode("utf-8"), "audit_calibration.csv"
