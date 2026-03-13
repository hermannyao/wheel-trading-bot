import importlib
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import database


def make_test_client():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    database.engine = engine
    database.SessionLocal = TestingSessionLocal
    database.Base.metadata.create_all(bind=engine)

    main = importlib.import_module('main')
    importlib.reload(main)
    return TestClient(main.app)


def test_scan_config():
    client = make_test_client()
    res = client.get('/api/scan-config')
    assert res.status_code == 200
    data = res.json()
    assert 'min_apr' in data
    assert 'sp500_local_file' in data


def test_trigger_scan_inserts_signals(monkeypatch):
    client = make_test_client()

    def fake_run_scan(overrides):
        return {
            'signals': [
                {
                    'symbol': 'TEST',
                    'price': 100.0,
                    'strike': 95.0,
                    'dte': 30,
                    'bid': 1.0,
                    'ask': 1.2,
                    'delta': 0.25,
                    'iv': 0.3,
                    'openInterest': 200,
                    'volume': 10,
                    'spread': 0.2,
                    'apr': 12.5,
                    'contract_price': 100.0,
                    'max_profit': 100.0,
                    'distance_to_strike_pct': -5.0,
                    'is_itm': False,
                    'status': 'SELL PUT',
                    'expiration': '2026-04-10',
                    'contracts': 1,
                    'budget_used': 9500.0,
                    'max_budget_per_trade': 10000.0,
                }
            ],
            'symbols_total': 1,
            'symbols_priced': 1,
            'symbols_affordable': 1,
        }

    import main

    def fake_start(_params):
        db = database.SessionLocal()
        try:
            sig = fake_run_scan({})['signals'][0]
            db.add(database.Signal(
                symbol=sig['symbol'],
                price=sig['price'],
                strike=sig['strike'],
                dte=sig['dte'],
                bid=sig['bid'],
                ask=sig['ask'],
                delta=sig['delta'],
                iv=sig['iv'],
                open_interest=sig['openInterest'],
                volume=sig['volume'],
                spread=sig['spread'],
                apr=sig['apr'],
                contract_price=sig['contract_price'],
                max_profit=sig['max_profit'],
                distance_to_strike_pct=sig['distance_to_strike_pct'],
                is_itm=0,
                status=sig['status'],
                expiration=sig['expiration'],
                contracts=sig['contracts'],
                budget_used=sig['budget_used'],
                max_budget_per_trade=sig['max_budget_per_trade'],
                scan_id='test-scan',
            ))
            db.commit()
        finally:
            db.close()
        return 'test-scan'

    monkeypatch.setattr(main.scan_runner, 'start', fake_start)

    res = client.post('/api/scan/run', json={
        'capital': 10000,
        'delta_target': 0.25,
        'min_dte': 30,
        'max_dte': 45,
        'min_iv': 0.2,
        'min_apr': 8,
    })
    assert res.status_code == 202

    res_signals = client.get('/api/signals?limit=10')
    assert res_signals.status_code == 200
    data = res_signals.json()
    assert len(data) == 1
    assert data[0]['symbol'] == 'TEST'
