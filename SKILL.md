# 涨停板量化筛选系统 (get_hot)

基于徐翔交易哲学的 A 股涨停板量化筛选工具。八条铁律一票否决 + 五维共振加权评分，输出 Top N 推荐标的及买卖点位。

## 何时使用

- 用户问「今天涨停股有哪些值得关注」「帮我筛一下涨停板」「A股涨停复盘」
- 用户想对某段区间做涨停策略回测
- 用户想了解某只股票是否符合涨停打板条件

## 前置条件

```bash
# 在项目目录下安装依赖（仅首次）
cd /root/.openclaw/workspace/get_hot
pip install -r requirements.txt
```

依赖：akshare, pandas, numpy, tabulate, pytest

## 命令速查

```bash
# 1. 筛选当天涨停股（收盘后运行）
python3 main.py

# 2. 筛选指定日期
python3 main.py 20260430

# 3. 只输出 Top 5
python3 main.py --top 5

# 4. 详细日志模式
python3 main.py -v

# 5. 回测区间（默认持仓 3 天）
python3 main.py --backtest 20260101 20260430

# 6. 回测 + 自定义持仓天数
python3 main.py --backtest 20260101 20260430 --hold-days 5

# 7. 直接调用回测模块
python3 backtester.py 20260101 20260430 3
```

## 输出解读

### 筛选结果包含

| 字段 | 含义 |
|------|------|
| `total_score` | 五维综合评分（0-100），越高越优 |
| `d1_limit_premium` | 涨停板溢价：连板数 + 封板速度 |
| `d2_capital` | 主力资金共振：换手率 + 成交额 + 资金流 + 龙虎榜 + 北向 |
| `d3_news` | 全网消息催化：板块热度 + 龙虎榜解读 + 连板效应 |
| `d4_leader` | 龙头地位：连板高度 + 涨停基因密度 |
| `d5_vol_health` | 量价健康度：量比 + 相对位置 + 均线排列 |
| `buy_point` | 建议买入价位与时机 |
| `sell_point` | 建议卖出目标 + 止损位 |
| `timing` | 操作时间窗口 |

### 回测结果包含

- `win_rate`：胜率
- `avg_return`：平均收益率
- `max_win` / `max_loss`：最大盈亏
- `profit_loss_ratio`：盈亏比

## 参数调优

所有阈值集中在 `config.py` 的 dataclass 中，运行时可直接修改：

```python
# 放宽价格上限
CFG.iron.max_price = 30.0

# 调整五维权重（总和必须 = 1.0）
CFG.weights.capital_resonance = 0.30

# 增加输出数量
CFG.output_top_n = 5
```

## 八条铁律（一票否决）

| 铁律 | 规则 |
|------|------|
| R1 | 仅限当日涨停，排除 14:50 后尾盘偷袭 |
| R2 | 股价 ≤ 20 元 或 流通市值 ≤ 1000 亿 |
| R3 | 近 12 月自然涨停 ≥ 5 次（自适应 10%/20% 板） |
| R4 | 涨停日量能放大 ≥ 30% |
| R5 | 5 日线日均斜率 ≥ 1% 或 突破 120/250 日均线 |
| R6 | 上方套牢盘 ≤ 20% |
| R7 | 开盘 1 小时内封板，炸板 ≤ 2 次 |
| R8 | 排除 ST / 天地板 / 炸板 > 8% |

## 注意事项

- **运行时间**：需在收盘后运行（15:00+），盘中数据不完整
- **网络依赖**：数据源为新浪财经 + 东方财富，首次运行需联网拉取
- **缓存机制**：自动缓存到 `.cache/` 目录，12 小时过期
- **运行耗时**：首次运行约 1-2 分钟（4 线程并发拉取历史 K 线），缓存命中后 10-20 秒
- **风险提示**：量化信号仅供参考，不构成投资建议

## Agent 调用示例

```
用户: 帮我看看今天涨停板有什么好标的
→ cd /root/.openclaw/workspace/get_hot && python3 main.py

用户: 回测一下今年的胜率
→ cd /root/.openclaw/workspace/get_hot && python3 main.py --backtest 20260101 20260430

用户: 看看 2026-04-30 涨停 Top 10
→ cd /root/.openclaw/workspace/get_hot && python3 main.py 20260430 --top 10
```
