"""
Tests for EdgeTTSProvider._get_proxy_url security validation.

Covers:
- Valid proxy configurations (happy paths)
- Scheme injection via invalid proxy_type
- Host-confusion / credential-injection via '@' in proxy_server
- Path/query/fragment injection via '/', '?', '#' in proxy_server
- Protocol stripping from proxy_server values
"""
import pytest
import urllib.parse
from unittest.mock import MagicMock

from src.tts.providers.edge_tts_provider import EdgeTTSProvider


def _make_provider(settings: dict) -> EdgeTTSProvider:
    """Create an EdgeTTSProvider backed by a mock SettingsManager."""
    mgr = MagicMock()
    mgr.get.side_effect = lambda key, default=None: settings.get(key, default)
    provider = EdgeTTSProvider(settings_manager=mgr)
    return provider


def _enabled_settings(**overrides) -> dict:
    """Base settings dict with proxy enabled; override any field via kwargs."""
    base = {
        "proxy_enabled": True,
        "proxy_type": "http",
        "proxy_server": "proxy.example.com:8080",
        "proxy_username": "",
        "proxy_password": "",
    }
    base.update(overrides)
    return base


class TestGetProxyUrlHappyPaths:
    """Valid proxy configurations should produce correct URLs."""

    @pytest.mark.parametrize("proxy_type", ["http", "https", "socks4", "socks5"])
    def test_allowed_proxy_types(self, proxy_type):
        provider = _make_provider(_enabled_settings(proxy_type=proxy_type))
        url = provider._get_proxy_url()
        assert url is not None
        assert url.startswith(f"{proxy_type}://")

    def test_simple_host_and_port(self):
        provider = _make_provider(_enabled_settings(
            proxy_type="http", proxy_server="proxy.example.com:3128"
        ))
        assert provider._get_proxy_url() == "http://proxy.example.com:3128"

    def test_proxy_disabled_returns_none(self):
        provider = _make_provider(_enabled_settings(proxy_enabled=False))
        assert provider._get_proxy_url() is None

    def test_no_settings_manager_returns_none(self):
        provider = EdgeTTSProvider(settings_manager=None)
        assert provider._get_proxy_url() is None

    def test_empty_proxy_server_returns_none(self):
        provider = _make_provider(_enabled_settings(proxy_server=""))
        assert provider._get_proxy_url() is None

    def test_credentials_url_encoded(self):
        provider = _make_provider(_enabled_settings(
            proxy_username="user name",
            proxy_password="p@ss/word",
        ))
        url = provider._get_proxy_url()
        assert url is not None
        # Spaces and special chars must be percent-encoded
        assert "user%20name" in url
        assert "p%40ss%2Fword" in url

    def test_username_without_password(self):
        provider = _make_provider(_enabled_settings(
            proxy_username="bob",
            proxy_password="",
        ))
        url = provider._get_proxy_url()
        assert url is not None
        assert "bob@" in url
        assert ":@" not in url  # No empty password separator

    def test_protocol_prefix_stripped_from_server(self):
        """Users may paste a full URL into the proxy_server field."""
        provider = _make_provider(_enabled_settings(
            proxy_type="http",
            proxy_server="http://proxy.example.com:8080",
        ))
        url = provider._get_proxy_url()
        assert url == "http://proxy.example.com:8080"

    def test_mismatched_protocol_prefix_stripped(self):
        """Protocol in proxy_server that differs from proxy_type is replaced."""
        provider = _make_provider(_enabled_settings(
            proxy_type="socks5",
            proxy_server="http://proxy.example.com:1080",
        ))
        url = provider._get_proxy_url()
        assert url is not None
        parsed = urllib.parse.urlparse(url)
        assert parsed.scheme == "socks5"
        assert parsed.hostname == "proxy.example.com"
        assert parsed.port == 1080


class TestGetProxyUrlSchemeInjection:
    """proxy_type not in allowlist must return None (scheme injection prevention)."""

    @pytest.mark.parametrize("bad_type", [
        "file",       # file:///etc/passwd
        "javascript", # javascript:// URLs
        "data",       # data: URLs
        "ftp",        # FTP not supported
        "FILE",       # Case variants
        "",
        "   ",
        "http; DROP TABLE",
    ])
    def test_invalid_proxy_type_returns_none(self, bad_type):
        provider = _make_provider(_enabled_settings(proxy_type=bad_type))
        assert provider._get_proxy_url() is None


class TestGetProxyUrlServerInjection:
    """proxy_server containing '@', '/', '?', '#' must be rejected."""

    @pytest.mark.parametrize("bad_server", [
        # '@' injection: host-confusion / credential leak
        "attacker.com@real-server.com",
        "@real-server.com",
        "user@host.com:8080",
        # Path injection
        "proxy.com/steal",
        "proxy.com/path/to/resource",
        # Query injection
        "proxy.com?query=value",
        "proxy.com:8080?x=1",
        # Fragment injection
        "proxy.com#fragment",
        # Combined
        "attacker.com@proxy.com/path?q=1#frag",
    ])
    def test_invalid_server_characters_return_none(self, bad_server):
        provider = _make_provider(_enabled_settings(proxy_server=bad_server))
        assert provider._get_proxy_url() is None

    def test_server_with_embedded_at_after_protocol_strip_is_rejected(self):
        """Ensure '@' is still detected after protocol-stripping."""
        # e.g., "http://attacker.com@real.com" strips to "attacker.com@real.com"
        provider = _make_provider(_enabled_settings(
            proxy_type="http",
            proxy_server="http://attacker.com@real.com",
        ))
        assert provider._get_proxy_url() is None

    def test_server_with_path_after_protocol_strip_is_rejected(self):
        """Ensure '/' is still detected after protocol-stripping."""
        provider = _make_provider(_enabled_settings(
            proxy_type="http",
            proxy_server="http://proxy.com/malicious-path",
        ))
        assert provider._get_proxy_url() is None
