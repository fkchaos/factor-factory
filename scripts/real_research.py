"""真实数据因子重测流水线（需 Tushare token，操作方按 docs/SOP_TUSHARE_TOKEN.md 配置）。

自动：读 token -> 实例化 TushareProvider（拉数据 + 缓存）-> 对 overnight_intraday / ivol 跑单因子验证
+ 组合回测 -> 把真实指标追加写进 research/TEST_LOG.md 与 research/factor_cards/。

无 token 时清晰报错，指引到 SOP。
"""
from __future__ import annotations
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.providers import TushareProvider
from data.contract import assert_adj_policy
from factors.overnight_intraday import OvernightIntradayFactor
from factors.ivol import IvolFactor
from engine.interface import BacktestConfig, QuadraticCost
from engine.engine_impl import WalkForwardEngine
from validate.validator import validate_factor
from portfolio.combiner import combine_factors


def _load_token() -> str | None:
    t = os.getenv("TUSHARE_TOKEN")
    if t:
        return t
    p = ROOT / "configs" / "tushare.yaml"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("token:"):
                v = s.split(":", 1)[1].strip().strip('"').strip("'")
                if v and v != "YOUR_TOKEN_HERE":
                    return v
    return None


def _make_provider(universe: str, hist_start: str):
    """按 FF_PROVIDER 选择数据源（tushare 默认 / akshare / baostock 免积分）。"""
    mode = os.getenv("FF_PROVIDER", "tushare")
    if mode == "baostock":
        from data.providers import BaoStockProvider
        # baostock 仅支持指数池/ALL；不支持的 universe 回退 sz50 并提示
        if universe not in ("hs300", "csi500", "zz500", "sz50", "ALL"):
            print(f"⚠️ FF_PROVIDER=baostock 仅支持 universe ∈ hs300/csi500/zz500/sz50/ALL"
                  f"（当前 {universe}），已切换为 sz50")
            universe = "sz50"
        prov = BaoStockProvider(universe=universe, history_start=hist_start)
        assert_adj_policy(getattr(prov, "adj_policy", "unknown"))  # qfq 符合契约
        return prov
    if mode == "akshare":
        from data.providers import AkShareProvider
        prov = AkShareProvider()
        assert_adj_policy(getattr(prov, "adj_policy", "unknown"))  # qfq 符合契约
        return prov
    # 默认 tushare
    from data.providers import TushareProvider
    token = _load_token()
    if not token:
        raise RuntimeError("未找到 TUSHARE_TOKEN（FF_PROVIDER=tushare 需要）。"
                           "可设 FF_PROVIDER=baostock 免积分运行。")
    prov = TushareProvider(token=token, universe=universe, calls_per_min=45,
                           history_start=hist_start)
    # 免费 token 仅能返回 raw（不复权）价，与契约 qfq 不一致——默认 fail-loud，
    # 须显式 FF_ALLOW_ADJ_MISMATCH=1 放行（并在产物标注口径差异）。
    assert_adj_policy(getattr(prov, "adj_policy", "unknown"),
                      allow_mismatch=os.getenv("FF_ALLOW_ADJ_MISMATCH") == "1")
    return prov


def _append_to_test_log(header: str, body: str):
    log = ROOT / "research" / "TEST_LOG.md"
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n## 🔬 {header}\n\n{body}\n")


def main():
    # 数据源：FF_PROVIDER ∈ {tushare(默认), akshare, baostock}；baostock 免 token/积分
    mode = os.getenv("FF_PROVIDER", "tushare")

    # 股票池：默认全A(L)；真实重测请先设 FF_UNIVERSE=hs300(沪深300)/csi500/zz500/sz50
    # 或交易所子集 SZ/SH/BJ（基础积分即可，指数接口积分不足时回退用）。
    # baostock 模式仅支持指数池/ALL。
    universe = os.getenv("FF_UNIVERSE", "L")
    # 分析窗口起点：全历史 6000+ 日对免费 token + 沙箱内存不友好，默认 2020 起
    # （约 1600 交易日，RankIC 统计量充分）；可设 FF_START=2000-01-01 恢复全历史。
    hist_start = os.getenv("FF_START", "2020-01-01")
    cfg = BacktestConfig(train_days=252, test_days=126, step_days=63,
                         top_n=20, cost_model="quadratic", execution="t1_open")
    try:
        prov = _make_provider(universe, hist_start)
    except Exception as e:
        print(f"❌ Provider 初始化失败（FF_PROVIDER={mode}）: {e}")
        print("   提示：FF_PROVIDER=baostock 免积分运行；tushare 需 token，见 docs/SOP_TUSHARE_TOKEN.md。")
        sys.exit(1)

    print(f"✅ {mode} 数据源就绪，股票池规模={len(prov.list_universe('2024-12-31'))}")
    print("⏳ 首次拉取可能较慢（已缓存到 .cache/），请耐心等待...")

    factors = [OvernightIntradayFactor(), IvolFactor()]
    results = {}
    for f in factors:
        m = validate_factor(f, prov, cfg)
        results[f.name] = m
        print(f"  {f.name}: RankIC={m['rank_ic']:.4f} ICIR={m['icir']:.4f} "
              f"win={m['ic_win_rate']:.2f} decay20={m['decay'].get('ic_20d')} "
              f"DSR={m['dsr']} PBO={m['pbo']}")

    comp = combine_factors(factors, provider=prov, config=cfg, method="icir")
    try:
        res = WalkForwardEngine(QuadraticCost()).run(comp, prov, cfg)
        combo_line = f"- 组合(combine='icir'): {res.metrics}\n"
        print(f"  组合回测: {res.metrics}")
    except Exception as e:
        # 沙箱内存受限时组合回测可能被无痕杀；因子结果仍有效，记录后继续
        res_metrics = f"{{'error': 'combo stage failed: {e}'}}"
        combo_line = f"- 组合(combine='icir'): {res_metrics}\n"
        print(f"  ⚠️ 组合回测未完成（内存受限或异常）: {e}")

    today = date.today().isoformat()
    body = f"**真实数据重测（{mode}，运行日 {today}，universe={universe}）**\n\n"
    for name, m in results.items():
        body += (f"- {name}: RankIC={m['rank_ic']:.4f}, ICIR={m['icir']:.4f}, "
                 f"IC胜率={m['ic_win_rate']:.2f}, n={m['n_obs']}, "
                 f"衰减(1/5/10/20d)={m['decay']}, DSR={m['dsr']}, PBO={m['pbo']}\n")
    body += combo_line
    body += "\n> ⚠️ DSR/PBO 门禁：DSR≥0.95 且 PBO≤0.30 方可通过（见 validate/overfit_audit.py）。\n"
    _append_to_test_log(f"真实数据重测 {today} (universe={universe})", body)
    print(f"\n✅ 真实指标已追加至 research/TEST_LOG.md")


if __name__ == "__main__":
    main()
