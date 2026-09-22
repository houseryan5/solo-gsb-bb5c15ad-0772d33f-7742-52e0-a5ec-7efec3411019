"""稳健标准化与排名核心逻辑。

按评委做中位数 / MAD（median absolute deviation）标准化：

    robust_z = 0.6745 * (x - median) / MAD

当某评委打分方差为零（MAD = 0）时退化为：
  1) 若数据存在离群值（MAD=0 但普通标准差 > 0），用样本标准差代替；
  2) 完全无差异时该评委所有 z 记为 0。

校准分再映射回原始分量纲（全体打分的中位数、稳健尺度），便于与原分比较。
"""
from __future__ import annotations

import csv
import io
import math
from collections import OrderedDict
from typing import Dict, List, Tuple

REQUIRED_FIELDS = ("contestant", "judge", "project", "score")

# CSV 表头中英文别名
HEADER_ALIASES = {
    "选手": "contestant",
    "选手姓名": "contestant",
    "参赛者": "contestant",
    "contestant": "contestant",
    "contestant_name": "contestant",
    "name": "contestant",
    "评委": "judge",
    "评委姓名": "judge",
    "judge": "judge",
    "judge_name": "judge",
    "项目": "project",
    "项目名称": "project",
    "比赛项目": "project",
    "project": "project",
    "project_name": "project",
    "event": "project",
    "分数": "score",
    "得分": "score",
    "评分": "score",
    "score": "score",
    "points": "score",
}


class ValidationError(Exception):
    """CSV 数据校验失败。"""


