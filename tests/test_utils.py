"""utils.py 单元测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import datetime
from utils import parse_time, is_limit_up, format_amount, safe_float, safe_int


class TestParseTime:
    def test_hhmmss_no_colon(self):
        t = parse_time("092500")
        assert t is not None
        assert t.hour == 9 and t.minute == 25 and t.second == 0

    def test_hhmmss_colon(self):
        t = parse_time("09:25:00")
        assert t is not None
        assert t.hour == 9 and t.minute == 25

    def test_hhmm_colon(self):
        t = parse_time("10:30")
        assert t is not None
        assert t.hour == 10 and t.minute == 30

    def test_empty(self):
        assert parse_time("") is None
        assert parse_time("nan") is None

    def test_invalid(self):
        assert parse_time("abc") is None
        assert parse_time("25:00:00") is None


class TestIsLimitUp:
    def test_10pct_board(self):
        assert is_limit_up(9.9) is True
        assert is_limit_up(10.0) is True

    def test_below_limit(self):
        assert is_limit_up(9.0) is False
        assert is_limit_up(5.0) is False

    def test_20pct_board(self):
        assert is_limit_up(19.8, threshold=19.5) is True
        assert is_limit_up(20.0, threshold=19.5) is True

    def test_custom_threshold(self):
        assert is_limit_up(9.5, threshold=9.5) is True
        assert is_limit_up(9.4, threshold=9.5) is False


class TestFormatAmount:
    def test_yi(self):
        assert "亿" in format_amount(1.5e8)

    def test_wan(self):
        assert "万" in format_amount(5e5)

    def test_small(self):
        assert format_amount(1000) == "1000"


class TestSafeFloat:
    def test_normal(self):
        assert safe_float(3.14) == 3.14
        assert safe_float("2.5") == 2.5

    def test_none(self):
        assert safe_float(None) == 0.0
        assert safe_float(None, default=-1.0) == -1.0

    def test_invalid(self):
        assert safe_float("abc") == 0.0


class TestSafeInt:
    def test_normal(self):
        assert safe_int(5) == 5
        assert safe_int("10") == 10

    def test_none(self):
        assert safe_int(None) == 0

    def test_invalid(self):
        assert safe_int("abc") == 0
