# Trading Bot V3

This version fixes an important V2 backtesting flaw: signals are calculated from the completed prior trading day and entries are assumed at the following day's open. This avoids look-ahead from using the same closing price to both generate and execute a signal.

It also uses daily high/low for exits, handles opening gaps, uses a conservative stop-first assumption when both target and stop are touched on the same daily bar, includes commission/slippage, and provides stock ranking plus 5%-10% target optimisation.

Paper/backtest only. No Trading 212 orders are placed.
