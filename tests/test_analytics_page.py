"""Tests for the Analytics "coming soon" page (GET /analytics)."""
import html
import re

import pytest

import app as app_module
import database.db as db_module

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_spendly.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    conn = db_module.get_db()
    db_module.init_db(conn)
    db_module.seed_db(conn)
    conn.close()
    return db_file


@pytest.fixture
def client(seeded_db):
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as test_client:
        yield test_client


def log_in(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


@pytest.fixture
def auth_client(client):
    log_in(client)
    return client


def page(response):
    return html.unescape(response.get_data(as_text=True))


def analytics_links(body):
    """Return the opening <a ...> tags whose href points to /analytics."""
    tags = re.findall(r"<a\b[^>]*>", body, flags=re.IGNORECASE)
    return [t for t in tags if re.search(r"""href=["']/analytics/?["']""", t)]


class TestAuthGuard:
    def test_analytics_logged_out_redirects_to_login(self, client):
        response = client.get("/analytics", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


class TestAnalyticsPage:
    def test_analytics_logged_in_returns_200(self, auth_client):
        response = auth_client.get("/analytics")
        assert response.status_code == 200

    def test_analytics_contains_heading(self, auth_client):
        assert "Advanced Analytics" in page(auth_client.get("/analytics"))

    def test_analytics_contains_coming_soon(self, auth_client):
        assert "coming soon" in page(auth_client.get("/analytics")).lower()

    def test_analytics_contains_tagline(self, auth_client):
        body = page(auth_client.get("/analytics")).replace("’", "'")
        assert "We're crafting something special" in body


class TestNavbar:
    @pytest.mark.parametrize("path", ["/profile", "/analytics"])
    def test_logged_in_nav_has_analytics_link(self, auth_client, path):
        body = page(auth_client.get(path))
        assert analytics_links(body), f"Expected Analytics link on {path}"
        assert "Analytics" in body

    @pytest.mark.parametrize("path", ["/", "/login"])
    def test_logged_out_nav_has_no_analytics_link(self, client, path):
        response = client.get(path)
        assert response.status_code == 200
        assert not analytics_links(page(response)), (
            f"Logged-out {path} must not link to /analytics"
        )


class TestActiveState:
    def test_analytics_link_is_active_on_analytics_page(self, auth_client):
        links = analytics_links(page(auth_client.get("/analytics")))
        assert links, "Expected Analytics nav link"
        assert any(
            "is-active" in t and re.search(r"""aria-current=["']page["']""", t)
            for t in links
        ), f"Expected is-active and aria-current=page, got {links}"

    def test_analytics_link_not_active_on_profile_page(self, auth_client):
        links = analytics_links(page(auth_client.get("/profile")))
        assert links, "Expected Analytics nav link on profile"
        for tag in links:
            assert "is-active" not in tag, f"Unexpected is-active: {tag}"


class TestStaticAssets:
    @pytest.mark.parametrize(
        "path",
        [
            "/static/css/analytics.css",
            "/static/img/analytics/clock.svg",
            "/static/img/analytics/progress.svg",
            "/static/img/analytics/corner-ornament.svg",
        ],
    )
    def test_static_asset_returns_200(self, client, path):
        response = client.get(path)
        assert response.status_code == 200, f"{path} should be served"
        response.close()
