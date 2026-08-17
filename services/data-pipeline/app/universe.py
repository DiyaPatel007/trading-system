"""
Starting trading universe: NIFTY 50 constituents, as Yahoo Finance
tickers (.NS suffix for NSE). This is a static list for now -- a later
module can replace this with a dynamic fetch from an index-constituents
source, but hardcoding is the right choice to start: it's simple,
debuggable, and small enough to sanity-check by eye.

List current as of this module's authoring -- constituents change
periodically when NSE rebalances the index, AND when a listed company
demerges, renames, or changes its trading symbol. Update this list
when that happens; nothing else in the pipeline needs to change.

Known corporate actions already reflected below:
- Tata Motors demerged (Oct/Nov 2025) into two separately listed
  companies: TMPV.NS (Tata Motors Passenger Vehicles) and TMCV.NS
  (Tata Motors Ltd, commercial vehicles). The old TATAMOTORS.NS
  ticker no longer resolves.
- LTIMindtree's trading symbol changed from LTIM to LTM (effective
  27 Feb 2026), alongside a rebrand to "LTM Limited."
"""

NIFTY_50: list[str] = [
    "ADANIENT.NS", "ADANIPORTS.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS", "AXISBANK.NS",
    "BAJAJ-AUTO.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "BEL.NS", "BHARTIARTL.NS",
    "CIPLA.NS", "COALINDIA.NS", "DRREDDY.NS", "EICHERMOT.NS", "GRASIM.NS",
    "HCLTECH.NS", "HDFCBANK.NS", "HDFCLIFE.NS", "HEROMOTOCO.NS", "HINDALCO.NS",
    "HINDUNILVR.NS", "ICICIBANK.NS", "ITC.NS", "INDUSINDBK.NS", "INFY.NS",
    "JSWSTEEL.NS", "KOTAKBANK.NS", "LT.NS", "M&M.NS", "MARUTI.NS",
    "NTPC.NS", "NESTLEIND.NS", "ONGC.NS", "POWERGRID.NS", "RELIANCE.NS",
    "SBILIFE.NS", "SHRIRAMFIN.NS", "SBIN.NS", "SUNPHARMA.NS", "TCS.NS",
    "TATACONSUM.NS", "TMPV.NS", "TMCV.NS", "TATASTEEL.NS", "TECHM.NS", "TITAN.NS",
    "TRENT.NS", "ULTRACEMCO.NS", "UPL.NS", "WIPRO.NS", "LTM.NS",
]