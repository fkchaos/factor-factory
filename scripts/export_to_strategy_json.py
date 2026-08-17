"""把 f-code / s-code 交付包聚合成策略组（a-share-quant-sim）阶段 0 输入 JSON。

背景：对方研发框架阶段 0 会把全部外部输入归一化为
`alpha-research/inputs/{stock_factors,timing_signals,risk_params}.json`
并标 `source=external`，阶段 1 按 §7.2 门槛验证。
本脚本直接产出该 schema，**预填阶段 0**，让他们阶段 1 直接吃，不需二次搬运。

对齐依据：docs/REQUIREMENTS_ALIGNMENT-2026-08-07.md v2 §3 / §5.1 / §5.2 / §6。

产出（默认写 deliverables/strategy_export/）：
  - stock_factors.json    ← deliverables/factors/*（f-code）
  - timing_signals.json   ← deliverables/signals/*（s-code）
  - risk_params.json      ← 占位说明（我们不出风控参数，边界声明）
  - README.md             ← 交付说明 + exec_lag 钢印 + 字段映射表

设计约束：
1. **幂等**：纯读交付包 + 覆盖写 JSON，重复跑结果一致，不碰 baostock、不重算。
2. **不发明数字**：所有指标必须能溯源到 metrics_*.json / state_performance.json /
   manifest.yaml / card.md；拿不到的字段写 "unknown" 并进 TODO 列表，绝不臆造。
3. **schema 洁癖**：对方 schema 字段放顶层；我们的增量（多池 IC 表、§7.2 判决徽章、
   DSR/PBO、exec_lag 钢印）统一收在 `_factory_extra` 下，避免污染他们的解析。

用法：
  python scripts/export_to_strategy_json.py
  python scripts/export_to_strategy_json.py --out ../a-share-quant-sim/alpha-research/inputs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FACTOR_ROOT = Path("deliverables/factors")
SIGNAL_ROOT = Path("deliverables/signals")
DEFAULT_OUT = Path("deliverables/strategy_export")

# 对方 §7.2 三类型验证门槛（verbatim，见对齐文档 §5.2）
GATE_STOCK = {"valid": ("|IC|>0.03", "|IR|>0.3"), "refuted": ("|IC|<0.01", "|IR|<0.1")}
GATE_TIMING = {"valid": "sharpe>1.5", "refuted": "sharpe<1.0"}

# 因子 category 映射（对方枚举：technical / fundamental / alternative）
FACTOR_CATEGORY = {
    "overnight_intraday": "technical",
    "ivol": "technical",
    "combo_equal_v1": "technical",
    "momentum_20": "technical",
    "reversal_5": "technical",
    "size_log_mcap": "fundamental",
}
# 信号 category 映射（对方枚举：regime / sentiment / trend / volatility）
SIGNAL_CATEGORY = {
    "breadth_regime": "regime",         # 参与度（涨跌家数占比）→ 市场状态
    "risk_appetite": "sentiment",       # 小盘−大盘收益价差 = 风险偏好，情绪类更贴切
    "volatility_regime": "volatility",  # 二阶矩（波动收缩 / 扩张）
}

EXEC_LAG_STAMP = (
    "exec_lag=1（T 日收盘后才算得出 T 日状态，最早 T+1 建仓）。"
    "⚠️ 禁止用同期收益 ret[T] 评估本信号，必须 state.shift(1)；"
    "同期口径对广度类信号近似同义反复，实测可把 Sharpe 从真值撑高一大截。"
)


# ---------------------------------------------------------------------------
# 解析工具（纯函数，可单测）
# ---------------------------------------------------------------------------

def parse_manifest(path: Path) -> dict:
    """极简 YAML 解析：交付包 manifest 只有一层 `key: value`，不引 pyyaml。"""
    out: dict[str, Any] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            out[k.strip()] = [x.strip() for x in inner.split(",")] if inner else []
        elif v in ("null", ""):
            out[k.strip()] = None
        elif v in ("true", "false"):
            out[k.strip()] = (v == "true")
        else:
            out[k.strip()] = v
    return out


def parse_card_field(card_text: str, label: str) -> Optional[str]:
    """从 card.md 抓 `- <label>：<value>` 形式的字段。"""
    m = re.search(rf"^-\s*{re.escape(label)}[:：]\s*(.+)$", card_text, re.M)
    return m.group(1).strip() if m else None


def infer_direction(card_text: str) -> str:
    """方向：card 的「类别 / 方向」行。正向 → positive，负向 → negative。"""
    raw = parse_card_field(card_text, "类别 / 方向") or ""
    if "负向" in raw:
        return "negative"
    if "正向" in raw:
        return "positive"
    return "unknown"


def gate_stock_verdict(ic: Optional[float], ir: Optional[float]) -> str:
    """按对方 §7.2 stock 门槛判决：valid / refuted / gray。"""
    if ic is None or ir is None:
        return "unknown"
    a_ic, a_ir = abs(ic), abs(ir)
    if a_ic > 0.03 and a_ir > 0.3:
        return "valid"
    if a_ic < 0.01 or a_ir < 0.1:
        return "refuted"
    return "gray"


def gate_timing_verdict(sharpe: Optional[float]) -> str:
    """按对方 §7.2 timing 门槛判决。"""
    if sharpe is None:
        return "unknown"
    if sharpe > 1.5:
        return "valid"
    if sharpe < 1.0:
        return "refuted"
    return "gray"


def pick_home_pool(pool_metrics: dict) -> Optional[str]:
    """主场池 = |ICIR| 最大的池（判决随池翻转，见对齐文档 §5.3）。"""
    best, best_v = None, None
    for pool, m in pool_metrics.items():
        icir = (m.get("ic") or {}).get("icir")
        if icir is None:
            continue
        v = abs(float(icir))
        if best_v is None or v > best_v:
            best, best_v = pool, v
    return best


# ---------------------------------------------------------------------------
# 因子（stock）导出
# ---------------------------------------------------------------------------

def build_stock_factor(pkg_dir: Path) -> Optional[dict]:
    manifest = parse_manifest(pkg_dir / "manifest.yaml")
    card_path = pkg_dir / "card.md"
    if not manifest or not card_path.exists():
        return None
    card = card_path.read_text(encoding="utf-8")

    pool_metrics: dict[str, dict] = {}
    for mf in sorted(pkg_dir.glob("metrics_*.json")):
        pool = mf.stem.replace("metrics_", "")
        try:
            pool_metrics[pool] = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue

    home = pick_home_pool(pool_metrics)
    home_m = pool_metrics.get(home, {}) if home else {}
    ic_mean = (home_m.get("ic") or {}).get("rank_ic")
    ir = (home_m.get("ic") or {}).get("icir")

    audit = {}
    ap = pkg_dir / "overfit_audit.json"
    if ap.exists():
        try:
            audit = json.loads(ap.read_text(encoding="utf-8"))
        except Exception:
            audit = {}

    fcode = manifest.get("fcode") or pkg_dir.name
    factor = manifest.get("factor") or fcode
    title = card.splitlines()[0].lstrip("# ").strip() if card else fcode
    logic_one = parse_card_field(card, "逻辑一句话") or factor

    # calc_logic：一句话 + 中性化/PIT/窗口/数据口径 + 复现命令，扩写成可执行说明
    calc_logic = (
        f"{logic_one} | 数据口径：provider={manifest.get('provider')}，"
        f"复权={manifest.get('adj_policy')}，窗口自 {manifest.get('window_start')} 起 | "
        f"中性化：{manifest.get('neutralization')}；PIT 认证：{manifest.get('pit_certified')} | "
        f"复现：{manifest.get('reproduce')}"
    )
    if manifest.get("components"):
        calc_logic += f" | 组合成分：{','.join(manifest['components'])}（等权 z-score）"

    per_pool = []
    for pool, m in sorted(pool_metrics.items()):
        icm = m.get("ic") or {}
        bt = (m.get("backtest") or {}).get("net") or {}
        per_pool.append({
            "pool": pool,
            "ic_mean": icm.get("rank_ic"),
            "ir": icm.get("icir"),
            "ic_win_rate": icm.get("ic_win_rate"),
            "n_days": icm.get("n_days"),
            "sharpe_net": bt.get("sharpe"),
            "max_dd_net": bt.get("max_dd"),
            "gate_7_2_verdict": gate_stock_verdict(icm.get("rank_ic"), icm.get("icir")),
        })

    todo = []
    if ic_mean is None:
        todo.append("ic_mean 缺失（该包无 metrics_*.json）")
    todo.append("regime_dependency 待 P0『分 regime IC』补丁量化")
    todo.append("decay_status 待 P0『IC 衰减/半衰期』补丁量化")

    return {
        # ---- 对方 schema 顶层字段 ----
        "name": fcode,
        "type": "stock",
        "category": FACTOR_CATEGORY.get(factor, "technical"),
        "direction": infer_direction(card),
        "data_source": f"{manifest.get('provider')}/{manifest.get('adj_policy')}",
        "calc_logic": calc_logic,
        "ic_mean": ic_mean,
        "ir": ir,
        "regime_dependency": "unknown",
        "decay_status": "unknown",
        "expiry_date": None,
        "source": "external",
        "description": f"{title}｜{logic_one}",
        # ---- 我方增量（不属于对方 schema，独立命名空间避免污染解析）----
        "_factory_extra": {
            "fcode": fcode,
            "factor_impl": factor,
            "display_name": title,
            "home_pool": home,
            "home_pool_rule": "|ICIR| 最大的池（判决随池翻转，见对齐文档 §5.3）",
            "metrics_by_pool": per_pool,
            "gate_7_2_at_home_pool": gate_stock_verdict(ic_mean, ir),
            "gate_7_2_rule": GATE_STOCK,
            "overfit_audit": audit,
            "neutralization": manifest.get("neutralization"),
            "pit_certified": manifest.get("pit_certified"),
            "window_start": manifest.get("window_start"),
            "contract_version": manifest.get("contract_version"),
            "package_path": str(pkg_dir).replace("\\", "/"),
            "reproduce": manifest.get("reproduce"),
            "todo": todo,
        },
    }


# ---------------------------------------------------------------------------
# 信号（timing）导出
# ---------------------------------------------------------------------------

def build_timing_signal(pkg_dir: Path) -> Optional[dict]:
    manifest = parse_manifest(pkg_dir / "manifest.yaml")
    perf_path = pkg_dir / "state_performance.json"
    if not manifest or not perf_path.exists():
        return None
    try:
        perf = json.loads(perf_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    card = (pkg_dir / "card.md").read_text(encoding="utf-8") if (pkg_dir / "card.md").exists() else ""
    scode = manifest.get("scode") or pkg_dir.name
    sig_name = manifest.get("signal") or scode
    title = card.splitlines()[0].lstrip("# ").strip() if card else scode

    ov = perf.get("overlay") or {}
    dh = perf.get("direction_hit") or {}
    exec_lag = perf.get("exec_lag", 1)

    # backtest_sharpe：只认 exec_lag 口径的 overlay Sharpe（fwd 口径），
    # 绝不用 *_contemp（同期含当日信息，不可交易）。
    backtest_sharpe = ov.get("overlay_sharpe")
    win_rate = dh.get("risk_on_fwd1_up_rate")

    window = manifest.get("state_window")
    thr = manifest.get("state_threshold")
    try:
        thr_f = float(thr)
    except (TypeError, ValueError):
        thr_f = None

    audit = {}
    ap = pkg_dir / "overfit_audit.json"
    if ap.exists():
        try:
            audit = json.loads(ap.read_text(encoding="utf-8"))
        except Exception:
            audit = {}

    # trigger_logic 通用化：优先抓 card.md 的「状态定义：」原文（每个信号自带，
    # 见 Signal.state_def），避免每加一个信号就要回来补一个 if 分支（s0003x 时改）。
    state_def = ""
    for line in card.splitlines():
        s = line.lstrip("- ").strip()
        if s.startswith("状态定义："):
            state_def = s[len("状态定义："):].strip()
            break
    if state_def:
        trigger_logic = f"{state_def}（池={manifest.get('universe')}，MA{window} > {thr} → state=1）"
    elif sig_name == "breadth_regime":
        trigger_logic = (f"raw = 每日(上涨家数-下跌家数)/总数（池={manifest.get('universe')}）；"
                         f"MA{window} > {thr} → risk_on(1)，否则 risk_off(0)")
    else:
        trigger_logic = f"见 {pkg_dir.name}/card.md 状态定义；MA{window} > {thr} → state=1"

    return {
        # ---- 对方 schema 顶层字段 ----
        "name": scode,
        "type": "timing",
        "category": SIGNAL_CATEGORY.get(sig_name, "regime"),
        "trigger_logic": trigger_logic,
        "position_logic": (
            f"state.shift({exec_lag}) 后叠加：risk_on 允许因子多头暴露/持仓，"
            f"risk_off 减仓或空仓。T 日信号最早 T+{exec_lag} 日建仓。"
        ),
        "thresholds": {"high": thr_f, "low": thr_f},
        "backtest_sharpe": backtest_sharpe,
        "win_rate": win_rate,
        "regime_dependency": "unknown",
        "decay_status": "unknown",
        "expiry_date": None,
        "source": "external",
        "description": f"{title}｜市场级状态判断（每天一个标量），不是选股因子，勿并入横截面组合。",
        # ---- 🔴 防前视钢印：顶层显式暴露，堵对方框架盲点（对齐文档 §5.4）----
        "exec_lag": exec_lag,
        "exec_lag_warning": EXEC_LAG_STAMP,
        # ---- 我方增量 ----
        "_factory_extra": {
            "scode": scode,
            "signal_impl": sig_name,
            "display_name": title,
            "universe": manifest.get("universe"),
            "window_start": manifest.get("window_start"),
            "state_window": window,
            "state_threshold": thr_f,
            "n_days": perf.get("n"),
            "switch_rate": perf.get("switch_rate"),
            "hit_spread": dh.get("hit_spread"),
            "state_fwd_corr": dh.get("state_fwd_corr"),
            "states": perf.get("states"),
            "transition": perf.get("transition"),
            "overlay": ov,
            "gate_7_2_verdict": gate_timing_verdict(backtest_sharpe),
            "gate_7_2_rule": GATE_TIMING,
            "overfit_audit": audit,
            "pit_certified": manifest.get("pit_certified"),
            "package_path": str(pkg_dir).replace("\\", "/"),
            "reproduce": manifest.get("reproduce"),
            "todo": [
                "regime_dependency 待量化（强/弱市依赖）",
                "decay_status 待 P0『信号半衰期』补丁量化",
                "category 枚举已覆盖 regime / sentiment / volatility；trend 类待新建信号",
            ],
        },
    }


# ---------------------------------------------------------------------------
# 编排
# ---------------------------------------------------------------------------

def collect_stock_factors() -> list[dict]:
    out = []
    if not FACTOR_ROOT.exists():
        return out
    for d in sorted(FACTOR_ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        rec = build_stock_factor(d)
        if rec:
            out.append(rec)
    return out


def collect_timing_signals() -> list[dict]:
    out = []
    if not SIGNAL_ROOT.exists():
        return out
    for d in sorted(SIGNAL_ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        rec = build_timing_signal(d)
        if rec:
            out.append(rec)
    return out


def render_readme(n_stock: int, n_timing: int, generated: str) -> str:
    return f"""# 策略组阶段 0 输入包（factor-factory → a-share-quant-sim）

