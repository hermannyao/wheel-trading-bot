import importlib
from datetime import datetime, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import database


def make_client():
    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    database.engine = engine
    database.SessionLocal = TestingSessionLocal
    database.Base.metadata.create_all(bind=engine)

    main = importlib.import_module('main')
    importlib.reload(main)
    return TestClient(main.app), main


def test_spot_guard(monkeypatch):
    client, main = make_client()
    payload = {
        'symbol': 'AAL',
        'position_type': 'SELL PUT',
        'strike': 10.0,
        'dte_open': 30,
        'expiration_date': date.today().isoformat(),
        'premium_received': 0.5,
        'contracts': 1,
        'opened_at': datetime.utcnow().isoformat(),
    }
    res = client.post('/api/positions', json=payload)
    assert res.status_code == 200
    pos = res.json()
    res2 = client.patch(
        f"/api/positions/{pos['id']}",
        json={'status': 'ASSIGNED', 'assigned_at': datetime.utcnow().isoformat()},
    )
    assert res2.status_code == 200

    monkeypatch.setattr(main, 'fetch_prices_bulk', lambda symbols: {'AAL': 1000.0})
    monkeypatch.setattr(main, 'scan_covered_calls', lambda **kwargs: [])

    res3 = client.get('/api/positions/assigned-calls')
    assert res3.status_code == 200
    data = res3.json()
    assert data[0]['status'] == 'spot_incoherent'


def test_cost_basis_simple_cycle(monkeypatch):
    client, main = make_client()
    payload = {
        'symbol': 'AAL',
        'position_type': 'SELL PUT',
        'strike': 10.0,
        'dte_open': 30,
        'expiration_date': date.today().isoformat(),
        'premium_received': 0.5,
        'contracts': 1,
        'opened_at': datetime.utcnow().isoformat(),
    }
    res = client.post('/api/positions', json=payload)
    pos = res.json()
    client.patch(
        f"/api/positions/{pos['id']}",
        json={'status': 'ASSIGNED', 'assigned_at': datetime.utcnow().isoformat()},
    )
    monkeypatch.setattr(main, 'fetch_prices_bulk', lambda symbols: {'AAL': 10.0})
    monkeypatch.setattr(main, 'scan_covered_calls', lambda **kwargs: [])
    res2 = client.get('/api/positions/assigned-calls')
    data = res2.json()[0]
    assert data['cost_basis_adjusted'] == 9.5


def test_cost_basis_multi_call(monkeypatch):
    client, main = make_client()
    payload = {
        'symbol': 'AAL',
        'position_type': 'SELL PUT',
        'strike': 10.0,
        'dte_open': 30,
        'expiration_date': date.today().isoformat(),
        'premium_received': 0.5,
        'contracts': 1,
        'opened_at': datetime.utcnow().isoformat(),
    }
    res = client.post('/api/positions', json=payload)
    pos = res.json()
    client.patch(
        f"/api/positions/{pos['id']}",
        json={'status': 'ASSIGNED', 'assigned_at': datetime.utcnow().isoformat()},
    )
    client.post(
        f"/api/positions/{pos['id']}/legs",
        json={'leg_type': 'SELL CALL', 'strike': 10.5, 'premium_received': 0.2},
    )
    client.post(
        f"/api/positions/{pos['id']}/legs",
        json={'leg_type': 'SELL CALL', 'strike': 11.0, 'premium_received': 0.1},
    )
    monkeypatch.setattr(main, 'fetch_prices_bulk', lambda symbols: {'AAL': 10.0})
    monkeypatch.setattr(main, 'scan_covered_calls', lambda **kwargs: [])
    res2 = client.get('/api/positions/assigned-calls')
    data = res2.json()[0]
    assert data['cost_basis_adjusted'] == 9.2


