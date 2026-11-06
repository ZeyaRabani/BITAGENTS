"""
Named trading strategy templates for Jupiter Trade Agent.

Users can say "use MACD" / "RSI mean reversion" / template id; the agent maps
onto a preset (params + entry/exit rules) then runs confirm → paper → live.
"""

from __future__ import annotations

from typing import Any, Optional


def _t(
    tid: str,
    name: str,
    family: str,
    summary: str,
    *,
    params: Optional[dict[str, Any]] = None,
    entry: str = "",
    exit_rule: str = "",
    default_tp: float = 12.0,
    default_sl: float = 6.0,
    aliases: Optional[list[str]] = None,
    timeframe: str = "1h",
) -> dict[str, Any]:
    return {
        "id": tid,
        "name": name,
        "family": family,
        "summary": summary,
        "params": params or {},
        "entry": entry,
        "exit": exit_rule,
        "default_tp_pct": default_tp,
        "default_sl_pct": default_sl,
        "aliases": aliases or [],
        "timeframe": timeframe,
        "venue": "jupiter_spot",
    }


# ─── Core families + popular named variants (~100) ────────────────────────────
STRATEGY_TEMPLATES: list[dict[str, Any]] = [
    # Trend / MA
    _t("ema_9_21_cross", "EMA 9/21 Cross", "trend", "Fast/slow EMA crossover",
       params={"fast": 9, "slow": 21}, entry="EMA9 crosses above EMA21", exit_rule="EMA9 crosses below EMA21",
       aliases=["ema cross", "9/21", "ema9 ema21"]),
    _t("ema_12_26_cross", "EMA 12/26 Cross", "trend", "MACD-style EMA lengths without histogram",
       params={"fast": 12, "slow": 26}, entry="EMA12 > EMA26 cross up", exit_rule="Cross down",
       aliases=["12/26 ema"]),
    _t("ema_20_50_cross", "EMA 20/50 Cross", "trend", "Swing trend following",
       params={"fast": 20, "slow": 50}, entry="EMA20 crosses above EMA50", exit_rule="Cross down",
       aliases=["20/50", "swing ema"]),
    _t("sma_50_200_golden", "SMA 50/200 Golden Cross", "trend", "Classic long-term trend",
       params={"fast": 50, "slow": 200}, entry="SMA50 crosses above SMA200", exit_rule="Death cross",
       default_tp=20, default_sl=10, aliases=["golden cross", "death cross", "50/200"]),
    _t("ema_ribbon", "EMA Ribbon", "trend", "Stack of EMAs aligned for trend",
       params={"lengths": [8, 13, 21, 34, 55]}, entry="Price above ribbon + ribbon fanning up",
       exit_rule="Price loses ribbon", aliases=["ribbon"]),
    _t("hma_trend", "Hull MA Trend", "trend", "Low-lag Hull moving average",
       params={"length": 55}, entry="Price closes above HMA + HMA rising", exit_rule="Close below HMA",
       aliases=["hull", "hma"]),
    _t("tema_trend", "TEMA Trend", "trend", "Triple EMA trend filter",
       params={"length": 30}, entry="Close above TEMA", exit_rule="Close below TEMA", aliases=["tema"]),
    _t("vwma_trend", "VWMA Trend", "trend", "Volume-weighted MA trend",
       params={"length": 20}, entry="Close crosses above VWMA", exit_rule="Cross below", aliases=["vwma"]),

    # MACD family
    _t("macd_classic", "MACD Classic Cross", "macd", "Standard MACD line/signal cross",
       params={"fast": 12, "slow": 26, "signal": 9}, entry="MACD crosses above signal",
       exit_rule="MACD crosses below signal", aliases=["macd", "macd cross"]),
    _t("macd_histogram", "MACD Histogram Flip", "macd", "Trade histogram zero-line / color flip",
       params={"fast": 12, "slow": 26, "signal": 9}, entry="Histogram turns positive",
       exit_rule="Histogram turns negative", aliases=["macd hist", "macd histogram"]),
    _t("macd_zero_cross", "MACD Zero-Line Cross", "macd", "MACD line crosses zero",
       params={"fast": 12, "slow": 26, "signal": 9}, entry="MACD crosses above 0",
       exit_rule="MACD crosses below 0", aliases=["macd zero"]),
    _t("macd_rsi_confirm", "MACD + RSI Confirm", "macd", "MACD cross only if RSI supports",
       params={"fast": 12, "slow": 26, "signal": 9, "rsi": 14, "rsi_min": 50},
       entry="MACD bullish cross and RSI>50", exit_rule="MACD bearish or RSI<45",
       aliases=["macd rsi"]),
    _t("macd_ema_filter", "MACD + EMA200 Filter", "macd", "Only long above EMA200",
       params={"fast": 12, "slow": 26, "signal": 9, "ema": 200},
       entry="MACD bullish + price > EMA200", exit_rule="MACD bearish or lose EMA200",
       aliases=["macd ema200"]),

    # RSI / oscillators
    _t("rsi_mean_reversion", "RSI Mean Reversion", "mean_reversion", "Buy oversold, sell overbought",
       params={"rsi": 14, "buy": 30, "sell": 70}, entry="RSI crosses up through 30",
       exit_rule="RSI crosses down through 70", aliases=["rsi", "rsi 30 70"]),
    _t("rsi_50_trend", "RSI 50 Trend", "trend", "RSI as trend filter",
       params={"rsi": 14, "level": 50}, entry="RSI crosses above 50", exit_rule="RSI crosses below 50",
       aliases=["rsi 50"]),
    _t("rsi_divergence", "RSI Divergence (flag)", "mean_reversion", "Flag bullish/bearish RSI divergence setups",
       params={"rsi": 14, "lookback": 30}, entry="Price LL + RSI HL (bullish div)",
       exit_rule="TP/SL or RSI extreme", default_tp=10, default_sl=5, aliases=["rsi div"]),
    _t("stoch_rsi", "Stochastic RSI", "mean_reversion", "StochRSI cross in extremes",
       params={"rsi": 14, "stoch": 14, "k": 3, "d": 3, "buy": 20, "sell": 80},
       entry="%K crosses above %D while <20", exit_rule="%K crosses below %D while >80",
       aliases=["stochrsi", "stoch rsi"]),
    _t("stochastic_classic", "Stochastic Classic", "mean_reversion", "Slow stochastic cross",
       params={"k": 14, "d": 3, "smooth": 3, "buy": 20, "sell": 80},
       entry="%K crosses %D in oversold", exit_rule="Cross in overbought", aliases=["stochastic"]),
    _t("cci_reversion", "CCI Reversion", "mean_reversion", "Commodity Channel Index extremes",
       params={"length": 20, "buy": -100, "sell": 100}, entry="CCI crosses up through -100",
       exit_rule="CCI crosses down through 100", aliases=["cci"]),
    _t("williams_r", "Williams %R", "mean_reversion", "Williams %R reclaim from oversold",
       params={"length": 14, "buy": -80, "sell": -20}, entry="%R crosses above -80",
       exit_rule="%R crosses below -20", aliases=["williams", "%r"]),
    _t("mfi_reversion", "MFI Mean Reversion", "mean_reversion", "Money Flow Index extremes",
       params={"length": 14, "buy": 20, "sell": 80}, entry="MFI crosses up 20", exit_rule="MFI crosses down 80",
       aliases=["mfi", "money flow"]),
    _t("roc_momentum", "ROC Momentum", "momentum", "Rate of change momentum",
       params={"length": 12, "threshold": 0}, entry="ROC crosses above 0", exit_rule="ROC crosses below 0",
       aliases=["roc"]),
    _t("momentum_10", "10-Period Momentum", "momentum", "Simple momentum sign flip",
       params={"length": 10}, entry="Momentum turns positive", exit_rule="Momentum turns negative",
       aliases=["momentum"]),

    # Bollinger / volatility
    _t("bollinger_mean_reversion", "Bollinger Mean Reversion", "mean_reversion", "Fade band touches",
       params={"length": 20, "std": 2}, entry="Close below lower band then reclaim",
       exit_rule="Touch upper band or mid-band", aliases=["bollinger", "bb", "bollinger bands"]),
    _t("bollinger_breakout", "Bollinger Breakout", "breakout", "Trade squeeze expansion",
       params={"length": 20, "std": 2}, entry="Close breaks above upper band after squeeze",
       exit_rule="Close back inside bands", default_tp=15, default_sl=7, aliases=["bb breakout", "squeeze breakout"]),
    _t("bollinger_squeeze", "Bollinger Squeeze", "breakout", "Keltner/BB squeeze proxy",
       params={"bb": 20, "kc": 20, "bb_std": 2, "kc_atr": 1.5}, entry="Squeeze release + direction candle",
       exit_rule="Opposite band or ATR stop", aliases=["ttm squeeze", "squeeze"]),
    _t("keltner_breakout", "Keltner Channel Breakout", "breakout", "ATR channel breakout",
       params={"length": 20, "atr_mult": 1.5}, entry="Close above upper Keltner",
       exit_rule="Close below mid/lower", aliases=["keltner"]),
    _t("atr_breakout", "ATR Channel Breakout", "breakout", "Price breaks ATR envelope",
       params={"atr": 14, "mult": 2}, entry="Close > SMA + 2*ATR", exit_rule="Close < SMA",
       aliases=["atr breakout"]),
    _t("atr_trail", "ATR Trailing Stop", "trend", "Chandelier-style trail",
       params={"atr": 22, "mult": 3}, entry="Trend direction + trail arm",
       exit_rule="Price hits ATR trail", default_tp=0, default_sl=0, aliases=["chandelier", "atr trail"]),
    _t("supertrend", "Supertrend", "trend", "ATR supertrend flips",
       params={"atr": 10, "mult": 3}, entry="Supertrend flips bullish", exit_rule="Flips bearish",
       aliases=["super trend", "st"]),
    _t("parabolic_sar", "Parabolic SAR", "trend", "SAR flip entries",
       params={"step": 0.02, "max": 0.2}, entry="SAR flips below price", exit_rule="SAR flips above",
       aliases=["sar", "psar"]),

    # Breakouts
    _t("donchian_20", "Donchian 20 Breakout", "breakout", "Turtle-style 20-bar breakout",
       params={"entry": 20, "exit": 10}, entry="Close > 20-bar high", exit_rule="Close < 10-bar low",
       default_tp=18, default_sl=8, aliases=["donchian", "turtle 20"]),
    _t("donchian_55", "Donchian 55 Breakout", "breakout", "Longer turtle breakout",
       params={"entry": 55, "exit": 20}, entry="Close > 55-bar high", exit_rule="Close < 20-bar low",
       default_tp=25, default_sl=10, aliases=["turtle 55", "donchian 55"]),
    _t("n_day_high", "N-Day High Breakout", "breakout", "Generic lookback high break",
       params={"n": 14}, entry="Break N-day high", exit_rule="Break N/2-day low or SL",
       aliases=["nday breakout", "lookback high"]),
    _t("volume_breakout", "Volume Breakout", "breakout", "Price break + volume spike",
       params={"vol_ma": 20, "vol_mult": 1.5, "range": 20},
       entry="New 20-high with volume > 1.5x avg", exit_rule="TP/SL",
       aliases=["vol breakout"]),
    _t("opening_range", "Opening Range Breakout", "breakout", "Break first-session range",
       params={"range_bars": 4}, entry="Break opening range high", exit_rule="Range mid or SL",
       timeframe="15m", aliases=["orb", "opening range"]),
    _t("inside_bar_break", "Inside Bar Breakout", "breakout", "Break mother-bar range",
       params={}, entry="Break inside-bar high", exit_rule="Break opposite or SL",
       aliases=["inside bar"]),
    _t("nr7_breakout", "NR7 Breakout", "breakout", "Narrowest range 7 breakout",
       params={"lookback": 7}, entry="Break NR7 bar high", exit_rule="SL below NR7 low",
       aliases=["nr7"]),

    # Ichimoku / complex trend
    _t("ichimoku_tk_cross", "Ichimoku TK Cross", "trend", "Tenkan/Kijun cross",
       params={"tenkan": 9, "kijun": 26, "senkou": 52}, entry="Tenkan crosses above Kijun",
       exit_rule="Tenkan crosses below Kijun", aliases=["ichimoku", "tk cross"]),
    _t("ichimoku_cloud_break", "Ichimoku Cloud Break", "trend", "Price breaks Kumo",
       params={"tenkan": 9, "kijun": 26, "senkou": 52}, entry="Close above cloud",
       exit_rule="Close back into/below cloud", aliases=["kumo break", "cloud break"]),
    _t("ichimoku_full", "Ichimoku Full Stack", "trend", "TK cross + above cloud + lagging span",
       params={"tenkan": 9, "kijun": 26, "senkou": 52},
       entry="Bullish TK + price/lagging above cloud", exit_rule="Any pillar fails",
       default_tp=15, default_sl=8, aliases=["ichimoku complete"]),

    # ADX / DMI
    _t("adx_trend", "ADX Trend Strength", "trend", "Trade only strong trends",
       params={"adx": 14, "min_adx": 25}, entry="ADX>25 and +DI>-DI", exit_rule="ADX fades or DI flip",
       aliases=["adx", "dmi"]),
    _t("adx_di_cross", "ADX DI Cross", "trend", "+DI/-DI crossover with ADX filter",
       params={"adx": 14, "min_adx": 20}, entry="+DI crosses above -DI and ADX rising",
       exit_rule="-DI crosses above +DI", aliases=["di cross"]),

    # VWAP / session
    _t("vwap_reversion", "VWAP Reversion", "mean_reversion", "Fade stretch from VWAP",
       params={"band_pct": 1.0}, entry="Price extended below VWAP then reclaim",
       exit_rule="Back to VWAP / upper band", timeframe="15m", aliases=["vwap"]),
    _t("vwap_breakout", "VWAP Breakout", "breakout", "Momentum away from VWAP",
       params={}, entry="Hold above VWAP + impulse", exit_rule="Lose VWAP",
       timeframe="15m", aliases=["vwap momentum"]),
    _t("anchored_vwap", "Anchored VWAP", "trend", "Hold/reject around anchored VWAP",
       params={"anchor": "swing_low"}, entry="Reclaim anchored VWAP", exit_rule="Lose AVWAP",
       aliases=["avwap"]),

    # Candlestick / price action (rule templates)
    _t("engulfing_trend", "Engulfing + Trend", "price_action", "Engulfing with EMA filter",
       params={"ema": 50}, entry="Bullish engulfing above EMA50", exit_rule="Bearish engulfing or SL",
       aliases=["engulfing"]),
    _t("pin_bar_reversal", "Pin Bar Reversal", "price_action", "Rejection wick at level",
       params={"wick_ratio": 2.0}, entry="Bullish pin at support/EMA", exit_rule="TP/SL",
       aliases=["pin bar", "hammer"]),
    _t("three_soldiers", "Three Soldiers / Crows", "price_action", "Continuation candle pattern",
       params={}, entry="Three white soldiers", exit_rule="Opposite pattern or SL",
       aliases=["three soldiers"]),

    # Dual / hybrid popular recipes
    _t("ema_rsi_pullback", "EMA Pullback + RSI", "trend", "Buy pullback to EMA in uptrend",
       params={"ema": 21, "rsi": 14, "rsi_max": 45}, entry="Uptrend + touch EMA21 + RSI reclaim",
       exit_rule="Lose EMA or TP/SL", aliases=["ema pullback"]),
    _t("macd_bb_combo", "MACD + Bollinger", "hybrid", "MACD cross near lower band",
       params={"macd": [12, 26, 9], "bb": [20, 2]}, entry="Near lower BB + MACD bullish",
       exit_rule="Upper BB or MACD flip", aliases=["macd bollinger"]),
    _t("rsi_bb_combo", "RSI + Bollinger", "mean_reversion", "Double oversold confirm",
       params={"rsi": 14, "bb": [20, 2], "buy": 30}, entry="Lower BB + RSI<30 reclaim",
       exit_rule="Mid/upper band", aliases=["rsi bb"]),
    _t("supertrend_rsi", "Supertrend + RSI", "trend", "Supertrend with RSI filter",
       params={"atr": 10, "mult": 3, "rsi": 14, "rsi_min": 50},
       entry="Supertrend long + RSI>50", exit_rule="Supertrend flip", aliases=["st rsi"]),
    _t("adx_ema_stack", "ADX + EMA Stack", "trend", "Strong trend + EMA alignment",
       params={"adx": 14, "emas": [8, 21, 55], "min_adx": 25},
       entry="EMA stack bullish + ADX>25", exit_rule="Stack breaks", aliases=["adx ema"]),

    # Crypto-popular named styles
    _t("buy_the_dip_5", "Buy the Dip 5%", "mean_reversion", "Add on 5% drawdown from local high",
       params={"dip_pct": 5, "lookback": 48}, entry="5% dip from recent high",
       exit_rule="Return to high or TP/SL", default_tp=8, default_sl=5, aliases=["buy the dip", "dip buy"]),
    _t("buy_the_dip_10", "Buy the Dip 10%", "mean_reversion", "Deeper dip entry",
       params={"dip_pct": 10, "lookback": 72}, entry="10% dip from recent high",
       exit_rule="Mean reclaim or TP/SL", default_tp=12, default_sl=7, aliases=["dip 10"]),
    _t("grid_like_levels", "Grid-like Level Scalps", "grid", "Buy/sell predefined % bands (spot)",
       params={"step_pct": 2, "levels": 5}, entry="Hit lower grid level", exit_rule="Hit upper grid level",
       default_tp=2, default_sl=4, aliases=["grid levels", "spot grid"]),
    _t("dca_signal_boost", "DCA on RSI Oversold", "dca", "Scheduled/add-on buys when RSI oversold",
       params={"rsi": 14, "buy": 35}, entry="RSI<35 add tranche", exit_rule="TP ladder",
       aliases=["dca rsi"]),
    _t("momentum_burst", "Momentum Burst", "momentum", "Short burst after range expansion",
       params={"atr": 14, "expand": 1.4}, entry="ATR expansion + directional close",
       exit_rule="Time stop or TP/SL", timeframe="15m", aliases=["burst"]),
    _t("mean_reversion_zscore", "Z-Score Mean Reversion", "mean_reversion", "Distance from SMA in σ",
       params={"length": 20, "entry_z": -2, "exit_z": 0}, entry="Z-score <= -2",
       exit_rule="Z-score >= 0", aliases=["zscore", "z-score"]),
    _t("kalman_trend", "Kalman Trend Proxy", "trend", "Smooth trend estimate crossover",
       params={"q": 0.001, "r": 0.01}, entry="Price crosses above Kalman estimate",
       exit_rule="Cross below", aliases=["kalman"]),

    # Risk / overlay templates (combinable notes)
    _t("fixed_rr_2", "Fixed R:R 1:2", "risk", "Entry any signal; enforce 1:2 reward",
       params={"rr": 2}, entry="User/template signal", exit_rule="SL 1R / TP 2R",
       default_tp=12, default_sl=6, aliases=["1:2", "rr 2"]),
    _t("fixed_rr_3", "Fixed R:R 1:3", "risk", "Entry any signal; enforce 1:3 reward",
       params={"rr": 3}, entry="User/template signal", exit_rule="SL 1R / TP 3R",
       default_tp=18, default_sl=6, aliases=["1:3", "rr 3"]),
    _t("time_stop_24h", "24h Time Stop", "risk", "Force exit if thesis not working",
       params={"hours": 24}, entry="Any", exit_rule="Flat after 24h if not TP",
       aliases=["time stop"]),
    _t("max_daily_loss", "Max Daily Loss Guard", "risk", "Halt new entries after daily loss",
       params={"max_loss_pct": 3}, entry="Allowed only if day PnL > -3%", exit_rule="Halt",
       aliases=["daily loss"]),

    # More popular named indicators / systems
    _t("awesome_oscillator", "Awesome Oscillator", "momentum", "AO zero / saucer",
       params={}, entry="AO crosses above 0 or saucer", exit_rule="AO crosses below 0",
       aliases=["ao", "awesome"]),
    _t("ultimate_oscillator", "Ultimate Oscillator", "mean_reversion", "UO extremes",
       params={"buy": 30, "sell": 70}, entry="UO exits oversold", exit_rule="UO overbought",
       aliases=["uo"]),
    _t("trix", "TRIX", "trend", "TRIX signal cross",
       params={"length": 15, "signal": 9}, entry="TRIX crosses signal up", exit_rule="Cross down",
       aliases=["trix"]),
    _t("ppo", "Percentage Price Oscillator", "macd", "PPO cross (MACD % form)",
       params={"fast": 12, "slow": 26, "signal": 9}, entry="PPO crosses signal up",
       exit_rule="Cross down", aliases=["ppo"]),
    _t("kama_trend", "Kaufman AMA Trend", "trend", "Adaptive MA trend",
       params={"length": 10}, entry="Close above KAMA + rising", exit_rule="Close below KAMA",
       aliases=["kama", "ama"]),
    _t("alma_trend", "ALMA Trend", "trend", "Arnaud Legoux MA",
       params={"length": 9, "offset": 0.85, "sigma": 6}, entry="Close above ALMA",
       exit_rule="Close below ALMA", aliases=["alma"]),
    _t("vortex", "Vortex Indicator", "trend", "VI+ / VI- cross",
       params={"length": 14}, entry="VI+ crosses above VI-", exit_rule="Opposite cross",
       aliases=["vortex"]),
    _t("aroon", "Aroon Up/Down", "trend", "Aroon crossover",
       params={"length": 25}, entry="Aroon Up crosses above Aroon Down",
       exit_rule="Opposite", aliases=["aroon"]),
    _t("cmf", "Chaikin Money Flow", "volume", "CMF zero-line",
       params={"length": 20}, entry="CMF crosses above 0", exit_rule="CMF crosses below 0",
       aliases=["cmf", "chaikin"]),
    _t("obv_trend", "OBV Trend", "volume", "On-balance volume vs its MA",
       params={"ma": 20}, entry="OBV crosses above OBV MA", exit_rule="Cross below",
       aliases=["obv"]),
    _t("elder_ray", "Elder Ray", "trend", "Bull/Bear power",
       params={"ema": 13}, entry="Bear power rising while above EMA", exit_rule="Bull power fails",
       aliases=["elder"]),
    _t("force_index", "Force Index", "momentum", "Elder Force Index",
       params={"length": 13}, entry="FI crosses above 0", exit_rule="FI crosses below 0",
       aliases=["force index"]),
    _t("schaff_trend", "Schaff Trend Cycle", "trend", "STC cross",
       params={"fast": 23, "slow": 50, "cycle": 10}, entry="STC crosses up from low",
       exit_rule="STC crosses down from high", aliases=["schaff", "stc"]),
    _t("qstick", "Qstick", "momentum", "Candlestick body momentum",
       params={"length": 8}, entry="Qstick crosses above 0", exit_rule="Cross below 0",
       aliases=["qstick"]),
    _t("coppock", "Coppock Curve", "trend", "Long-term curve (adapted to crypto TF)",
       params={}, entry="Coppock turns up from below 0", exit_rule="Turns down",
       timeframe="4h", aliases=["coppock"]),
    _t("kst", "Know Sure Thing", "momentum", "KST signal cross",
       params={}, entry="KST crosses signal up", exit_rule="Cross down", aliases=["kst"]),
    _t("dpo", "Detrended Price Oscillator", "mean_reversion", "DPO zero cross",
       params={"length": 20}, entry="DPO crosses above 0", exit_rule="Cross below",
       aliases=["dpo"]),
    _t("fisher_transform", "Fisher Transform", "mean_reversion", "Fisher extreme reclaim",
       params={"length": 9}, entry="Fisher turns up from low", exit_rule="Turns down from high",
       aliases=["fisher"]),
    _t("heikin_ashi_trend", "Heikin Ashi Trend", "trend", "HA color streaks",
       params={"streak": 3}, entry="3+ green HA candles", exit_rule="HA flips red",
       aliases=["heikin ashi", "ha"]),
    _t("renko_proxy", "Range/Renko Proxy", "trend", "Fixed range continuation",
       params={"brick_pct": 1.0}, entry="Up brick sequence", exit_rule="Opposite brick",
       aliases=["renko"]),
    _t("pivot_bounce", "Classic Pivot Bounce", "mean_reversion", "Bounce from daily pivots",
       params={}, entry="Reject S1/S2 then reclaim", exit_rule="Pivot R levels",
       timeframe="1h", aliases=["pivots", "floor pivots"]),
    _t("fib_pullback", "Fib Pullback", "trend", "Buy 0.382–0.618 pullback in trend",
       params={"ratios": [0.382, 0.5, 0.618]}, entry="Pullback into fib zone + reclaim",
       exit_rule="Swing invalidation", aliases=["fib", "fibonacci"]),
    _t("market_structure_bos", "Break of Structure", "price_action", "BOS / CHOCH style rules",
       params={"swing": 5}, entry="Break of structure in trend direction",
       exit_rule="Change of character against", aliases=["bos", "choch", "smc"]),
    _t("liquidity_sweep", "Liquidity Sweep Reversal", "price_action", "Sweep highs/lows then reverse",
       params={"lookback": 20}, entry="Sweep then close back inside range",
       exit_rule="TP/SL", aliases=["liquidity sweep", "stop hunt"]),
    _t("range_fade", "Range Fade", "mean_reversion", "Fade established range edges",
       params={"lookback": 48}, entry="Touch range low + rejection", exit_rule="Mid/high of range",
       aliases=["range trade", "fade range"]),
    _t("trend_channel", "Trend Channel Ride", "trend", "Trade channel midline/breaks",
       params={"lookback": 40}, entry="Bounce channel low in uptrend", exit_rule="Channel high or break",
       aliases=["channel"]),
    _t("dual_thrust", "Dual Thrust", "breakout", "Classic Dual Thrust ranges",
       params={"n": 4, "k1": 0.5, "k2": 0.5}, entry="Break upper dual-thrust line",
       exit_rule="Break lower or TP/SL", aliases=["dual thrust"]),
    _t("abby_breakout", "Abby/Volatility Breakout", "breakout", "Prev range * k breakout",
       params={"k": 0.6}, entry="Open + k*prev_range break", exit_rule="Opposite / EOD proxy",
       aliases=["volatility breakout"]),
    _t("connors_rsi", "Connors RSI", "mean_reversion", "CRSI short-term mean reversion",
       params={"crsi_buy": 10, "crsi_sell": 90}, entry="CRSI < 10", exit_rule="CRSI > 90 or bars",
       aliases=["connors", "crsi"]),
    _t("rsi2", "RSI(2) Mean Reversion", "mean_reversion", "Connors-style RSI(2)",
       params={"rsi": 2, "buy": 10, "sell": 90, "trend_sma": 200},
       entry="Above SMA200 and RSI2 < 10", exit_rule="RSI2 > 90",
       aliases=["rsi 2", "rsi2"]),
    _t("sma_envelope", "SMA Envelope", "mean_reversion", "Percent envelopes around SMA",
       params={"sma": 20, "pct": 2.5}, entry="Touch lower envelope", exit_rule="Mid/upper",
       aliases=["envelope"]),
    _t("percent_b", "Bollinger %B", "mean_reversion", "Trade %B crosses",
       params={"length": 20, "std": 2}, entry="%B crosses above 0", exit_rule="%B crosses below 1",
       aliases=["%b", "percent b"]),
    _t("bandwidth_expand", "BB Width Expansion", "breakout", "Enter when bandwidth expands",
       params={"length": 20, "std": 2}, entry="Bandwidth rising from low + direction",
       exit_rule="Bandwidth peaks fade", aliases=["bb width"]),
    _t("tsi", "True Strength Index", "momentum", "TSI signal cross",
       params={"long": 25, "short": 13, "signal": 13}, entry="TSI crosses signal up",
       exit_rule="Cross down", aliases=["tsi"]),
    _t("rvi", "Relative Vigor Index", "momentum", "RVI signal cross",
       params={"length": 10}, entry="RVI crosses signal up", exit_rule="Cross down",
       aliases=["rvi"]),
    _t("mass_index", "Mass Index Reversal", "mean_reversion", "Mass index bulge reversal",
       params={"bulge": 27}, entry="Mass index falls from bulge", exit_rule="TP/SL",
       aliases=["mass index"]),
    _t("chandelier_long", "Chandelier Exit Long", "trend", "Long-only chandelier management",
       params={"atr": 22, "mult": 3}, entry="Trend entry then trail", exit_rule="Chandelier stop",
       aliases=["chandelier long"]),
    _t("turtle_unit", "Turtle Unit Sizing Overlay", "risk", "ATR unit sizing with breakout",
       params={"atr": 20, "unit_risk_pct": 1}, entry="Donchian entry", exit_rule="Turtle exit",
       aliases=["turtle sizing"]),
    _t("kelly_lite", "Kelly-lite Sizing Overlay", "risk", "Cap size from recent win rate",
       params={"lookback_trades": 30, "cap_pct": 25}, entry="Any", exit_rule="Size overlay only",
       aliases=["kelly"]),
    _t("vol_target", "Volatility Targeting", "risk", "Scale size to target vol",
       params={"target_vol": 0.4, "atr": 14}, entry="Any", exit_rule="Size overlay only",
       aliases=["vol target"]),
    _t("pair_relative", "Relative Strength Pair (spot)", "relative", "Rotate into stronger of two",
       params={"lookback": 24}, entry="Buy relative winner vs alt", exit_rule="Leadership flips",
       aliases=["relative strength", "rs rotate"]),
    _t("btc_beta_filter", "BTC Beta Filter", "filter", "Only long alts when BTC trend up",
       params={"btc_ema": 50}, entry="Alt signal + BTC > EMA50", exit_rule="BTC loses EMA50",
       aliases=["btc filter", "beta filter"]),
    _t("funding_ignore", "Spot-Only (Ignore Funding)", "filter", "Explicitly disable perp/funding logic",
       params={}, entry="Spot templates only", exit_rule="n/a",
       aliases=["no funding", "spot only"]),
    _t("custom_user", "Custom User Strategy", "custom", "Free-form user rules captured in notes",
       params={}, entry="As described by user", exit_rule="As described by user",
       aliases=["custom", "my strategy", "user strategy"]),
]

