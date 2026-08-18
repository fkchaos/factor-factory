"""构建时序信号交付包（docs/PLAN_SIGNAL_LINE.md · Signal Division）。

产出：deliverables/signals/<s-code>/ 下
  - card.md              状态定义 + 各状态绩效 + 叠加改善 + 消费指引
  - state_sequence.csv   日期 / 原始值 / 离散状态
  - state_performance.json  各状态统计 + 叠加改善 + 转移矩阵
  - overfit_audit.json   DSR 信任证书（叠加策略）
  - manifest.yaml        元数据/溯源
并同步 signals/_REGISTRY.csv。

与 build_deliverable.py（因子线）平行：因子给每股打分(RankIC/分层回测)，
信号给市场判状态(状态命中率/叠加Sharpe-DD改善)。

用法：
  python scripts/build_signal_deliverable.py --signal breadth_regime --scode s0001x \
      --name "广度Regime" --pool hs800 --window-start 2015-01-01
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.providers import BaoStockProvider
from signals.interface import get_signal, slice_panel_to_date
from validate.signal_validator import state_performance

OUT_ROOT = Path("deliverables/signals")
REGISTRY_CSV = OUT_ROOT / "_REGISTRY.csv"
FIELDS = ["open", "high", "low", "close", "volume", "amount", "turnover", "market_cap"]
SIG_WINDOW = 20
SIG_THRESHOLD = 0.0

# 卡片「已知陷阱」兜底文案。信号可用类属性 `caveat` 覆盖为自己的失真场景。
# （2026-08-12 修：原来硬编码成广度信号那句，s0002x/s0003x 卡片都在印别人的陷阱——
#  对外交付里放错误的适用边界说明，比不写更糟。）
DEFAULT_CAVEAT = ("该信号未声明专属失真场景；市场级状态信号在极端流动性枯竭 / 涨跌停潮 / "
                  "长假前后交易日稀疏时普遍失真，建议与其他 regime 信号交叉验证。")

# 🔴 防前视钢印：对外交付时必须随包出现在 card.md 与 manifest.yaml。
# 背景：外部策略组研发框架全文零提及 exec_lag / shift / T+1，若用同期收益评估
# 广度类信号会复现我们已堵掉的 Sharpe 虚高。见 docs/PLAN_SIGNAL_LINE.md §4.1
# 与 docs/REQUIREMENTS_ALIGNMENT-2026-08-07.md §5.4。
EXEC_LAG_WARNING = (
    "禁止用同期收益 ret[T] 评估本信号，必须 state.shift(exec_lag) 后再对齐收益；"
    "同期口径对由当日行情统计构造的信号（广度/涨跌家数/当日收益差等）近似同义反复，会显著虚高 Sharpe。"
    "本包所有 fwd_* / overlay 指标均已按 exec_lag 滞后计算，可直接采信；"
    "card.md 中 *_contemp 列仅供诊断，不可用于评估或上线决策。"
)


# ---------------------------------------------------------------------------
# 纯函数（可独立单测，不依赖 baostock）
# ---------------------------------------------------------------------------

def allocate_scode(registry_csv: Path, name: str, stype: str,
                   components: Optional[list] = None) -> str:
    """集中分配下一个 s-code：最大 NNNN +1，字母从 a 起。"""
    next_n = 1
    if registry_csv.exists():
        with open(registry_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        nums = []
        for r in rows:
            code = r.get("scode", "")
            if code.startswith("s") and code[1:5].isdigit():
                nums.append(int(code[1:5]))
        if nums:
            next_n = max(nums) + 1
    scode = f"s{next_n:04d}a"
    row = {
        "scode": scode, "name": name, "type": stype,
        "components": ",".join(components) if components else "",
        "status": "current", "supersedes": "",
        "created": pd.Timestamp.now().strftime("%Y-%m-%d"), "note": "",
    }
    _upsert_registry(registry_csv, row)
    return scode


def _upsert_registry(registry_csv: Path, row: dict) -> None:
    cols = ["scode", "name", "type", "components", "status", "supersedes", "created", "note"]
    rows = []
    if registry_csv.exists():
        with open(registry_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    rows = [r for r in rows if r.get("scode") != row["scode"]]
    rows.append(row)
    registry_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(registry_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def render_manifest(**kw) -> str:
    lines = ["# 时序信号交付包元数据（溯源 / 复现 / 防火墙基准）"]
    for k, v in kw.items():
        if isinstance(v, (list, tuple)):
            v = "[" + ", ".join(str(x) for x in v) + "]" if v else "[]"
        elif v is None:
            v = "null"
        elif isinstance(v, bool):
            v = "true" if v else "false"
        lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 数据密集：逐日信号值 + 基准收益（需 baostock 缓存）
# ---------------------------------------------------------------------------

def build_signal_series(signal, provider, window_start) -> tuple[pd.Series, pd.Series]:
    """逐日 compute 信号原始值，并同步算等权市场基准**当日已实现收益**。

    返回 (raw_series: date->信号标量, bench_ret: date->当日已实现等权收益)。

    ⚠️ 约定（曾踩坑，勿改）：bench_ret[t] = mean(close_t / close_{t-1} - 1)，即
    **t 日当天已经发生的收益**，不是 t→t+1 的前向收益。滞后由验证器
    state_performance(exec_lag=1) 统一负责（T 日信号 → T+1 建仓）。
    若这里存前向收益、验证器再滞后一次 = 双重滞后，指标会被莫名压平。
    逐日 compute 已自带 slice_panel_to_date 防前视。
    """
    panel = provider.get_panel(FIELDS, None, None)
    dates = sorted(panel.index.get_level_values("date").unique())

    raw = {}
    bench = {}
    for idx, t in enumerate(dates):
        try:
            val = signal.compute(panel, t)
        except Exception:
            val = float("nan")
        raw[t] = val if np.isfinite(val) else float("nan")
        if idx > 0:
            close_prev = panel.xs(dates[idx - 1], level="date")["close"]
            close_t = panel.xs(t, level="date")["close"]
            aligned = close_prev.reindex(close_t.index)
            rets = (close_t / aligned - 1.0).dropna()
            bench[t] = float(rets.mean()) if len(rets) else float("nan")
    raw_s = pd.Series(raw).sort_index()
    bench_s = pd.Series(bench).sort_index()
    return raw_s, bench_s


# ---------------------------------------------------------------------------
# 编排
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--signal", required=True)
    ap.add_argument("--scode", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--pool", default="hs800")
    ap.add_argument("--window-start", default="2015-01-01")
    ap.add_argument("--state-window", type=int, default=SIG_WINDOW)
    ap.add_argument("--state-threshold", type=float, default=SIG_THRESHOLD)
    ap.add_argument("--exec-lag", type=int, default=1,
                    help="T日信号→T+lag日建仓。默认1，禁止设0（0=同期口径，隐性前视）")
    args = ap.parse_args()
    if args.exec_lag < 1:
        print("❌ --exec-lag 必须 ≥1：同期口径是隐性前视，不允许出包", flush=True)
        return 2

    signal = get_signal(args.signal)
    stype = "single"

    pkg_dir = OUT_ROOT / args.scode
    pkg_dir.mkdir(parents=True, exist_ok=True)

    provider = BaoStockProvider(universe=args.pool, history_start=args.window_start)
    raw_s, bench_s = build_signal_series(signal, provider, args.window_start)

    # 离散状态序列
    ma = raw_s.rolling(args.state_window,
                       min_periods=max(5, args.state_window // 2)).mean()
    state = (ma > args.state_threshold).astype(int)
    seq = pd.DataFrame({
        "date": raw_s.index,
        "raw_value": raw_s.values,
        "state": state.reindex(raw_s.index).fillna(0).astype(int).values,
    })

    # 验证指标
    perf = state_performance(raw_s, bench_s, window=args.state_window,
                             threshold=args.state_threshold, exec_lag=args.exec_lag)
    if "error" in perf:
        print(f"⚠️ 信号验证失败: {perf['error']}", flush=True)
        return 1

    # 叠加策略收益（仅 risk_on 持多，risk_off 空仓）
    # ⚠️ 必须用 shift(exec_lag)：T 日信号最早 T+1 才能建仓，同期口径是隐性前视
    state_exec = state.shift(args.exec_lag).reindex(bench_s.index)
    overlay_ret = bench_s.where(state_exec.fillna(0).astype(bool), 0.0)
    from validate.overfit_audit import audit as _audit
    audit_res = _audit(overlay_ret.dropna().values, n_trials=4, n_splits=12)

    # 写文件
    seq.to_csv(pkg_dir / "state_sequence.csv", index=False)
    with open(pkg_dir / "state_performance.json", "w", encoding="utf-8") as f:
        json.dump(_jsonify(perf), f, ensure_ascii=False, indent=2)
    with open(pkg_dir / "overfit_audit.json", "w", encoding="utf-8") as f:
        json.dump({"dsr": audit_res.get("dsr"), "pbo": audit_res.get("pbo"),
                   "verdict": audit_res.get("verdict"),
                   "n_trials": 4, "n_splits": 12}, f, ensure_ascii=False, indent=2)

    # manifest
    manifest = render_manifest(
        scode=args.scode, signal=args.signal, version="1.0.0", doc_rev=1,
        status="current", generated=pd.Timestamp.now().strftime("%Y-%m-%d"),
        contract_version=1, provider="baostock", adj_policy="qfq",
        universe=args.pool, window_start=args.window_start,
        state_window=args.state_window, state_threshold=args.state_threshold,
        pit_certified=True,
        # 🔴 防前视钢印（对接外部策略组的红线，勿删）
        exec_lag=args.exec_lag,
        exec_lag_warning=EXEC_LAG_WARNING,
        reproduce=(f"FF_PROVIDER=baostock python scripts/build_signal_deliverable.py "
                   f"--signal {args.signal} --scode {args.scode} --pool {args.pool}"),
    )
    (pkg_dir / "manifest.yaml").write_text(manifest, encoding="utf-8")

    # card.md
    card = _render_card(args, signal, perf, audit_res, seq)
    (pkg_dir / "card.md").write_text(card, encoding="utf-8")

    # 同步 registry
    _upsert_registry(REGISTRY_CSV, {
        "scode": args.scode, "name": args.name or args.signal, "type": stype,
        "components": "", "status": "current", "supersedes": "",
        "created": pd.Timestamp.now().strftime("%Y-%m-%d"), "note": "",
    })
    print(f"✅ 信号交付包已生成：{pkg_dir}")
    ov = perf.get("overlay", {})
    print(f"  叠加 Sharpe 改善={ov.get('sharpe_improve'):+.3f}  "
          f"最大回撤改善={ov.get('dd_improve'):+.2%}  "
          f"long_days={ov.get('long_days_ratio'):.1%}")
    return 0


def _jsonify(obj):
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, pd.Series):
        return obj.to_dict()
    return obj


def _fmt(v, spec=".4f", dash="—"):
    try:
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return dash
        return format(float(v), spec)
    except Exception:
        return dash


def _render_card(args, signal, perf: dict, audit_res: dict, seq: pd.DataFrame) -> str:
    st = perf.get("states", {})
    ov = perf.get("overlay", {})
    dh = perf.get("direction_hit", {})
    s1 = st.get("state_1", {})
    s0 = st.get("state_0", {})

    return f"""# {args.name or args.signal}（{args.scode}）

