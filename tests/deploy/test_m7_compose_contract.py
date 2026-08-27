from __future__ import annotations

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCKER_ROOT = REPOSITORY_ROOT / "deploy" / "docker"
COMPOSE_ROOT = REPOSITORY_ROOT / "deploy" / "compose"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _compose(name: str = "compose.yaml") -> dict:
    return yaml.safe_load(_read(COMPOSE_ROOT / name))


def test_m7_images_copy_only_observability_app_sources() -> None:
    api = _read(DOCKER_ROOT / "Dockerfile.api")
    web = _read(DOCKER_ROOT / "Dockerfile.web")
    api_ignore = _read(DOCKER_ROOT / "Dockerfile.api.dockerignore")
    web_ignore = _read(DOCKER_ROOT / "Dockerfile.web.dockerignore")

    assert "COPY apps/api" in api
    assert "COPY apps/web" in web
    assert "COPY ." not in api
    assert "COPY ." not in web
    assert api_ignore.splitlines()[0] == "**"
    assert "!apps/api/**" in api_ignore
    assert web_ignore.splitlines()[0] == "**"
    assert "!apps/web/**" in web_ignore
    assert "apps/web/node_modules/" in web_ignore
    assert "apps/web/dist/" in web_ignore
    assert "apps/web/coverage/" in web_ignore

    forbidden = (".env", "graphs/", "libs/", "scripts/")
    assert all(value not in api for value in forbidden)
    assert all(value not in web for value in forbidden)


def test_m7_images_are_non_root_and_health_checked() -> None:
    api = _read(DOCKER_ROOT / "Dockerfile.api")
    web = _read(DOCKER_ROOT / "Dockerfile.web")

    assert "USER 10001:10001" in api
    assert "USER 101:101" in web
    assert "HEALTHCHECK" in api
    assert "HEALTHCHECK" in web
    assert '"--workers", "1"' in api


def test_m7_api_is_private_and_web_is_localhost_only() -> None:
    compose = _compose()
    services = compose["services"]
    api = services["api"]
    web = services["web"]

    assert "ports" not in api
    assert api["expose"] == ["8000"]
    assert web["ports"] == ["127.0.0.1:${OBSERVABILITY_WEB_PORT:-3000}:8080"]
    assert web["depends_on"]["api"]["condition"] == "service_healthy"
    assert set(api["networks"]) == {"observability"}
    assert set(web["networks"]) == {"observability", "edge"}
    assert compose["networks"]["observability"]["internal"] is True
    assert compose["networks"]["edge"] is None


def test_m7_evidence_mounts_are_read_only() -> None:
    api = _compose()["services"]["api"]
    mounts = {row["target"]: row for row in api["volumes"]}

    assert set(mounts) == {
        "/data/reports",
        "/data/runtime-logs",
        "/data/state",
        "/data/evidence",
    }
    assert all(row["type"] == "bind" for row in mounts.values())
    assert all(row["read_only"] is True for row in mounts.values())


def test_m7_services_enforce_runtime_isolation_limits() -> None:
    services = _compose()["services"]

    for service in services.values():
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert service["cpus"] > 0
        assert service["mem_limit"]
        assert service["pids_limit"] > 0
        assert service["tmpfs"]

    assert _compose()["networks"]["observability"]["internal"] is True


def test_m7_public_override_changes_only_api_exposure_profile() -> None:
    public = _compose("compose.public.yaml")

    assert set(public) == {"services"}
    assert set(public["services"]) == {"api"}
    assert public["services"]["api"] == {
        "environment": {"OBSERVABILITY_EXPOSURE_PROFILE": "public"}
    }


def test_m7_web_gateway_is_get_only_and_proxies_api_privately() -> None:
    nginx = _read(DOCKER_ROOT / "nginx.conf")

    assert "server api:8000" in nginx
    assert "location /api/" in nginx
    assert "location = /health/live" in nginx
    assert "location = /health/ready" in nginx
    assert "if ($request_method !~ ^(GET|HEAD)$)" in nginx
    assert "listen 8080" in nginx