def median(values: List[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def mad(values: List[float], med: float) -> float:
    return median([abs(v - med) for v in values])


def stdev(values: List[float], mean: float) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def _ordered_unique(items) -> List[str]:
    seen = OrderedDict()
    for it in items:
        if it not in seen:
            seen[it] = None
    return list(seen.keys())


def parse_csv(content: bytes) -> List[dict]:
    """解析上传的 CSV 字节，返回规范化记录列表。"""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("gb18030")  # 兼容 Excel 中文导出

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValidationError("CSV 为空或缺少表头行。")

    col_map: Dict[str, str] = {}
    for col in reader.fieldnames:
        norm = HEADER_ALIASES.get((col or "").strip().lower())
        if norm:
            col_map[norm] = col.strip()

    missing = [f for f in REQUIRED_FIELDS if f not in col_map]
    if missing:
        names = {"contestant": "选手", "judge": "评委", "project": "项目", "score": "分数"}
        raise ValidationError(
            "CSV 缺少必需列：" + "、".join(names[m] for m in missing)
            + f"。检测到的表头：{', '.join(reader.fieldnames)}"
        )

    records: List[dict] = []
    seen: set[Tuple[str, str, str]] = set()
    for lineno, row in enumerate(reader, start=2):
        values = [(col_map[f], (row.get(col_map[f]) or "").strip()) for f in REQUIRED_FIELDS]
        if not any(v for _, v in values):
            continue  # 跳过整行空白
        blanks = [label for label, v in values if not v]
        if blanks:
            raise ValidationError(f"第 {lineno} 行存在空值（{ '、'.join(blanks) }）。")

        contestant, judge, project, raw_score = (v for _, v in values)
        try:
            score = float(raw_score)
        except ValueError:
            raise ValidationError(f"第 {lineno} 行分数不是数字：{raw_score!r}")
        if not math.isfinite(score):
            raise ValidationError(f"第 {lineno} 行分数无效：{raw_score!r}")

        key = (contestant, judge, project)
        if key in seen:
            raise ValidationError(
                f"第 {lineno} 行重复：选手「{contestant}」/ 评委「{judge}」/ 项目「{project}」。"
            )
        seen.add(key)
        records.append(
            {"contestant": contestant, "judge": judge, "project": project, "raw_score": score}
        )

    if not records:
        raise ValidationError("CSV 中没有任何有效评分记录。")
    return records


def calibrate(records: List[dict]) -> Tuple[List[dict], dict]:
    """对记录列表追加按评委的稳健 z 分与映射回原量纲的校准分。

    返回 (records, judge_stats)，每条记录增加：
      robust_z, calibrated_score
    judge_stats[judge] 包含 median / mad / scale_used / n / mean / std。
    """
    by_judge: Dict[str, List[dict]] = {}
    for r in records:
        by_judge.setdefault(r["judge"], []).append(r)

    all_scores = [r["raw_score"] for r in records]
    global_med = median(all_scores)
    global_mad = mad(all_scores, global_med)
    global_scale = global_mad / 0.6745 if global_mad > 0 else (
        stdev(all_scores, sum(all_scores) / len(all_scores)) if len(all_scores) > 1 else 1.0
    )
    if global_scale <= 0:
        global_scale = 1.0

    judge_stats: Dict[str, dict] = {}
    for judge, rows in by_judge.items():
        vals = [r["raw_score"] for r in rows]
        med = median(vals)
        md = mad(vals, med)
        mean = sum(vals) / len(vals)
        sd = stdev(vals, mean)

        if md > 0:
            scale = md / 0.6745
            scale_used = "mad"
        elif sd > 0:
            scale = sd
            scale_used = "stdev"  # MAD 为 0（半数以上同分）时的退化策略
        else:
            scale = 0.0
            scale_used = "none"

        judge_stats[judge] = {
            "judge": judge,
            "n": len(vals),
            "median": med,
            "mad": md,
            "mean": mean,
            "std": sd,
            "scale": scale,
            "scale_used": scale_used,
        }
        for r in rows:
            z = (r["raw_score"] - med) / scale if scale > 0 else 0.0
            r["robust_z"] = z
            r["calibrated_score"] = global_med + global_scale * z

    return records, judge_stats


def competition_ranks(pairs: List[Tuple[str, float]], descending: bool = True) -> Dict[str, int]:
    """标准竞赛排名（1224）。pairs: [(key, score), ...]。"""
    ordered = sorted(pairs, key=lambda p: p[1], reverse=descending)
    ranks: Dict[str, int] = {}
    prev_score = None
    for idx, (key, score) in enumerate(ordered, start=1):
        if prev_score is not None and score == prev_score:
            ranks[key] = ranks[ordered[idx - 2][0]]
        else:
            ranks[key] = idx
        prev_score = score
    return ranks


def build_result(records: List[dict], judge_stats: dict, decisions: Dict[str, dict]) -> dict:
    """合成项目总分、计算三套排名（原分 / 校准 / 生效）与名次反转明细。

    decisions key 形如 "contestant|project|judge"，值 {"mode": "calibrated|raw", "reason": str}。
    """
    contestants = _ordered_unique(r["contestant"] for r in records)
    projects = _ordered_unique(r["project"] for r in records)
    judges = _ordered_unique(r["judge"] for r in records)

    rec_index: Dict[Tuple[str, str, str], dict] = {
        (r["contestant"], r["project"], r["judge"]): r for r in records
    }

    def decision_of(contestant, project, judge):
        d = decisions.get(f"{contestant}|{project}|{judge}")
        if d and d.get("mode") in ("raw", "calibrated"):
            return d["mode"], (d.get("reason") or "").strip()
        return "calibrated", ""

    # ---- 逐项（选手 × 项目 × 评委） ----
    items: List[dict] = []
    # 项目聚合：project -> contestant -> {"raw": [], "cal": [], "eff": []}
    agg: Dict[str, Dict[str, Dict[str, List[float]]]] = {
        p: {c: {"raw": [], "cal": [], "eff": []} for c in contestants} for p in projects
    }
    for r in records:
        c, p, j = r["contestant"], r["project"], r["judge"]
        mode, reason = decision_of(c, p, j)
        eff = r["raw_score"] if mode == "raw" else r["calibrated_score"]
        items.append(
            {
                "id": f"{c}|{p}|{j}",
                "contestant": c,
                "project": p,
                "judge": j,
                "raw_score": r["raw_score"],
                "robust_z": r["robust_z"],
                "calibrated_score": r["calibrated_score"],
                "effective_score": eff,
                "delta": eff - r["raw_score"],
                "mode": mode,
                "reason": reason,
            }
        )
        bucket = agg[p][c]
        bucket["raw"].append(r["raw_score"])
        bucket["cal"].append(r["calibrated_score"])
        bucket["eff"].append(eff)

    def avg(xs: List[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    # ---- 项目总分（各评委均值）+ 项目内排名 ----
    project_rows: Dict[str, List[dict]] = {}
    project_reversals: List[dict] = []
    for p in projects:
        rows = []
        for c in contestants:
            b = agg[p][c]
            if not b["raw"]:
                continue
            rows.append(
                {
                    "contestant": c,
                    "project": p,
                    "n_judges": len(b["raw"]),
                    "raw_score": avg(b["raw"]),
                    "calibrated_score": avg(b["cal"]),
                    "effective_score": avg(b["eff"]),
                }
            )
        raw_ranks = competition_ranks([(x["contestant"], x["raw_score"]) for x in rows])
        cal_ranks = competition_ranks([(x["contestant"], x["calibrated_score"]) for x in rows])
        eff_ranks = competition_ranks([(x["contestant"], x["effective_score"]) for x in rows])
        for x in rows:
            x["raw_rank"] = raw_ranks[x["contestant"]]
            x["calibrated_rank"] = cal_ranks[x["contestant"]]
            x["effective_rank"] = eff_ranks[x["contestant"]]
        project_rows[p] = rows

        # 校准前后名次反转：原分占优但校准后落后（或相反），且分数严格不等
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if a["raw_score"] == b["raw_score"] or a["calibrated_score"] == b["calibrated_score"]:
                    continue
                raw_lead = a["raw_score"] > b["raw_score"]
                cal_lead = a["calibrated_score"] > b["calibrated_score"]
                if raw_lead != cal_lead:
                    winner_raw, winner_cal = (a, b) if raw_lead else (b, a)
                    project_reversals.append(
                        {
                            "scope": "project",
                            "project": p,
                            "contestant_a": winner_raw["contestant"],
                            "contestant_b": winner_cal["contestant"],
                            "raw_leader": winner_raw["contestant"],
                            "calibrated_leader": winner_cal["contestant"],
                            "raw_gap": abs(a["raw_score"] - b["raw_score"]),
                            "calibrated_gap": abs(a["calibrated_score"] - b["calibrated_score"]),
                        }
                    )

    # ---- 总评：项目总分之和（不缺项选手），缺项仅按已有项目但标注 ----
    overall_rows = []
    for c in contestants:
        present = [p for p in projects if agg[p][c]["raw"]]
        raw_tot = sum(avg(agg[p][c]["raw"]) for p in present)
        cal_tot = sum(avg(agg[p][c]["cal"]) for p in present)
        eff_tot = sum(avg(agg[p][c]["eff"]) for p in present)
        overall_rows.append(
            {
                "contestant": c,
                "n_projects": len(present),
                "raw_total": raw_tot,
                "calibrated_total": cal_tot,
                "effective_total": eff_tot,
            }
        )
    raw_ranks = competition_ranks([(x["contestant"], x["raw_total"]) for x in overall_rows])
    cal_ranks = competition_ranks([(x["contestant"], x["calibrated_total"]) for x in overall_rows])
    eff_ranks = competition_ranks([(x["contestant"], x["effective_total"]) for x in overall_rows])
    for x in overall_rows:
        x["raw_rank"] = raw_ranks[x["contestant"]]
        x["calibrated_rank"] = cal_ranks[x["contestant"]]
        x["effective_rank"] = eff_ranks[x["contestant"]]

    overall_reversals = []
    for i, a in enumerate(overall_rows):
        for b in overall_rows[i + 1:]:
            if a["raw_total"] == b["raw_total"] or a["calibrated_total"] == b["calibrated_total"]:
                continue
            raw_lead = a["raw_total"] > b["raw_total"]
            cal_lead = a["calibrated_total"] > b["calibrated_total"]
            if raw_lead != cal_lead:
                winner_raw, winner_cal = (a, b) if raw_lead else (b, a)
                overall_reversals.append(
                    {
                        "scope": "overall",
                        "project": "",
                        "contestant_a": winner_raw["contestant"],
                        "contestant_b": winner_cal["contestant"],
                        "raw_leader": winner_raw["contestant"],
                        "calibrated_leader": winner_cal["contestant"],
                        "raw_gap": abs(a["raw_total"] - b["raw_total"]),
                        "calibrated_gap": abs(a["calibrated_total"] - b["calibrated_total"]),
                    }
                )

    return {
        "contestants": contestants,
        "judges": judges,
        "projects": projects,
        "judge_stats": [judge_stats[j] for j in judges],
        "items": items,
        "project_rows": project_rows,
        "overall_rows": overall_rows,
        "reversals": project_reversals + overall_reversals,
        "n_items": len(items),
        "n_decisions": sum(1 for it in items if it["mode"] == "raw"),
    }
