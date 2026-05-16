#!/usr/bin/env python3
"""btc-backtest — Simple backtesting engine for BTC trading strategies.

Tests strategies against historical price data. No real money involved.
Strategies return signals, engine simulates trades, reports P&L.

Usage:
    python3 btc-backtest.py --days 90 --strategy sma_cross
    python3 btc-backtest.py --days 180 --strategy rsi_reversal
    python3 btc-backtest.py --days 365 --strategy composite
"""

import json
import math
import sys
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class OHLCV:
    timestamp: int  # unix ms
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Trade:
    entry_price: float
    exit_price: float
    entry_time: int
    exit_time: int
    side: str  # "long" or "short"
    size_btc: float
    pnl_usd: float
    pnl_pct: float
    fee_usd: float


@dataclass
class BacktestResult:
    strategy: str
    period_days: int
    initial_capital: float
    final_capital: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl_usd: float
    total_pnl_pct: float
    max_drawdown_pct: float
    sharpe_ratio: Optional[float]
    avg_trade_pnl_usd: float
    avg_holding_hours: float
    best_trade_pct: float
    worst_trade_pct: float
    trades: list = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"=== Backtest: {self.strategy} ({self.period_days} days) ===",
            f"Capital:     ${self.initial_capital:,.0f} → ${self.final_capital:,.0f}",
            f"P&L:         ${self.total_pnl_usd:+,.0f} ({self.total_pnl_pct:+.1f}%)",
            f"Trades:      {self.total_trades} ({self.winning_trades}W / {self.losing_trades}L)",
            f"Win rate:    {self.win_rate:.1%}",
            f"Avg trade:   ${self.avg_trade_pnl_usd:+,.0f}",
            f"Max DD:      {self.max_drawdown_pct:.1f}%",
            f"Sharpe:      {self.sharpe_ratio:.2f}" if self.sharpe_ratio else "Sharpe:      N/A",
            f"Best trade:  {self.best_trade_pct:+.1f}%",
            f"Worst trade: {self.worst_trade_pct:+.1f}%",
            f"Avg hold:    {self.avg_holding_hours:.1f}h",
        ]
        return "\n".join(lines)


# ── Price data ────────────────────────────────────────────────────────────────

def fetch_ohlcv(days: int = 90) -> list[OHLCV]:
    """Fetch daily OHLCV from CoinGecko."""
    url = f"https://api.coingecko.com/api/v3/coins/bitcoin/ohlc?vs_currency=usd&days={days}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ManifoldBTC/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            candles = []
            for ts, o, h, l, c in data:
                candles.append(OHLCV(timestamp=ts, open=o, high=h, low=l, close=c, volume=0))
            return candles
    except Exception as e:
        print(f"Error fetching OHLCV: {e}")
        return []


# ── Indicators ────────────────────────────────────────────────────────────────

def sma(values: list[float], period: int) -> list[Optional[float]]:
    result = [None] * (period - 1)
    for i in range(period - 1, len(values)):
        result.append(sum(values[i - period + 1:i + 1]) / period)
    return result


def ema(values: list[float], period: int) -> list[Optional[float]]:
    result = [None] * (period - 1)
    k = 2 / (period + 1)
    seed = sum(values[:period]) / period
    result.append(seed)
    for i in range(period, len(values)):
        result.append(values[i] * k + result[-1] * (1 - k))
    return result


def rsi_series(closes: list[float], period: int = 14) -> list[Optional[float]]:
    n = len(closes)
    if n < period + 1:
        return [None] * n

    result = [None] * (period + 1)  # first `period` deltas need warmup, plus index 0
    gains = []
    losses = []
    for i in range(1, n):
        d = closes[i] - closes[i - 1]
        gains.append(max(0, d))
        losses.append(max(0, -d))

    # First RSI value after warmup
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    if avg_l == 0:
        result.append(100.0)
    else:
        rs = avg_g / avg_l
        result.append(100 - 100 / (1 + rs))

    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        if avg_l == 0:
            result.append(100.0)
        else:
            rs = avg_g / avg_l
            result.append(100 - 100 / (1 + rs))

    # Pad or trim to match closes length
    while len(result) < n:
        result.append(None)
    return result[:n]


# ── Strategies ────────────────────────────────────────────────────────────────