def test_snoozed_position(monkeypatch):
    client, main = make_client()
    payload = {
        'symbol': 'AAL',
        'position_type': 'SELL PUT',
        'strike': 10.0,
        'dte_open': 30,
        'expiration_date': date.today().isoformat(),
        'premium_received': 0.5,
        'contracts': 1,
        'opened_at': datetime.utcnow().isoformat(),
    }
    res = client.post('/api/positions', json=payload)
    pos = res.json()
    client.patch(
        f"/api/positions/{pos['id']}",
        json={'status': 'ASSIGNED', 'assigned_at': datetime.utcnow().isoformat()},
    )
    client.post(
        f"/api/positions/{pos['id']}/snooze?snooze_until={date.today().isoformat()}",
    )
    monkeypatch.setattr(main, 'fetch_prices_bulk', lambda symbols: {'AAL': 10.0})
    monkeypatch.setattr(main, 'scan_covered_calls', lambda **kwargs: [])
    res2 = client.get('/api/positions/assigned-calls')
    data = res2.json()[0]
    assert data['status'] == 'snoozed'


def test_cost_basis_no_premium(monkeypatch):
    client, main = make_client()
    payload = {
        'symbol': 'AAL',
        'position_type': 'SELL PUT',
        'strike': 10.0,
        'dte_open': 30,
        'expiration_date': date.today().isoformat(),
        'premium_received': 0.0,
        'contracts': 1,
        'opened_at': datetime.utcnow().isoformat(),
    }
    res = client.post('/api/positions', json=payload)
    pos = res.json()
    client.patch(
        f"/api/positions/{pos['id']}",
        json={'status': 'ASSIGNED', 'assigned_at': datetime.utcnow().isoformat()},
    )
    monkeypatch.setattr(main, 'fetch_prices_bulk', lambda symbols: {'AAL': 10.0})
    monkeypatch.setattr(main, 'scan_covered_calls', lambda **kwargs: [])
    res2 = client.get('/api/positions/assigned-calls')
    data = res2.json()[0]
    assert data['cost_basis_adjusted'] == 10.0


def test_cost_basis_multiple_contracts(monkeypatch):
    client, main = make_client()
    payload = {
        'symbol': 'AAL',
        'position_type': 'SELL PUT',
        'strike': 10.0,
        'dte_open': 30,
        'expiration_date': date.today().isoformat(),
        'premium_received': 0.5,
        'contracts': 3,
        'opened_at': datetime.utcnow().isoformat(),
    }
    res = client.post('/api/positions', json=payload)
    pos = res.json()
    client.patch(
        f"/api/positions/{pos['id']}",
        json={'status': 'ASSIGNED', 'assigned_at': datetime.utcnow().isoformat()},
    )
    client.post(
        f"/api/positions/{pos['id']}/legs",
        json={'leg_type': 'SELL CALL', 'strike': 10.5, 'premium_received': 0.2},
    )
    monkeypatch.setattr(main, 'fetch_prices_bulk', lambda symbols: {'AAL': 10.0})
    monkeypatch.setattr(main, 'scan_covered_calls', lambda **kwargs: [])
    res2 = client.get('/api/positions/assigned-calls')
    data = res2.json()[0]
    assert data['cost_basis_adjusted'] == 9.3


def test_double_call_rejected():
    client, _ = make_client()
    payload = {
        'symbol': 'AAL',
        'position_type': 'SELL PUT',
        'strike': 10.0,
        'dte_open': 30,
        'expiration_date': date.today().isoformat(),
        'premium_received': 0.5,
        'contracts': 1,
        'opened_at': datetime.utcnow().isoformat(),
    }
    res = client.post('/api/positions', json=payload)
    pos = res.json()
    client.patch(
        f"/api/positions/{pos['id']}",
        json={'status': 'ASSIGNED', 'assigned_at': datetime.utcnow().isoformat()},
    )
    res2 = client.post(
        f"/api/positions/{pos['id']}/legs",
        json={'leg_type': 'SELL CALL', 'strike': 10.5, 'premium_received': 0.2},
    )
    assert res2.status_code == 200
    res3 = client.post(
        f"/api/positions/{pos['id']}/legs",
        json={'leg_type': 'SELL CALL', 'strike': 11.0, 'premium_received': 0.1},
    )
    assert res3.status_code == 409
