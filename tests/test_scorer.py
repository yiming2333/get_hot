"""scorer.py 单元测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scorer import FiveDimScorer


def _make_history(days=100, base_price=10.0):
    dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days, 0, -1)]
    np.random.seed(42)
    prices = [base_price * (1 + np.random.normal(0.3, 2) / 100) ** i for i in range(days)]
    return pd.DataFrame({
        "date": dates,
        "close": prices,
        "volume": [1e6 + np.random.randint(0, 5e5) for _ in range(days)],
        "amount": [1e7 + np.random.randint(0, 5e6) for _ in range(days)],
        "pct_chg": [0] + [np.random.normal(0.3, 2) for _ in range(days - 1)],
    })


class TestScorerInit:
    def test_empty_candidates(self):
        scorer = FiveDimScorer(pd.DataFrame(), "20260430")
        result = scorer.score_all()
        assert result.empty


class TestD1LimitPremium:
    def test_high_ban_count(self):
        scorer = FiveDimScorer(pd.DataFrame(), "20260430")
        row = {"ban_count": 3, "seal_time": "093100"}
        score = scorer._score_limit_premium(row, pd.DataFrame())
        assert score >= 75  # 连板+秒封

    def test_low_ban_late_seal(self):
        scorer = FiveDimScorer(pd.DataFrame(), "20260430")
        row = {"ban_count": 1, "seal_time": "102000"}
        score = scorer._score_limit_premium(row, pd.DataFrame())
        assert score <= 65  # 首板+晚封


class TestD5VolHealth:
    def test_healthy_volume(self):
        scorer = FiveDimScorer(pd.DataFrame(), "20260430")
        hist = _make_history(60)
        row = {"close": 10.0}
        score = scorer._score_vol_health(row, hist)
        assert 40 <= score <= 100

    def test_empty_history(self):
        scorer = FiveDimScorer(pd.DataFrame(), "20260430")
        score = scorer._score_vol_health({}, pd.DataFrame())
        assert score == 40  # 基础分
