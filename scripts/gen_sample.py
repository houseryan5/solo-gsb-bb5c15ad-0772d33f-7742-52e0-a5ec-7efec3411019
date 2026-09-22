"""生成示例 CSV：刻意设计评委宽严差异与偏好打分，使标准化前后出现明显名次反转。

用法：python scripts/gen_sample.py
"""
import csv  # noqa: F401
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.calibration import build_result, calibrate, parse_csv  # noqa: E402

CONTESTANTS = ["林一", "陈二", "周三", "吴四", "郑五"]
PROJECTS = ["命题展示", "即兴问答", "团队实操"]
# 每位评委的系统偏差与个人尺度：评委乙手松、评委丁手松但区分度低、评委丙偏严
JUDGE_BIAS = {"评委甲": (0.0, 1.0), "评委乙": (7.0, 1.6), "评委丙": (-2.5, 0.9), "评委丁": (4.5, 0.6)}
# 评委个人偏好（不公正成分）：评委乙偏爱郑五，评委丁偏爱吴四
JUDGE_FAVOR = {
    "评委乙": {"郑五": 4.5},
    "评委丁": {"吴四": 4.0, "周三": -2.0},
    "评委丙": {"林一": 2.0},
}
# 选手真实水平（每项目，校准后排名应接近它）
TRUE_SCORE = {
    "命题展示": {"林一": 88, "陈二": 83, "周三": 86, "吴四": 79, "郑五": 80},
    "即兴问答": {"林一": 85, "陈二": 91, "周三": 84, "吴四": 80, "郑五": 78},
    "团队实操": {"林一": 87, "陈二": 85, "周三": 90, "吴四": 82, "郑五": 83},
}


def gen(seed):
    rng = random.Random(seed)
    lines = []
    for project in PROJECTS:
        for c in CONTESTANTS:
            for judge, (bias, scale) in JUDGE_BIAS.items():
                favor = JUDGE_FAVOR.get(judge, {}).get(c, 0.0)
                noise = rng.gauss(0, 0.8)
                score = TRUE_SCORE[project][c] + bias + favor + scale * noise
                lines.append((c, judge, project, round(score, 1)))
    out = "\n".join(
        ["选手,评委,项目,分数"]
        + [f"{c},{j},{p},{s}" for c, j, p, s in lines]
    )
    return out


def main():
    chosen = None
    for seed in range(1, 3000):
        text = gen(seed)
        records = parse_csv(text.encode("utf-8"))
        records, stats = calibrate(records)
        result = build_result(records, stats, {})
        overall_rev = [r for r in result["reversals"] if r["scope"] == "overall"]
        proj_rev = [r for r in result["reversals"] if r["scope"] == "project"]
        # 要求总评发生反转，且至少两个项目内反转，分差有一定肉眼可见度
        if overall_rev and len(proj_rev) >= 2:
            chosen = (seed, text, result)
            break
    if not chosen:
        raise SystemExit("未找到含反转的种子")

    seed, text, result = chosen
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "sample_data.csv",
    )
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text + "\n")

    print(f"seed={seed} -> {path}")
    print("总评：原分排名 / 校准排名")
    for r in sorted(result["overall_rows"], key=lambda x: x["raw_rank"]):
        flag = " *反转*" if r["raw_rank"] != r["calibrated_rank"] else ""
        print(
            f"  {r['contestant']}: raw={r['raw_total']:.2f}(#{r['raw_rank']}) "
            f"cal={r['calibrated_total']:.2f}(#{r['calibrated_rank']}){flag}"
        )
    print(f"反转对数：{len(result['reversals'])}（总评 "
          f"{sum(1 for r in result['reversals'] if r['scope']=='overall')}，"
          f"项目内 {sum(1 for r in result['reversals'] if r['scope']=='project')}）")


if __name__ == "__main__":
    main()
