"""为已交付的因子/信号 card.md 幂等追加「聚合视图」节。

背景（2026-08-18 用户决策）：
  交付物只有两类——因子（f-code）/ 信号（s-code），均有编号。
  strategy_export（机器可读发货形态）与 universe_matrix（跨池检验记录）
  是主交付物的**附属视图**，不另立编号。本脚本把"本交付物在聚合视图
  中的位置"写回各 card.md，并从 card 内指向聚合目录。

用法：
  python scripts/backfill_card_aggregate_views.py [--dry-run]
幂等：已含「## 聚合视图」节的卡自动跳过，可反复跑。
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FACTORS = ROOT / "deliverables" / "factors"
SIGNALS = ROOT / "deliverables" / "signals"

FACTOR_SEC = """
## 聚合视图（本因子在聚合交付中的位置）
- 机器可读发货形态：`../strategy_export/stock_factors.json`（条目 name={fcode}，供策略组阶段 0 消费）
- 跨池检验记录：`../universe_matrix/ic_matrix_<最新日期>.csv` 及同批 icir / dsr 三表（本因子行以矩阵实际收录为准）
- 说明：上述为同一交付物的聚合 / 检验视图，由 `scripts/export_to_strategy_json.py` / `scripts/factor_universe_matrix.py` 生成，与本卡同源，不另立交付编号。
"""

SIGNAL_SEC = """
## 聚合视图（本信号在聚合交付中的位置）
- 机器可读发货形态：`../strategy_export/timing_signals.json`（条目 name={scode}，含 exec_lag 钢印，供策略组阶段 0 消费）
- 说明：聚合视图由 `scripts/export_to_strategy_json.py` 生成，与本卡同源，不另立交付编号。
"""


def backfill(directory: pathlib.Path, code_re: str, section_tpl: str, dry_run: bool) -> int:
    n = 0
    for p in sorted(directory.glob("*/card.md")):
        text = p.read_text(encoding="utf-8")
        if "## 聚合视图" in text:
            continue  # 幂等
        m = re.search(code_re, text.splitlines()[0])
        if not m:
            print(f"!! 无法提取编号，跳过: {p}（首行: {text.splitlines()[0]!r}）")
            continue
        code = m.group(1)
        sec = section_tpl.format(**{("fcode" if "fcode" in section_tpl else "scode"): code})
        if not dry_run:
            p.write_text(text.rstrip() + "\n" + sec, encoding="utf-8")
        print(f"{'[dry] ' if dry_run else '+     '}{p}  <- {code}")
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    nf = backfill(FACTORS, r"（(f\d{4}[a-z])）", FACTOR_SEC, args.dry_run)
    ns = backfill(SIGNALS, r"（(s\d{4}x)）", SIGNAL_SEC, args.dry_run)
    print(f"因子卡回填 {nf} 张，信号卡回填 {ns} 张")
    return 0


if __name__ == "__main__":
    sys.exit(main())
