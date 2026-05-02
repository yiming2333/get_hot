"""
终端输出格式化 - 美观的表格展示
"""
from tabulate import tabulate
from datetime import datetime
from config import WEIGHTS


def print_banner():
    banner = """
╔══════════════════════════════════════════════════════════════════╗
║          徐翔五维共振 · 涨停板量化筛选系统 v1.0               ║
║          热点为王 | 趋势为魂 | 纪律为根 | 极致风控             ║
╚══════════════════════════════════════════════════════════════════╝
    """
    print(banner)


def print_stage(stage: str):
    print(f"\n{'='*60}")
    print(f"  ▶ {stage}")
    print(f"{'='*60}")


def print_filter_summary(total_input: int, total_passed: int, reasons: dict = None):
    print(f"\n📊 筛选结果: {total_input} 只涨停股 → {total_passed} 只通过全部铁律")
    if reasons:
        print("   淘汰原因分布:")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"     {reason}: {count}只")


def print_results(df):
    """打印最终推荐结果"""
    if df.empty:
        print("\n⚠️  当前市场无标的通过全部铁律筛选，宁可不做，不可做错。")
        return

    print(f"\n{'='*60}")
    print(f"  🏆 五维共振最终推荐（Top {len(df)}）")
    print(f"{'='*60}")

    for idx, row in df.iterrows():
        rank = idx + 1
        code = row.get("code", "")
        name = row.get("name", "")
        close = row.get("close", 0)
        total = row.get("total_score", 0)
        ban = row.get("ban_count", 1)
        seal = row.get("seal_time", row.get("first_seal_time", "—"))
        amount = float(row.get("amount", 0) or 0)

        print(f"""
┌──────────────────────────────────────────────────────────────┐
│  #{rank}  {code} {name}  │  评分: {total:.1f}/100  │  连板: {ban}板
├──────────────────────────────────────────────────────────────┤
│  收盘价: {float(close):.2f}元   封板时间: {seal}   成交额: {amount/1e8:.1f}亿
│
│  五维明细:
│    D1 涨停板溢价:   {row.get('d1_limit_premium', 0):.0f}/100  (权重{WEIGHTS['limit_up_premium']*100:.0f}%)
│    D2 主力资金共振: {row.get('d2_capital', 0):.0f}/100  (权重{WEIGHTS['capital_resonance']*100:.0f}%)
│    D3 全网消息催化: {row.get('d3_news', 0):.0f}/100  (权重{WEIGHTS['news_catalyst']*100:.0f}%)
│    D4 龙头地位确认: {row.get('d4_leader', 0):.0f}/100  (权重{WEIGHTS['leader_status']*100:.0f}%)
│    D5 量价健康度:   {row.get('d5_vol_health', 0):.0f}/100  (权重{WEIGHTS['vol_health']*100:.0f}%)
│
│  📈 买入: {row.get('buy_point', '—')}
│  📉 卖出: {row.get('sell_point', '—')}
│  ⏰ 时机: {row.get('timing', '—')}
└──────────────────────────────────────────────────────────────┘""")

    # 汇总表
    print(f"\n{'='*60}")
    print("  📋 汇总排行")
    print(f"{'='*60}")

    table_data = []
    for idx, row in df.iterrows():
        table_data.append([
            idx + 1,
            row.get("code", ""),
            row.get("name", ""),
            f"{float(row.get('close', 0)):.2f}",
            row.get("ban_count", 1),
            f"{row.get('total_score', 0):.1f}",
            row.get("timing", "—"),
        ])

    headers = ["#", "代码", "名称", "收盘价", "连板", "总分", "操作时机"]
    print(tabulate(table_data, headers=headers, tablefmt="simple"))

    print(f"\n⚠️  风险提示: 量化信号仅供参考，严格执行止损纪律，控制单票仓位≤20%")
    print(f"{'='*60}\n")
