"""
公共工具函数
"""
from datetime import datetime
from typing import Optional


def parse_time(t_str: str) -> Optional[datetime]:
    """解析时间字符串，支持 092500 / 09:25:00 / 09:25 三种格式"""
    t_str = str(t_str).strip()
    if not t_str or t_str == "nan":
        return None
    # 无冒号格式 092500
    if len(t_str) == 6 and t_str.isdigit():
        try:
            return datetime.strptime(t_str, "%H%M%S")
        except ValueError:
            pass
    # 有冒号格式
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(t_str, fmt)
        except ValueError:
            continue
    return None


def is_limit_up(pct_chg: float, threshold: float = 9.8) -> bool:
    """判断是否涨停（兼容 10% 和 20% 涨跌幅限制）"""
    return pct_chg >= threshold


def format_amount(amount: float) -> str:
    """格式化成交额（亿元）"""
    if amount >= 1e8:
        return f"{amount / 1e8:.1f}亿"
    elif amount >= 1e4:
        return f"{amount / 1e4:.0f}万"
    return f"{amount:.0f}"


def safe_float(val, default: float = 0.0) -> float:
    """安全转 float"""
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def safe_int(val, default: int = 0) -> int:
    """安全转 int"""
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default