- s-code：{args.scode}
- 逻辑一句话：{getattr(signal, '__doc__', None) or getattr(signal, 'name', args.signal)}
- 状态定义：{getattr(signal, 'state_def', '见 manifest')}
- 计算窗口/阈值：MA{args.state_window} > {args.state_threshold} → risk_on，否则 risk_off
- 执行滞后：exec_lag={perf.get('exec_lag', 1)}（T 日信号 → T+{perf.get('exec_lag', 1)} 日建仓，无前视）

> 🔴 **exec_lag={perf.get('exec_lag', 1)} 钢印（消费方必读）**
> {EXEC_LAG_WARNING}

## 各状态预测力（样本 {perf.get('n','—')} 日，市场基准=等权多头）
**看这张表请只看 fwd_* 列**——未来 N 日收益才是可交易的预测力。
| 状态 | 样本数 | 未来1日均值 | 未来1日胜率 | 未来5日均值 | 未来20日均值 |
|---|---|---|---|---|---|
| risk_on (1) | {s1.get('count','—')} | {_fmt(s1.get('fwd_ret_1d'),'.4f')} | {_fmt(s1.get('fwd_win_1d'),'.1%')} | {_fmt(s1.get('fwd_ret_5d'),'.4f')} | {_fmt(s1.get('fwd_ret_20d'),'.4f')} |
| risk_off (0) | {s0.get('count','—')} | {_fmt(s0.get('fwd_ret_1d'),'.4f')} | {_fmt(s0.get('fwd_win_1d'),'.1%')} | {_fmt(s0.get('fwd_ret_5d'),'.4f')} | {_fmt(s0.get('fwd_ret_20d'),'.4f')} |

