import yfinance as yf
import datetime

ticker = "NVDA"
start_date = "2025-05-02"
end_date = "2025-05-03"

print(f"Fetching data for {ticker} from {start_date} to {end_date}...")
data = yf.download(ticker, start=start_date, end=end_date)

if not data.empty:
    print(data)
    # Accessing specific columns if needed, but printing the dataframe is usually enough
    # Note: yfinance might return a MultiIndex columns if multiple tickers, but here it's one.
else:
    print("No data found.")
