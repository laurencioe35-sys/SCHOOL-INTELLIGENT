from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_token


def test_accounting_chart_and_journal_flow():
    client = TestClient(app)
    tenant_id = str(uuid4())
    headers = {"Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=tenant_id, role='admin')}"}

    account = client.post(
        "/api/v1/accounting/chart-of-accounts",
        json={"code": "1105", "name": "Caja General", "account_type": "asset"},
        headers=headers,
    )
    assert account.status_code == 201, account.text

    account_2 = client.post(
        "/api/v1/accounting/chart-of-accounts",
        json={"code": "2105", "name": "Cuentas por Cobrar", "account_type": "asset"},
        headers=headers,
    )
    assert account_2.status_code == 201, account_2.text

    journal = client.post(
        "/api/v1/accounting/journal-entries",
        json={
            "entry_number": "JE-001",
            "memo": "Payment realization",
            "lines": [
                {"account_id": account.json()["id"], "debit_cents": 1000, "credit_cents": 0},
                {"account_id": account_2.json()["id"], "debit_cents": 0, "credit_cents": 1000},
            ],
        },
        headers=headers,
    )
    assert journal.status_code == 201, journal.text

    balance = client.get("/api/v1/accounting/trial-balance", headers=headers)
    assert balance.status_code == 200, balance.text
    payload = balance.json()
    assert len(payload) >= 2