<details><summary>同期口径（诊断用，含当日信息，不可交易）</summary>

| 状态 | 同期均值日收益 | 同期 Sharpe | 同期胜率 |
|---|---|---|---|
| risk_on (1) | {_fmt(s1.get('mean_ret_contemp'),'.4f')} | {_fmt(s1.get('sharpe_contemp'),'.2f')} | {_fmt(s1.get('win_rate_contemp'),'.1%')} |
| risk_off (0) | {_fmt(s0.get('mean_ret_contemp'),'.4f')} | {_fmt(s0.get('sharpe_contemp'),'.2f')} | {_fmt(s0.get('win_rate_contemp'),'.1%')} |

同期口径对"当日行情统计"型信号（广度 / 涨跌家数 / 当日收益差等）近似同义反复，只用于判断信号有多依赖当日信息：同期 Sharpe 越接近 fwd Sharpe，说明信号越不吃当日信息。
</details>

## 方向命中（T 日状态 → T+1 日收益）
- risk_on 后次日上涨率：{_fmt(dh.get('risk_on_fwd1_up_rate'),'.1%')}；risk_off 后次日：{_fmt(dh.get('risk_off_fwd1_up_rate'),'.1%')}
- 命中率价差（越大越有区分力）：{_fmt(dh.get('hit_spread'),'+.1%')}
- 状态值与未来1日收益相关：{_fmt(dh.get('state_fwd_corr'),'.3f')}
- 状态切换率：{_fmt(perf.get('switch_rate'),'.2%')}（过高=抖动，需降频）