def strategy_sma_cross(candles: list[OHLCV]) -> list[dict]:
    """SMA crossover: long when SMA20 crosses above SMA50, short when below."""
    closes = [c.close for c in candles]
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)

    signals = []
    for i in range(len(candles)):
        if sma20[i] is None or sma50[i] is None:
            signals.append({"signal": "hold", "strength": 0})
            continue

        prev_sma20 = sma20[i - 1] if i > 0 else None
        prev_sma50 = sma50[i - 1] if i > 0 else None

        # Cross up
        if prev_sma20 is not None and prev_sma50 is not None and prev_sma20 <= prev_sma50 and sma20[i] > sma50[i]:
            signals.append({"signal": "buy", "strength": 1})
        # Cross down
        elif prev_sma20 is not None and prev_sma50 is not None and prev_sma20 >= prev_sma50 and sma20[i] < sma50[i]:
            signals.append({"signal": "sell", "strength": 1})
        elif sma20[i] > sma50[i]:
            signals.append({"signal": "hold_long", "strength": 0.5})
        else:
            signals.append({"signal": "hold_short", "strength": 0.5})

    return signals


def strategy_rsi_reversal(candles: list[OHLCV]) -> list[dict]:
    """RSI reversal: buy when RSI crosses below 30 (oversold), sell above 70."""
    closes = [c.close for c in candles]
    rsi = rsi_series(closes)

    signals = []
    for i in range(len(candles)):
        if rsi[i] is None:
            signals.append({"signal": "hold", "strength": 0})
            continue

        prev_rsi = rsi[i - 1] if i > 0 and rsi[i - 1] is not None else 50

        if rsi[i] < 30 and prev_rsi >= 30:
            signals.append({"signal": "buy", "strength": min(1, (30 - rsi[i]) / 15)})
        elif rsi[i] > 70 and prev_rsi <= 70:
            signals.append({"signal": "sell", "strength": min(1, (rsi[i] - 70) / 15)})
        elif rsi[i] < 40:
            signals.append({"signal": "hold_long", "strength": 0.3})
        elif rsi[i] > 60:
            signals.append({"signal": "hold_short", "strength": 0.3})
        else:
            signals.append({"signal": "hold", "strength": 0})

    return signals


def strategy_composite(candles: list[OHLCV]) -> list[dict]:
    """Composite: weighted signal from SMA, RSI, and MACD."""
    closes = [c.close for c in candles]
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    rsi = rsi_series(closes)

    signals = []
    for i in range(len(candles)):
        score = 0
        weight = 0

        # SMA cross component (weight 0.3)
        if sma20[i] is not None and sma50[i] is not None:
            if sma20[i] > sma50[i]:
                score += 0.3
            else:
                score -= 0.3
            weight += 0.3

        # RSI component (weight 0.35)
        if rsi[i] is not None:
            if rsi[i] < 30:
                score += 0.35
            elif rsi[i] > 70:
                score -= 0.35
            elif rsi[i] < 45:
                score += 0.15
            elif rsi[i] > 55:
                score -= 0.15
            weight += 0.35

        # MACD component (weight 0.35)
        if ema12[i] is not None and ema26[i] is not None:
            macd = ema12[i] - ema26[i]
            if macd > 0:
                score += 0.35
            else:
                score -= 0.35
            weight += 0.35

        if weight == 0:
            signals.append({"signal": "hold", "strength": 0})
        elif score > 0.15:
            signals.append({"signal": "buy", "strength": min(1, score / weight)})
        elif score < -0.15:
            signals.append({"signal": "sell", "strength": min(1, -score / weight)})
        elif score > 0:
            signals.append({"signal": "hold_long", "strength": score / weight * 0.5})
        else:
            signals.append({"signal": "hold_short", "strength": -score / weight * 0.5})

    return signals


STRATEGIES = {
    "sma_cross": strategy_sma_cross,
    "rsi_reversal": strategy_rsi_reversal,
    "composite": strategy_composite,
}


# ── Engine ────────────────────────────────────────────────────────────────────

