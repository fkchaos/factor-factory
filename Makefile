# ============================================================
# factor-factory · Makefile
# 常用研发任务封装。前置：pip install -e ".[dev,data-baostock]"
# ============================================================

PY := python
VENV ?= C:/Users/jiaby1/.workbuddy/binaries/python/envs/default/Scripts/python.exe
ROOT := $(CURDIR)

.PHONY: help install board factor signal test export sync data

help:
	@echo "factor-factory 常用任务"
	@echo "  make install   安装为可编辑包（含 dev + baostock 数据源）"
	@echo "  make board     刷新看板 docs/factor_board.html"
	@echo "  make factor     构建一个因子包（F=因子模块 FCODE=编号 NAME=名称 POOLS=池子）"
	@echo "  make signal     构建一个信号包（S=信号模块 SCODE=编号 NAME=名称）"
	@echo "  make test       跑全量 pytest"
	@echo "  make export     导出策略组 JSON 交付物"
	@echo "  make data       补齐 hs1800 全市场缓存"
	@echo "  make sync       推送当前状态到 GitHub 公开仓（交互会话用）"

install:
	$(PY) -m pip install -e ".[dev,data-baostock]"

board:
	$(PY) scripts/factor_board.py --out docs/factor_board.html

# 例：make factor F=overnight_intraday FCODE=f0001a NAME=隔夜-日内反转 POOLS=hs300,hs800
factor:
	$(PY) scripts/build_deliverable.py --factor $(F) --fcode $(FCODE) --name "$(NAME)" --pools $(POOLS) --window-start 2020-01-01

# 例：make signal S=breadth_regime SCODE=s0001x NAME=广度Regime
signal:
	$(PY) scripts/build_signal_deliverable.py --signal $(S) --scode $(SCODE) --name "$(NAME)" --pool hs800 --window-start 2015-01-01

test:
	$(PY) -m pytest

export:
	$(PY) scripts/export_to_strategy_json.py

data:
	$(PY) .cache/cache_universe.py hs1800

sync:
	$(PY) scripts/gh_sync.py
