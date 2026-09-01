# Trading Bot V4

V4 fixes the target optimiser architecture.

The historical dataset is downloaded once and then every 5%-10% target is tested against the exact same data and signals. The selected target only changes the exit condition.

Other protections:
- signal from previous completed day
- entry at following day's open
- gap-aware target/stop
- conservative stop-first assumption if both are touched on one daily bar
- commission and slippage
- risk-based sizing
- maximum holding period
- force-close of remaining positions at end of test
- cache clear button
- 35-stock scanner
- equity curve, trades, win rate, profit factor and drawdown

This remains a research/paper-trading tool and does not place live orders.