def backtest(
    candles: list[OHLCV],
    signals: list[dict],
    strategy_name: str,
    initial_capital: float = 10000,
    fee_rate: float = 0.001,  # 0.1% fee
    position_size_pct: float = 0.95,  # use 95% of capital
) -> BacktestResult:
    """Run backtest on candles with pre-computed signals."""

    capital = initial_capital
    position = None  # {"side", "entry_price", "entry_time", "size_btc"}
    trades = []
    peak_capital = capital
    max_dd = 0

    for i, candle in enumerate(candles):
        sig = signals[i]["signal"]

        # Close position on sell signal (if long) or buy signal (if short)
        if position:
            if (position["side"] == "long" and sig == "sell") or \
               (position["side"] == "short" and sig == "buy"):
                exit_price = candle.close
                entry_price = position["entry_price"]
                size_btc = position["size_btc"]

                if position["side"] == "long":
                    pnl = (exit_price - entry_price) * size_btc
                else:
                    pnl = (entry_price - exit_price) * size_btc

                fee = exit_price * size_btc * fee_rate
                pnl -= fee

                trade = Trade(
                    entry_price=entry_price,
                    exit_price=exit_price,
                    entry_time=position["entry_time"],
                    exit_time=candle.timestamp,
                    side=position["side"],
                    size_btc=size_btc,
                    pnl_usd=pnl,
                    pnl_pct=pnl / (entry_price * size_btc) * 100,
                    fee_usd=fee,
                )
                trades.append(trade)
                capital += pnl
                position = None

        # Open position
        if not position:
            if sig == "buy":
                size_usd = capital * position_size_pct
                fee = size_usd * fee_rate
                size_btc = (size_usd - fee) / candle.close
                position = {
                    "side": "long",
                    "entry_price": candle.close,
                    "entry_time": candle.timestamp,
                    "size_btc": size_btc,
                }
            elif sig == "sell":
                size_usd = capital * position_size_pct
                fee = size_usd * fee_rate
                size_btc = (size_usd - fee) / candle.close
                position = {
                    "side": "short",
                    "entry_price": candle.close,
                    "entry_time": candle.timestamp,
                    "size_btc": size_btc,
                }

        # Track drawdown
        if capital > peak_capital:
            peak_capital = capital
        dd = (peak_capital - capital) / peak_capital * 100 if peak_capital > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # Close any open position at last price
    if position and candles:
        last = candles[-1].close
        entry = position["entry_price"]
        size = position["size_btc"]
        pnl = (last - entry) * size if position["side"] == "long" else (entry - last) * size
        fee = last * size * fee_rate
        pnl -= fee
        capital += pnl
        trades.append(Trade(
            entry_price=entry, exit_price=last,
            entry_time=position["entry_time"], exit_time=candles[-1].timestamp,
            side=position["side"], size_btc=size,
            pnl_usd=pnl, pnl_pct=pnl / (entry * size) * 100 if entry * size > 0 else 0,
            fee_usd=fee,
        ))

    winning = [t for t in trades if t.pnl_usd > 0]
    losing = [t for t in trades if t.pnl_usd <= 0]

    # Sharpe (annualized, daily returns)
    daily_returns = []
    for j in range(1, len(candles)):
        daily_returns.append((candles[j].close - candles[j - 1].close) / candles[j - 1].close)

    sharpe = None
    if len(daily_returns) > 1:
        mean_r = sum(daily_returns) / len(daily_returns)
        var_r = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)
        std_r = math.sqrt(var_r) if var_r > 0 else 0.001
        sharpe = (mean_r / std_r) * math.sqrt(365)

    avg_holding = 0
    if trades:
        avg_holding = sum(t.exit_time - t.entry_time for t in trades) / len(trades) / 3600000

    return BacktestResult(
        strategy=strategy_name,
        period_days=len(candles),
        initial_capital=initial_capital,
        final_capital=capital,
        total_trades=len(trades),
        winning_trades=len(winning),
        losing_trades=len(losing),
        win_rate=len(winning) / len(trades) if trades else 0,
        total_pnl_usd=capital - initial_capital,
        total_pnl_pct=(capital - initial_capital) / initial_capital * 100,
        max_drawdown_pct=max_dd,
        sharpe_ratio=sharpe,
        avg_trade_pnl_usd=sum(t.pnl_usd for t in trades) / len(trades) if trades else 0,
        avg_holding_hours=avg_holding,
        best_trade_pct=max((t.pnl_pct for t in trades), default=0),
        worst_trade_pct=min((t.pnl_pct for t in trades), default=0),
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="BTC Strategy Backtester")
    parser.add_argument("--days", type=int, default=90, help="Days of history")
    parser.add_argument("--strategy", default="composite", choices=list(STRATEGIES.keys()))
    parser.add_argument("--capital", type=float, default=10000, help="Starting capital")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    print(f"Fetching {args.days} days of BTC OHLCV...")
    candles = fetch_ohlcv(args.days)
    if not candles:
        print("Failed to fetch data")
        sys.exit(1)

    print(f"Got {len(candles)} candles: ${candles[0].close:,.0f} → ${candles[-1].close:,.0f}")

    strategy = STRATEGIES[args.strategy]
    signals = strategy(candles)

    result = backtest(candles, signals, args.strategy, args.capital)

    if args.json:
        out = {k: v for k, v in result.__dict__.items() if k != "trades"}
        out["trades_count"] = len(result.trades)
        print(json.dumps(out, indent=2))
    else:
        print()
        print(result.summary())
        print()
        print("Recent trades:")
        for t in result.trades[-5:]:
            ts_entry = datetime.fromtimestamp(t.entry_time / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            ts_exit = datetime.fromtimestamp(t.exit_time / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            print(f"  {ts_entry} → {ts_exit} | {t.side:5s} | {t.pnl_pct:+6.1f}% | ${t.pnl_usd:+,.0f}")


if __name__ == "__main__":
    main()