## 叠加改善（baseline=全样本多头 vs overlay=仅 risk_on 持多，已滞后 {perf.get('exec_lag', 1)} 日）
| 指标 | baseline | overlay | 改善 |
|---|---|---|---|
| Sharpe | {_fmt(ov.get('baseline_sharpe'),'.2f')} | {_fmt(ov.get('overlay_sharpe'),'.2f')} | {_fmt(ov.get('sharpe_improve'),'+.3f')} |
| 最大回撤 | {_fmt(ov.get('baseline_max_dd'),'.2%')} | {_fmt(ov.get('overlay_max_dd'),'.2%')} | {_fmt(ov.get('dd_improve'),'+.2%')} |
| 年化收益 | {_fmt(ov.get('baseline_ann_ret'),'.2%')} | {_fmt(ov.get('overlay_ann_ret'),'.2%')} | — |
| 持仓日占比 | — | {_fmt(ov.get('long_days_ratio'),'.1%')} | — |

> 同期口径参照 Sharpe（不可交易）：{_fmt(ov.get('_contemp_sharpe_ref'),'.2f')}。
> 若它显著高于 overlay Sharpe {_fmt(ov.get('overlay_sharpe'),'.2f')}，说明信号高度依赖当日信息，
> 实盘可用性以 overlay 列为准。

## 过拟合审计（叠加策略）
- DSR：{_fmt(audit_res.get('dsr'),'.3f')}（阈值 ≥0.95）
- 结论：{audit_res.get('verdict')}

## 消费指引
- 本信号是**市场级状态判断**（每天一个值），不是选股因子，请勿并入横截面因子组合（贡献≡0）。
- 用法：risk_on 时允许因子多头暴露 / 加仓；risk_off 时减仓或空仓。
- **执行约定**：T 日收盘后才能算出 T 日状态，最早 T+{perf.get('exec_lag', 1)} 日建仓。
  本包所有 overlay 指标已按此滞后计算；若贵方按当日收盘价成交，需自行评估冲击成本。
- 状态序列见 state_sequence.csv；各状态绩效见 state_performance.json。
- 复现命令：FF_PROVIDER=baostock python scripts/build_signal_deliverable.py --signal {args.signal} --scode {args.scode} --pool {args.pool}
- 已知陷阱：{getattr(signal, 'caveat', None) or DEFAULT_CAVEAT}

## 聚合视图（本信号在聚合交付中的位置）
- 机器可读发货形态：`../strategy_export/timing_signals.json`（条目 name={args.scode}，含 exec_lag 钢印，供策略组阶段 0 消费）
- 说明：聚合视图由 `scripts/export_to_strategy_json.py` 生成，与本卡同源，不另立交付编号。
"""


if __name__ == "__main__":
    sys.exit(main())
