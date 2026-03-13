from datetime import datetime, timedelta

import pandas as pd

import scanner


class DummyChain:
    def __init__(self, puts_df: pd.DataFrame):
        self.puts = puts_df


class DummyTicker:
    def __init__(self, options, puts_df: pd.DataFrame):
        self.options = options
        self._puts_df = puts_df

    def option_chain(self, expiration):
        return DummyChain(self._puts_df)


def make_puts_df(strike=95.0, bid=1.0, ask=1.2, iv=0.3, oi=200, volume=10):
    return pd.DataFrame([
        {
            'strike': strike,
            'bid': bid,
            'ask': ask,
            'impliedVolatility': iv,
            'openInterest': oi,
            'volume': volume,
        }
    ])


def test_calc_apr():
    apr = scanner._calc_apr(1.0, 100.0, 30)
    assert apr == round((1.0 / 100.0) * (365 / 30) * 100, 2)


def test_scan_symbol_filters_itm(monkeypatch):
    exp = (datetime.utcnow().date() + timedelta(days=30)).strftime('%Y-%m-%d')
    puts_df = make_puts_df(strike=110.0, bid=1.0, ask=1.2, volume=10)
    dummy = DummyTicker([exp], puts_df)

    monkeypatch.setattr(scanner.yf, 'Ticker', lambda symbol: dummy)

    res = scanner.scan_symbol('TEST', price=100.0, overrides={'min_dte': 21, 'max_dte': 45})
    assert res is None


def test_scan_symbol_filters_bid_or_volume(monkeypatch):
    exp = (datetime.utcnow().date() + timedelta(days=30)).strftime('%Y-%m-%d')
    puts_df = make_puts_df(strike=95.0, bid=0.0, ask=1.2, volume=10)
    dummy = DummyTicker([exp], puts_df)

    monkeypatch.setattr(scanner.yf, 'Ticker', lambda symbol: dummy)

    res = scanner.scan_symbol('TEST', price=100.0, overrides={'min_dte': 21, 'max_dte': 45})
    assert res is None

    puts_df2 = make_puts_df(strike=95.0, bid=1.0, ask=1.2, volume=0)
    dummy2 = DummyTicker([exp], puts_df2)
    monkeypatch.setattr(scanner.yf, 'Ticker', lambda symbol: dummy2)

    res2 = scanner.scan_symbol('TEST', price=100.0, overrides={'min_dte': 21, 'max_dte': 45})
    assert res2 is None


def test_scan_symbol_filters_min_apr(monkeypatch):
    exp = (datetime.utcnow().date() + timedelta(days=30)).strftime('%Y-%m-%d')
    puts_df = make_puts_df(strike=95.0, bid=0.1, ask=0.2, volume=10)
    dummy = DummyTicker([exp], puts_df)

    monkeypatch.setattr(scanner.yf, 'Ticker', lambda symbol: dummy)

    res = scanner.scan_symbol('TEST', price=100.0, overrides={'min_dte': 21, 'max_dte': 45, 'min_apr': 50})
    assert res is None


def test_scan_symbol_success(monkeypatch):
    exp = (datetime.utcnow().date() + timedelta(days=30)).strftime('%Y-%m-%d')
    puts_df = make_puts_df(strike=95.0, bid=1.0, ask=1.2, volume=10)
    dummy = DummyTicker([exp], puts_df)

    monkeypatch.setattr(scanner.yf, 'Ticker', lambda symbol: dummy)
    monkeypatch.setattr(scanner, '_put_delta', lambda *_: -0.25)

    res = scanner.scan_symbol(
        'TEST',
        price=100.0,
        overrides={'min_dte': 21, 'max_dte': 45, 'min_apr': 1, 'capital': 10000, 'max_spread_pct': 0.3},
    )
    assert res is not None
    assert res['symbol'] == 'TEST'
    assert res['strike'] == 95.0


def test_scan_symbol_filters_spread_too_large(monkeypatch):
    exp = (datetime.utcnow().date() + timedelta(days=30)).strftime('%Y-%m-%d')
    puts_df = make_puts_df(strike=95.0, bid=1.0, ask=1.7, volume=10)
    dummy = DummyTicker([exp], puts_df)
    monkeypatch.setattr(scanner.yf, 'Ticker', lambda symbol: dummy)

    res = scanner.scan_symbol('TEST', price=100.0, overrides={'min_dte': 21, 'max_dte': 45})
    assert res is None


