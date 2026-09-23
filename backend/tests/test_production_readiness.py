from app.config import Settings, reset_settings


def test_production_defaults_are_reported_as_blockers():
    reset_settings()
    settings = Settings(environment="production")

    assert settings.production_blockers
    try:
        settings.validate_production_settings()
    except RuntimeError as error:
        assert "unsafe" in str(error)
    else:
        raise AssertionError("unsafe production defaults must be rejected")


def test_production_configuration_can_be_validated():
    reset_settings()
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://user:pass@db/app",
        jwt_secret="a" * 64,
        cors_origins="https://portal.example.com",
    )

    assert settings.production_blockers == []
    settings.validate_production_settings()


def test_deployment_settings_support_api_base_url_and_trimmed_cors():
    reset_settings()
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://user:pass@db/app",
        jwt_secret="a" * 64,
        cors_origins=" https://portal.example.com, https://admin.example.com , ",
        api_base_url="https://api.example.com",
    )

    assert settings.api_base_url == "https://api.example.com"
    assert settings.cors_list == ["https://portal.example.com", "https://admin.example.com"]


def test_tenant_rate_limit_rejects_excessive_requests():
    from app.config import get_settings
    from app.main import app
    from app.security import create_access_token
    from fastapi.testclient import TestClient

    reset_settings()
    settings = get_settings()
    settings.rate_limit_enabled = True
    settings.rate_limit_per_tenant_per_minute = 2
    settings.rate_limit_per_ip_per_minute = 10
    settings.rate_limit_auth_per_ip_per_minute = 10

    try:
        client = TestClient(app)
        tenant_id = "11111111-1111-4111-8111-111111111111"
        user_id = "22222222-2222-4222-8222-222222222222"
        headers = {
            "Authorization": f"Bearer {create_access_token(user_id, tenant_id, 'admin')}",
            "Origin": "http://localhost:5173",
        }

        first = client.get("/api/v1/health", headers=headers)
        second = client.get("/api/v1/health", headers=headers)
        third = client.get("/api/v1/health", headers=headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        assert third.headers["access-control-allow-origin"] == "http://localhost:5173"
    finally:
        reset_settings()


def test_production_rate_limiting_requires_redis_for_shared_state():
    reset_settings()
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://user:pass@db/app",
        jwt_secret="a" * 64,
        cors_origins="https://portal.example.com",
        rate_limit_enabled=True,
        redis_url=None,
    )

    assert "REDIS_URL must be configured when rate limiting is enabled in production" in settings.production_blockers

    valid = Settings(
        environment="production",
        database_url="postgresql+psycopg://user:pass@db/app",
        jwt_secret="a" * 64,
        cors_origins="https://portal.example.com",
        rate_limit_enabled=True,
        redis_url="redis://redis:6379/0",
    )

    assert valid.production_blockers == []
