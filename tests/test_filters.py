"""filters.py 单元测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from filters import IronFilter


def _make_row(code="000001", name="测试", close=10.0, amount=5e8,
              circ_mv=50e8, seal_time="093500", ban_count=1,
              turnover=5.0, open_count=0, pct_chg=10.0, industry="银行"):
    return {
        "code": code, "name": name, "close": close, "amount": amount,
        "circ_mv": circ_mv, "seal_time": seal_time, "first_seal_time": seal_time,
        "ban_count": ban_count, "turnover": turnover, "open_count": open_count,
        "pct_chg": pct_chg, "industry": industry,
    }


def _make_history(days=200, base_price=10.0, pct_mean=0.5, pct_std=3.0):
    """生成模拟K线数据"""
    dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days, 0, -1)]
    np.random.seed(42)
    pct_chgs = np.random.normal(pct_mean, pct_std, days)
    prices = [base_price]
    for p in pct_chgs[1:]:
        prices.append(prices[-1] * (1 + p / 100))
    return pd.DataFrame({
        "date": dates,
        "open": prices,
        "high": [p * 1.02 for p in prices],
        "low": [p * 0.98 for p in prices],
        "close": prices,
        "volume": [1e6] * days,
        "amount": [1e7] * days,
        "pct_chg": [0] + list(pct_chgs[1:]),
    })


class TestRule1:
    def test_normal_seal_time(self):
        """正常封板时间应通过"""
        iron = IronFilter("20260430", pd.DataFrame())
        row = _make_row(seal_time="093500")
        assert iron._rule1_limit_up(row) is True

    def test_late_seal_rejected(self):
        """14:50后封板应被拒绝"""
        iron = IronFilter("20260430", pd.DataFrame())
        row = _make_row(seal_time="145500")
        assert iron._rule1_limit_up(row) is False


class TestRule2:
    def test_price_ok(self):
        iron = IronFilter("20260430", pd.DataFrame())
        row = _make_row(close=15.0, amount=1e8)
        assert iron._rule2_liquidity(row) is True

    def test_price_too_high(self):
        """股价超标且市值超标应被拒绝"""
        iron = IronFilter("20260430", pd.DataFrame())
        row = _make_row(close=50.0, circ_mv=2000e8, amount=1e8)
        assert iron._rule2_liquidity(row) is False


class TestRule7:
    def test_fast_seal(self):
        """09:35封板应通过"""
        iron = IronFilter("20260430", pd.DataFrame())
        row = _make_row(seal_time="093500", open_count=0)
        assert iron._rule7_seal_quality(row) is True

    def test_late_seal(self):
        """11:00封板应被拒绝"""
        iron = IronFilter("20260430", pd.DataFrame())
        row = _make_row(seal_time="110000", open_count=0)
        assert iron._rule7_seal_quality(row) is False

    def test_too_many_opens(self):
        """炸板次数过多应被拒绝"""
        iron = IronFilter("20260430", pd.DataFrame())
        row = _make_row(seal_time="094000", open_count=5)
        assert iron._rule7_seal_quality(row) is False


class TestRule8:
    def test_st_rejected(self):
        """ST股应被拒绝"""
        iron = IronFilter("20260430", pd.DataFrame())
        row = _make_row(name="*ST测试")
        hist = _make_history()
        assert iron._rule8_risk_exclusion(hist, row) is False

    def test_normal_pass(self):
        """正常股票应通过"""
        iron = IronFilter("20260430", pd.DataFrame())
        row = _make_row(name="正常股票")
        hist = _make_history()
        assert iron._rule8_risk_exclusion(hist, row) is True