def test_scan_symbol_filters_open_interest(monkeypatch):
    exp = (datetime.utcnow().date() + timedelta(days=30)).strftime('%Y-%m-%d')
    puts_df = make_puts_df(strike=95.0, bid=1.0, ask=1.2, oi=50, volume=10)
    dummy = DummyTicker([exp], puts_df)
    monkeypatch.setattr(scanner.yf, 'Ticker', lambda symbol: dummy)

    res = scanner.scan_symbol('TEST', price=100.0, overrides={'min_dte': 21, 'max_dte': 45})
    assert res is None


def test_scan_symbol_filters_iv_min(monkeypatch):
    exp = (datetime.utcnow().date() + timedelta(days=30)).strftime('%Y-%m-%d')
    puts_df = make_puts_df(strike=95.0, bid=1.0, ask=1.2, iv=0.1, volume=10)
    dummy = DummyTicker([exp], puts_df)
    monkeypatch.setattr(scanner.yf, 'Ticker', lambda symbol: dummy)

    res = scanner.scan_symbol('TEST', price=100.0, overrides={'min_dte': 21, 'max_dte': 45, 'min_iv': 0.2})
    assert res is None


def test_scan_symbol_filters_budget_exceeded(monkeypatch):
    exp = (datetime.utcnow().date() + timedelta(days=30)).strftime('%Y-%m-%d')
    puts_df = make_puts_df(strike=95.0, bid=1.0, ask=1.2, volume=10)
    dummy = DummyTicker([exp], puts_df)
    monkeypatch.setattr(scanner.yf, 'Ticker', lambda symbol: dummy)

    res = scanner.scan_symbol(
        'TEST',
        price=110.0,
        overrides={'min_dte': 21, 'max_dte': 45, 'capital': 5000},
    )
    assert res is None


def test_scan_symbol_filters_dte_out_of_window(monkeypatch):
    exp = (datetime.utcnow().date() + timedelta(days=10)).strftime('%Y-%m-%d')
    puts_df = make_puts_df(strike=95.0, bid=1.0, ask=1.2, volume=10)
    dummy = DummyTicker([exp], puts_df)
    monkeypatch.setattr(scanner.yf, 'Ticker', lambda symbol: dummy)

    res = scanner.scan_symbol('TEST', price=100.0, overrides={'min_dte': 21, 'max_dte': 45})
    assert res is None


def test_scan_symbol_filters_delta_out_of_range(monkeypatch):
    exp = (datetime.utcnow().date() + timedelta(days=30)).strftime('%Y-%m-%d')
    puts_df = make_puts_df(strike=95.0, bid=1.0, ask=1.2, volume=10)
    dummy = DummyTicker([exp], puts_df)
    monkeypatch.setattr(scanner.yf, 'Ticker', lambda symbol: dummy)
    monkeypatch.setattr(scanner, '_put_delta', lambda *_: -0.6)

    res = scanner.scan_symbol('TEST', price=100.0, overrides={'min_dte': 21, 'max_dte': 45})
    assert res is None


def test_scan_symbol_filters_otm_distance(monkeypatch):
    exp = (datetime.utcnow().date() + timedelta(days=30)).strftime('%Y-%m-%d')
    puts_df = make_puts_df(strike=96.0, bid=1.0, ask=1.2, volume=10)
    dummy = DummyTicker([exp], puts_df)
    monkeypatch.setattr(scanner.yf, 'Ticker', lambda symbol: dummy)

    res = scanner.scan_symbol('TEST', price=100.0, overrides={'min_dte': 21, 'max_dte': 45})
    assert res is None


def test_scan_all_symbols_without_data_ignored(monkeypatch):
    monkeypatch.setattr(scanner, 'fetch_sp500_symbols', lambda: ['AAA', 'BBB'])
    monkeypatch.setattr(scanner, 'fetch_prices_bulk', lambda symbols: {'AAA': 10.0})
    monkeypatch.setattr(scanner, 'scan_symbol', lambda *args, **kwargs: None)

    result = scanner.scan_all(capital=3000, overrides={})
    assert result['symbols_total'] == 2
    assert result['symbols_priced'] == 1
    assert result['symbols_affordable'] == 1
    assert result['signals'] == []


def test_fetch_sp500_symbols_fallback_wikipedia(monkeypatch):
    html = """
    <html><body>
      <table id="constituents">
        <tr><th>Symbol</th></tr>
        <tr><td>AAA</td></tr>
        <tr><td>BBB</td></tr>
      </table>
    </body></html>
    """

    class DummyResp:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    monkeypatch.setattr(scanner, '_read_local_symbols', lambda: [])
    monkeypatch.setattr(scanner, '_read_exclude_symbols', lambda: set())
    monkeypatch.setattr(scanner.requests, 'get', lambda *args, **kwargs: DummyResp(html))

    symbols = scanner.fetch_sp500_symbols()
    assert symbols == ['AAA', 'BBB']
