from app.config import Settings


def test_defaults_are_usable() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.redis_url.startswith("redis://")
    assert settings.broker_url == settings.redis_url
    assert settings.result_backend == settings.redis_url


def test_celery_overrides_take_precedence() -> None:
    settings = Settings(
        _env_file=None,
        celery_broker_url="redis://broker:6379/1",
        celery_result_backend="redis://backend:6379/2",
    )
    assert settings.broker_url == "redis://broker:6379/1"
    assert settings.result_backend == "redis://backend:6379/2"
