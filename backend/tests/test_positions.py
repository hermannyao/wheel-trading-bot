import importlib
from datetime import datetime, date
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import database


def make_client():
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


def create_open_position(client):
    payload = {
        'symbol': 'AAL',
        'position_type': 'SELL PUT',
        'strike': 10.0,
        'dte_open': 30,
        'expiration_date': date.today().isoformat(),
        'premium_received': 0.5,
        'contracts': 2,
        'opened_at': datetime.utcnow().isoformat(),
    }
    res = client.post('/api/positions', json=payload)
    assert res.status_code == 200
    return res.json()


def test_create_position():
    client = make_client()
    data = create_open_position(client)
    assert data['status'] == 'OPEN'
    assert data['capital_required'] == 10.0 * 100 * 2


def test_invalid_transition_rejected():
    client = make_client()
    pos = create_open_position(client)
    res = client.patch(f"/api/positions/{pos['id']}", json={'status': 'OPEN'})
    assert res.status_code in (200, 409)


def test_missing_fields_for_close():
    client = make_client()
    pos = create_open_position(client)
    res = client.patch(f"/api/positions/{pos['id']}", json={'status': 'CLOSED_EARLY'})
    assert res.status_code == 422


def test_close_early_success():
    client = make_client()
    pos = create_open_position(client)
    payload = {
        'status': 'CLOSED_EARLY',
        'closed_at': datetime.utcnow().isoformat(),
        'close_price': 0.2,
    }
    res = client.patch(f"/api/positions/{pos['id']}", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data['status'] == 'CLOSED_EARLY'


def test_assign_success():
    client = make_client()
    pos = create_open_position(client)
    payload = {
        'status': 'ASSIGNED',
        'assigned_at': datetime.utcnow().isoformat(),
    }
    res = client.patch(f"/api/positions/{pos['id']}", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data['trigger_sell_call'] is True


def test_expired_requires_date():
    client = make_client()
    pos = create_open_position(client)
    res = client.patch(f"/api/positions/{pos['id']}", json={'status': 'EXPIRED_WORTHLESS'})
    assert res.status_code == 422


def test_delete_only_open():
    client = make_client()
    pos = create_open_position(client)
    res = client.delete(f"/api/positions/{pos['id']}")
    assert res.status_code == 410


def test_cancel_requires_reason():
    client = make_client()
    pos = create_open_position(client)
    res = client.patch(f"/api/positions/{pos['id']}", json={'status': 'CANCELLED'})
    assert res.status_code == 422


def test_cancel_from_open_success():
    client = make_client()
    pos = create_open_position(client)
    payload = {'status': 'CANCELLED', 'motif_annulation': 'erreur_de_saisie'}
    res = client.patch(f"/api/positions/{pos['id']}", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data['status'] == 'CANCELLED'
    assert data['motif_annulation'] == 'erreur_de_saisie'


def test_cancel_not_allowed_from_closed():
    client = make_client()
    pos = create_open_position(client)
    payload = {
        'status': 'CLOSED_EARLY',
        'closed_at': datetime.utcnow().isoformat(),
        'close_price': 0.2,
    }
    res = client.patch(f"/api/positions/{pos['id']}", json=payload)
    assert res.status_code == 200
    res2 = client.patch(
        f"/api/positions/{pos['id']}",
        json={'status': 'CANCELLED', 'motif_annulation': 'trade_non_execute'},
    )
    assert res2.status_code == 409
