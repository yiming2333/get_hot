"""config.py 单元测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from config import CFG, IronRules, ScoringWeights, SystemConfig


class TestIronRules:
    def test_defaults(self):
        rules = IronRules()
        assert rules.max_price == 20.0
        assert rules.gene_min_limit_ups == 5
        assert rules.vol_min_amplify == 0.30

    def test_custom(self):
        rules = IronRules(max_price=30.0, gene_min_limit_ups=3)
        assert rules.max_price == 30.0
        assert rules.gene_min_limit_ups == 3


class TestScoringWeights:
    def test_validation_pass(self):
        w = ScoringWeights()
        w.validate()  # 默认权重应通过

    def test_validation_fail(self):
        w = ScoringWeights(limit_up_premium=0.5)
        with pytest.raises(AssertionError):
            w.validate()


class TestSystemConfig:
    def test_default_config_valid(self):
        cfg = SystemConfig()
        cfg.validate()  # 默认配置应通过验证

    def test_global_config_valid(self):
        CFG.validate()  # 全局配置应通过验证
