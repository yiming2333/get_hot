"""
徐翔五维共振量化系统 - 配置文件
所有阈值集中管理，便于调优和回测
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List

# ============================================================
# 日志配置
# ============================================================
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


@dataclass
class IronRules:
    """八条铁律参数"""

    # 铁律1：尾盘偷袭排除时间
    late_seal_hour: int = 14
    late_seal_minute: int = 50

    # 铁律2：价格与流动性门槛
    max_price: float = 20.0           # 股价上限（元）
    max_circ_mv: float = 1000e8       # 流通市值上限（元）= 1000亿
    top_turnover_rank: int = 200      # 全市场成交额前N名

    # 铁律3：涨停基因
    gene_lookback_months: int = 12    # 回看月数
    gene_min_limit_ups: int = 5       # 最少自然涨停次数
    gene_pct_threshold: float = 9.5   # 涨停判定阈值（%），兼容不同涨跌幅限制

    # 铁律4：量能验证
    vol_lookback_days: int = 5        # 前N个交易日
    vol_min_amplify: float = 0.30     # 最低放大比例（30%）

    # 铁律5：趋势斜率
    ma_short: int = 5                 # 短期均线
    trend_slope_threshold: float = 1.0  # 日均斜率阈值（%），原45度角换算
    long_term_mas: List[int] = field(default_factory=lambda: [120, 250])

    # 铁律6：上方阻力
    max_chip_resistance: float = 0.20  # 上方套牢盘占比上限

    # 铁律7：封板质量
    seal_time_limit_min: int = 60     # 开盘后N分钟内封板
    seal_open_times_max: int = 2      # 最大开板次数

    # 铁律8：风险排除
    risk_lookback_days: int = 3       # 近N天检查天地板/炸板
    crash_threshold: float = -0.08    # 炸板回落幅度
    intraday_range_max: float = 0.18  # 日内振幅上限


@dataclass
class ScoringWeights:
    """五维权重（总和 = 1.0）"""
    limit_up_premium: float = 0.25    # 涨停板溢价
    capital_resonance: float = 0.25   # 主力资金共振
    news_catalyst: float = 0.15       # 全网消息催化
    leader_status: float = 0.20       # 龙头地位确认
    vol_health: float = 0.15          # 量价健康度

    def validate(self):
        total = (self.limit_up_premium + self.capital_resonance +
                 self.news_catalyst + self.leader_status + self.vol_health)
        assert abs(total - 1.0) < 0.01, f"权重总和应为1.0，当前={total:.3f}"


@dataclass
class SystemConfig:
    """系统总配置"""
    iron: IronRules = field(default_factory=IronRules)
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    output_top_n: int = 3             # 最终输出标的数量
    cache_dir: str = ".cache"
    request_delay: float = 0.6        # 请求间隔（秒）

    def validate(self):
        self.weights.validate()
        assert self.output_top_n > 0, "输出数量必须大于0"


# 全局默认配置实例
CFG = SystemConfig()
CFG.validate()

# ============================================================
# 向后兼容：旧代码引用的顶层常量
# ============================================================
MAX_PRICE = CFG.iron.max_price
MAX_CIRC_MV = CFG.iron.max_circ_mv
TOP_TURNOVER_RANK = CFG.iron.top_turnover_rank
GENE_LOOKBACK_MONTHS = CFG.iron.gene_lookback_months
GENE_MIN_LIMIT_UPS = CFG.iron.gene_min_limit_ups
VOL_LOOKBACK_DAYS = CFG.iron.vol_lookback_days
VOL_MIN_AMPLIFY = CFG.iron.vol_min_amplify
MA_SHORT = CFG.iron.ma_short
TREND_SLOPE_THRESHOLD = CFG.iron.trend_slope_threshold
LONG_TERM_MAS = CFG.iron.long_term_mas
MAX_CHIP_RESISTANCE = CFG.iron.max_chip_resistance
SEAL_TIME_LIMIT_MIN = CFG.iron.seal_time_limit_min
SEAL_OPEN_TIMES_MAX = CFG.iron.seal_open_times_max
RISK_LOOKBACK_DAYS = CFG.iron.risk_lookback_days
CRASH_THRESHOLD = CFG.iron.crash_threshold
PERF_DECLINE_THRESHOLD = -0.50
WEIGHTS = {
    "limit_up_premium": CFG.weights.limit_up_premium,
    "capital_resonance": CFG.weights.capital_resonance,
    "news_catalyst": CFG.weights.news_catalyst,
    "leader_status": CFG.weights.leader_status,
    "vol_health": CFG.weights.vol_health,
}
OUTPUT_TOP_N = CFG.output_top_n