> 生成时间：{generated}｜生成脚本：`scripts/export_to_strategy_json.py`（幂等，可反复重跑）
> 对齐依据：`docs/REQUIREMENTS_ALIGNMENT-2026-08-07.md` v2 §3 / §5.1 / §5.2 / §6

## 文件

| 文件 | 内容 | 条目数 |
|---|---|---|
| `stock_factors.json` | 横截面选股因子（f-code） | {n_stock} |
| `timing_signals.json` | 市场级择时信号（s-code） | {n_timing} |
| `risk_params.json` | **占位**：风控参数不在我们交付范围 | 0 |

直接放到你们 `alpha-research/inputs/` 下即可被阶段 0 消费，`source` 均已标 `external`。

## 🔴 择时信号必读：exec_lag 钢印

{EXEC_LAG_STAMP}

每条 timing 记录顶层都带 `exec_lag` 与 `exec_lag_warning` 两个字段。
`backtest_sharpe` 取的是 **已 shift(1) 的 overlay Sharpe**，不是同期口径。
包内 `card.md` 的 `*_contemp` 列仅供诊断（判断信号对当日信息的依赖度），**不可用于评估**。

## 字段说明

- 对方 schema 字段一律放**顶层**，可直接解析。
- 我方增量统一收在 `_factory_extra` 下（多池 IC 表、§7.2 判决徽章、DSR/PBO、
  中性化/PIT 状态、复现命令、TODO 清单），忽略它不影响你们的解析。