assert len(STRATEGY_TEMPLATES) >= 100, len(STRATEGY_TEMPLATES)

_BY_ID = {t["id"]: t for t in STRATEGY_TEMPLATES}


def list_strategy_templates(
    family: str = "",
    query: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    family = (family or "").strip().lower()
    query = (query or "").strip().lower()
    rows = STRATEGY_TEMPLATES
    if family:
        rows = [t for t in rows if t["family"] == family]
    if query:
        rows = [t for t in rows if _matches(t, query)]
    limit = max(1, min(int(limit or 150), 200))
    return {
        "count": len(rows[:limit]),
        "total_catalog": len(STRATEGY_TEMPLATES),
        "families": sorted({t["family"] for t in STRATEGY_TEMPLATES}),
        "templates": [
            {
                "id": t["id"],
                "name": t["name"],
                "family": t["family"],
                "summary": t["summary"],
                "default_tp_pct": t["default_tp_pct"],
                "default_sl_pct": t["default_sl_pct"],
                "timeframe": t["timeframe"],
                "aliases": t["aliases"],
            }
            for t in rows[:limit]
        ],
    }


def get_strategy_template(template_id: str) -> dict[str, Any]:
    tid = (template_id or "").strip().lower().replace(" ", "_")
    if tid in _BY_ID:
        return {"template": _BY_ID[tid]}
    # alias / fuzzy name
    hit = match_strategy_template(template_id)
    if hit.get("template"):
        return hit
    return {
        "error": f"Unknown template '{template_id}'",
        "hint": "Use list_strategy_templates or search by MACD, RSI, Supertrend, etc.",
        "total_catalog": len(STRATEGY_TEMPLATES),
    }


def _matches(t: dict[str, Any], query: str) -> bool:
    blob = " ".join(
        [
            t["id"],
            t["name"],
            t["family"],
            t["summary"],
            " ".join(t.get("aliases") or []),
        ]
    ).lower()
    return query in blob


def match_strategy_template(text: str) -> dict[str, Any]:
    q = (text or "").strip().lower()
    if not q:
        return {"error": "Provide a strategy name or keywords."}
    q_id = q.replace(" ", "_").replace("-", "_")
    if q_id in _BY_ID:
        return {"template": _BY_ID[q_id], "matched_by": "id"}

    exact: list[dict[str, Any]] = []
    partial: list[tuple[int, dict[str, Any]]] = []
    for t in STRATEGY_TEMPLATES:
        aliases = [
            t["id"],
            t["id"].replace("_", " "),
            t["name"].lower(),
            *(t.get("aliases") or []),
        ]
        found_exact = False
        best_partial: tuple[int, dict[str, Any]] | None = None
        for alias in aliases:
            a = str(alias).lower().strip()
            if not a:
                continue
            if a == q or a.replace(" ", "_") == q_id:
                exact.append(t)
                found_exact = True
                break
            if a in q or q in a:
                # Prefer closer lengths (avoid "macd" matching "macd rsi" first)
                score = abs(len(a) - len(q))
                if best_partial is None or score < best_partial[0]:
                    best_partial = (score, t)
        # Only use partial if this template has no exact alias hit
        if not found_exact and best_partial is not None:
            partial.append(best_partial)

    if exact:
        best = exact[0]
        alts = [t["id"] for t in exact[1:6] if t["id"] != best["id"]]
        return {"template": best, "matched_by": "exact_alias", "alternatives": alts}

    if partial:
        partial.sort(key=lambda x: x[0])
        best = partial[0][1]
        alts = [t["id"] for _, t in partial[1:6] if t["id"] != best["id"]]
        return {"template": best, "matched_by": "alias", "alternatives": alts}

    soft = [t for t in STRATEGY_TEMPLATES if _matches(t, q)]
    if soft:
        return {
            "template": soft[0],
            "matched_by": "search",
            "alternatives": [s["id"] for s in soft[1:6]],
        }
    return {"error": f"No template matched '{text}'", "total_catalog": len(STRATEGY_TEMPLATES)}


def format_template_for_understanding(template: dict[str, Any]) -> str:
    params = template.get("params") or {}
    param_txt = ", ".join(f"{k}={v}" for k, v in params.items()) if params else "defaults"
    return (
        f"- Algo template: {template['name']} (`{template['id']}` · {template['family']})\n"
        f"- Summary: {template['summary']}\n"
        f"- Params: {param_txt}\n"
        f"- Entry: {template.get('entry') or 'n/a'}\n"
        f"- Exit: {template.get('exit') or 'n/a'}\n"
        f"- Default TF: {template.get('timeframe') or '1h'}"
    )
