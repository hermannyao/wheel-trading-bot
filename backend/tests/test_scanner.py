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

    res = scanner.scan_symbol('TEST', price=100.0, overrides={'min_dte': 21, 'max_dte': 45, 'min_apr': 1})
    assert res is not None
    assert res['symbol'] == 'TEST'
    assert res['strike'] == 95.0