- `regime_dependency` / `decay_status` 目前一律 `"unknown"`——不是遗漏，是我们
  拒绝在没算出来之前填数字，对应补丁见各条目 `_factory_extra.todo`。

## 判决随池翻转（重要）

选股因子的 §7.2 判决**是池子的函数**：同一因子在 sz50 可能"证伪"、在 zz1000 却"有效"。
我们不做内部门槛筛选，把**多池原始 IC 表全给**（`_factory_extra.metrics_by_pool`，
每池附 `gate_7_2_verdict`），主场池选择权交给你们的域判断。
顶层 `ic_mean` / `ir` 取的是 `_factory_extra.home_pool`（|ICIR| 最大池）的值。

## 我们不交付什么

止损 / 止盈 / 持仓天数上限 / 最大仓位 / 最大持仓数 —— 属策略层集成，不在因子/信号工厂范围。
我们仅提供**因子层面风险属性**（最大回撤、成本敏感性、中性化状态），见 `_factory_extra`。
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="输出目录（默认 deliverables/strategy_export）")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    import pandas as pd
    generated = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")

    stocks = collect_stock_factors()
    timings = collect_timing_signals()

    (out_dir / "stock_factors.json").write_text(
        json.dumps({"generated": generated, "source": "external",
                    "producer": "factor-factory", "factors": stocks},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    (out_dir / "timing_signals.json").write_text(
        json.dumps({"generated": generated, "source": "external",
                    "producer": "factor-factory",
                    "exec_lag_notice": EXEC_LAG_STAMP,
                    "signals": timings},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    (out_dir / "risk_params.json").write_text(
        json.dumps({"generated": generated, "source": "external",
                    "producer": "factor-factory",
                    "note": ("风控参数（stop_loss / take_profit / hold_days_max / "
                             "max_position / max_holdings）不在因子-信号工厂交付范围，"
                             "属策略层集成职责。我们仅提供因子层面风险属性："
                             "最大回撤、成本敏感性、中性化状态，见 stock_factors.json "
                             "的 _factory_extra。"),
                    "params": []},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    (out_dir / "README.md").write_text(
        render_readme(len(stocks), len(timings), generated), encoding="utf-8")

    print(f"✅ 策略组输入包已生成：{out_dir}")
    print(f"  stock_factors : {len(stocks)} 条 -> " +
          ", ".join(f"{s['name']}(IC={s['ic_mean']:.4f}@{s['_factory_extra']['home_pool']},"
                    f"{s['_factory_extra']['gate_7_2_at_home_pool']})"
                    if s["ic_mean"] is not None else f"{s['name']}(IC=NA)"
                    for s in stocks))
    for t in timings:
        bs = t["backtest_sharpe"]
        print(f"  timing_signal : {t['name']} sharpe="
              f"{bs:.3f}" if bs is not None else f"  timing_signal : {t['name']} sharpe=NA")
        print(f"                  exec_lag={t['exec_lag']} "
              f"verdict={t['_factory_extra']['gate_7_2_verdict']}")
    if not timings:
        print("  timing_signal : 0 条（deliverables/signals/ 下无已出包）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
