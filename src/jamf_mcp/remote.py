# Copyright 2026, Jamf Software LLC
"""Protected OAuth or scoped bearer authentication for Streamable HTTP.

OAuth discovers an external issuer's metadata and verifies RS256 access tokens
against its JWKS. Bearer mode verifies configured opaque credentials. Both modes
apply the same per-tool Jamf scopes before dispatch.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
import jwt
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware, get_access_token
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.routes import build_resource_metadata_url, create_protected_resource_routes
from mcp.server.auth.settings import AuthSettings
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import CallToolResult, TextContent
from pydantic import AnyHttpUrl, TypeAdapter
from starlette.applications import Starlette
from starlette.middleware import Middleware

logger = logging.getLogger(__name__)

ISSUER_ENV = "JAMF_MCP_OAUTH_ISSUER_URL"
RESOURCE_ENV = "JAMF_MCP_RESOURCE_URL"
AUDIENCE_ENV = "JAMF_MCP_OAUTH_AUDIENCE"
REMOTE_AUTH_MODE_ENV = "JAMF_MCP_REMOTE_AUTH_MODE"
BEARER_TOKENS_ENV = "JAMF_MCP_BEARER_TOKENS_JSON"

READ_SCOPE = "jamf:read"
WRITE_SCOPE = "jamf:write"
ADMIN_SCOPE = "jamf:admin"
SUPPORTED_SCOPES = frozenset({READ_SCOPE, WRITE_SCOPE, ADMIN_SCOPE})

# This tool returns a one-time client secret. Remote exposure stays disabled by
# default; local stdio registration is unaffected.
REMOTE_DISABLED_TOOL_NAMES = frozenset({"jamf_create_api_client_credentials"})

# These operations create or combine Jamf API roles and integrations. They need
# both ordinary write access and the explicit administrative grant.
ADMIN_TOOL_NAMES = frozenset(
    {
        "jamf_create_api_role",
        "jamf_create_api_integration",
        "jamf_create_api_client_credentials",
        "jamf_create_computer_update_api_client",
    }
)


class RemoteAuthConfigurationError(ValueError):
    """Raised when remote authentication is missing or unsafe to configure."""


RemoteAuthMode = Literal["oauth", "bearer"]


def remote_auth_mode_from_env(environ: Mapping[str, str] | None = None) -> RemoteAuthMode:
    """Return the selected remote auth mode, defaulting to external OAuth."""
    values = os.environ if environ is None else environ
    mode = values.get(REMOTE_AUTH_MODE_ENV, "oauth").strip().lower()
    if mode not in {"oauth", "bearer"}:
        raise RemoteAuthConfigurationError(
            f"{REMOTE_AUTH_MODE_ENV} must be either 'oauth' or 'bearer'"
        )
    return mode  # type: ignore[return-value]


def validate_remote_resource_url(value: str) -> str:
    """Validate a public remote resource URL and return it unchanged."""
    _validate_https_url(value, RESOURCE_ENV)
    return value


@dataclass(frozen=True, slots=True)
class RemoteAuthConfig:
    """Validated environment configuration for an external OAuth issuer."""

    issuer_url: str
    resource_url: str
    audience: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> RemoteAuthConfig:
        """Load and validate remote OAuth configuration from environment values."""
        values = os.environ if environ is None else environ
        issuer = values.get(ISSUER_ENV, "").strip()
        resource = values.get(RESOURCE_ENV, "").strip()
        missing = [
            name for name, value in ((ISSUER_ENV, issuer), (RESOURCE_ENV, resource)) if not value
        ]
        if missing:
            raise RemoteAuthConfigurationError(
                "Remote Streamable HTTP requires " + " and ".join(missing)
            )

        _validate_https_url(issuer, ISSUER_ENV)
        _validate_https_url(resource, RESOURCE_ENV)
        audience = values.get(AUDIENCE_ENV, "").strip() or resource
        if not audience or any(character.isspace() for character in audience):
            raise RemoteAuthConfigurationError(f"{AUDIENCE_ENV} must be a non-empty audience value")

        return cls(issuer_url=issuer, resource_url=resource, audience=audience)


@dataclass(frozen=True, slots=True)
class BearerTokenEntry:
    """A configured static bearer identity, with no retained plaintext token."""

    identity: str
    token_digest: bytes = field(repr=False)
    scopes: frozenset[str]


@dataclass(frozen=True, slots=True)
class RemoteBearerAuthConfig:
    """Validated static bearer configuration for the configured HTTPS resource."""

    resource_url: str
    tokens: tuple[BearerTokenEntry, ...]

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> RemoteBearerAuthConfig:
        """Load bearer token identities without retaining or exposing token text."""
        values = os.environ if environ is None else environ
        resource = values.get(RESOURCE_ENV, "").strip()
        if not resource:
            raise RemoteAuthConfigurationError(f"Remote bearer auth requires {RESOURCE_ENV}")
        validate_remote_resource_url(resource)

        encoded_entries = values.get(BEARER_TOKENS_ENV, "")
        if not encoded_entries:
            raise RemoteAuthConfigurationError(f"Remote bearer auth requires {BEARER_TOKENS_ENV}")
        try:
            raw_entries = json.loads(encoded_entries)
        except (json.JSONDecodeError, TypeError):
            raise RemoteAuthConfigurationError(
                f"{BEARER_TOKENS_ENV} must be a JSON array of token entries"
            ) from None
        if not isinstance(raw_entries, list) or not raw_entries:
            raise RemoteAuthConfigurationError(
                f"{BEARER_TOKENS_ENV} must be a non-empty JSON array of token entries"
            )

        tokens: list[BearerTokenEntry] = []
        identities: set[str] = set()
        digests: set[bytes] = set()
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                raise RemoteAuthConfigurationError("Each bearer token entry must be a JSON object")
            identity = raw_entry.get("identity")
            token = raw_entry.get("token")
            raw_scopes = raw_entry.get("scopes")
            if (
                not isinstance(identity, str)
                or not identity.strip()
                or identity != identity.strip()
            ):
                raise RemoteAuthConfigurationError(
                    "Each bearer token entry requires a non-empty identity"
                )
            if identity in identities:
                raise RemoteAuthConfigurationError("Bearer token identities must be unique")
            if (
                not isinstance(token, str)
                or len(token) < 32
                or re.fullmatch(r"[A-Za-z0-9._~+/-]+={0,}", token) is None
            ):
                raise RemoteAuthConfigurationError(
                    "Each bearer token must be at least 32 RFC 6750 b64token characters"
                )
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            if digest in digests:
                raise RemoteAuthConfigurationError("Bearer tokens must be unique")
            if not isinstance(raw_scopes, list) or not raw_scopes or any(
                not isinstance(scope, str) for scope in raw_scopes
            ):
                raise RemoteAuthConfigurationError("Each bearer token entry requires a scope array")
            scopes = frozenset(raw_scopes)
            if scopes.difference(SUPPORTED_SCOPES):
                raise RemoteAuthConfigurationError(
                    "Bearer token entry contains an unsupported scope"
                )
            if READ_SCOPE not in scopes:
                raise RemoteAuthConfigurationError(
                    "Every bearer token entry must include the jamf:read scope"
                )
            if len(scopes) != len(raw_scopes):
                raise RemoteAuthConfigurationError("Bearer token scopes must be unique")

            identities.add(identity)
            digests.add(digest)
            tokens.append(BearerTokenEntry(identity, digest, scopes))

        return cls(resource_url=resource, tokens=tuple(tokens))


class BearerAuthSettings(AuthSettings):
    """SDK auth settings for tokens without an OAuth authorization server.

    The SDK requires an auth settings object to install its official TokenVerifier
    middleware. Leaving both issuer and SDK resource metadata unset prevents it
    from publishing OAuth protected-resource metadata for this mode. The verifier
    itself binds each accepted token to the separately validated HTTPS resource.
    """

    issuer_url: AnyHttpUrl | None = None
    resource_server_url: AnyHttpUrl | None = None


class StaticBearerTokenVerifier(TokenVerifier):
    """Verify configured opaque bearer tokens with constant-time digest checks."""

    def __init__(self, config: RemoteBearerAuthConfig) -> None:
        self.resource_url = config.resource_url
        self._tokens = config.tokens

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return the configured identity and scopes for a matching token."""
        if not isinstance(token, str):
            return None
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        matched: BearerTokenEntry | None = None
        for entry in self._tokens:
            # Scan the full token set and compare fixed-size digests so token
            # contents and their configured length do not affect comparison time.
            if hmac.compare_digest(digest, entry.token_digest):
                matched = entry
        if matched is None:
            return None
        return AccessToken(
            token=token,
            client_id=matched.identity,
            subject=matched.identity,
            scopes=sorted(matched.scopes),
            resource=self.resource_url,
            claims={"auth_mode": "bearer"},
        )


def _validate_https_url(value: str, setting_name: str) -> None:
    """Reject insecure, credential-bearing, or ambiguous configured URLs.

    Args:
        value: URL value to validate.
        setting_name: Environment variable or metadata field name for errors.
    """
    try:
        parsed = urlsplit(value)
        parsed.port  # Force urllib to reject malformed and out-of-range ports.
        TypeAdapter(AnyHttpUrl).validate_python(value)
        invalid = (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        )
    except (TypeError, ValueError):
        invalid = True
    if invalid:
        raise RemoteAuthConfigurationError(
            f"{setting_name} must be an HTTPS URL without credentials, query, or fragment"
        )


class JwtJwksTokenVerifier(TokenVerifier):
    """Validate RS256 JWT access tokens using issuer metadata and its JWKS.

    Metadata and keys are fetched lazily and cached briefly. A caller may pass
    an ``httpx.AsyncClient`` for offline tests or application-managed transport;
    ownership of that client remains with the caller.
    """

    def __init__(
        self,
        config: RemoteAuthConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
        cache_ttl_seconds: int = 300,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.config = config
        self._http_client = http_client
        self._cache_ttl_seconds = max(1, cache_ttl_seconds)
        self._timeout_seconds = timeout_seconds
        self._metadata: dict[str, Any] | None = None
        self._metadata_expires_at = 0.0
        self._jwks: dict[str, dict[str, Any]] = {}
        self._jwks_expires_at = 0.0
        import asyncio

        self._metadata_lock = asyncio.Lock()
        self._jwks_lock = asyncio.Lock()

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return verified caller identity and Jamf scopes, or ``None``."""
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                return None
            jwk = await self._get_key(header["kid"])
            if jwk is None:
                return None

            claims = jwt.decode(
                token,
                key=jwt.PyJWK.from_dict(jwk, algorithm="RS256").key,
                algorithms=["RS256"],
                audience=self.config.audience,
                issuer=self.config.issuer_url,
                options={
                    "require": ["exp", "iss", "aud"],
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                    "verify_nbf": True,
                },
            )
            scopes = _parse_scopes(claims)
            if scopes is None:
                return None

            client_id = _first_string_claim(claims, "client_id", "azp", "sub")
            if client_id is None:
                return None
            subject = claims.get("sub")
            expires_at = claims["exp"]
            if not isinstance(expires_at, (int, float)):
                return None

            # The JWT audience check above binds the token to this configured
            # resource (or its deliberately configured provider identifier).
            # Report the canonical resource URL to the SDK's resource check.
            return AccessToken(
                token=token,
                client_id=client_id,
                subject=subject if isinstance(subject, str) else None,
                scopes=sorted(scopes),
                expires_at=int(expires_at),
                resource=self.config.resource_url,
                claims=claims,
            )
        except (jwt.PyJWTError, httpx.HTTPError, ValueError, TypeError, KeyError) as error:
            logger.debug("Remote OAuth token verification failed: %s", error)
            return None

    async def _get_key(self, kid: str) -> dict[str, Any] | None:
        now = time.monotonic()
        if now >= self._jwks_expires_at:
            async with self._jwks_lock:
                if time.monotonic() >= self._jwks_expires_at:
                    try:
                        metadata = await self._get_metadata()
                        jwks_url = _metadata_https_url(metadata.get("jwks_uri"), "jwks_uri")
                        document = await self._get_json(jwks_url)
                        keys = document.get("keys")
                        if not isinstance(keys, list):
                            raise ValueError("JWKS document has no keys array")
                        selected_keys: dict[str, dict[str, Any]] = {}
                        for key in keys:
                            if not _is_acceptable_jwk(key) or not isinstance(key.get("kid"), str):
                                continue
                            if key["kid"] in selected_keys:
                                raise ValueError("JWKS contains duplicate signing key identifiers")
                            selected_keys[key["kid"]] = key
                        self._jwks = selected_keys
                        self._jwks_expires_at = time.monotonic() + self._cache_ttl_seconds
                    except (httpx.HTTPError, ValueError, TypeError) as error:
                        logger.warning("Could not load trusted OAuth signing keys: %s", error)
                        self._jwks = {}
                        self._jwks_expires_at = time.monotonic() + min(self._cache_ttl_seconds, 15)
        return self._jwks.get(kid)

    async def _get_metadata(self) -> dict[str, Any]:
        if self._metadata is not None and time.monotonic() < self._metadata_expires_at:
            return self._metadata

        async with self._metadata_lock:
            if self._metadata is not None and time.monotonic() < self._metadata_expires_at:
                return self._metadata
            failures: list[str] = []
            for metadata_url in _metadata_discovery_urls(self.config.issuer_url):
                try:
                    metadata = await self._get_json(metadata_url)
                except httpx.HTTPStatusError as error:
                    failures.append(f"{metadata_url} returned HTTP {error.response.status_code}")
                    continue
                except httpx.HTTPError as error:
                    failures.append(f"{metadata_url} could not be fetched ({type(error).__name__})")
                    continue

                if metadata.get("issuer") != self.config.issuer_url:
                    raise ValueError(
                        "Issuer metadata does not exactly match the configured issuer URL"
                    )
                _metadata_https_url(metadata.get("jwks_uri"), "jwks_uri")
                self._metadata = metadata
                self._metadata_expires_at = time.monotonic() + self._cache_ttl_seconds
                return metadata

            raise ValueError("Could not discover issuer metadata: " + "; ".join(failures))

    async def _get_json(self, url: str) -> dict[str, Any]:
        if self._http_client is None:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = await client.get(url)
        else:
            response = await self._http_client.get(
                url,
                timeout=self._timeout_seconds,
                follow_redirects=False,
            )
        response.raise_for_status()
        document = response.json()
        if not isinstance(document, dict):
            raise ValueError(f"Expected a JSON object from {url}")
        return document


def _metadata_https_url(value: object, field_name: str) -> str:
    """Validate and return an HTTPS URL supplied by trusted issuer metadata.

    Args:
        value: Metadata field value.
        field_name: Metadata field name used in validation errors.

    Returns:
        The validated URL string.
    """
    if not isinstance(value, str):
        raise ValueError(f"Issuer metadata is missing {field_name}")
    _validate_https_url(value, field_name)
    return value


def _metadata_discovery_urls(issuer_url: str) -> tuple[str, str]:
    """Build OIDC and RFC 8414 metadata URLs for an issuer.

    Args:
        issuer_url: Configured, validated issuer URL.

    Returns:
        OIDC discovery URL followed by RFC 8414 authorization-server metadata URL.
    """
    parsed = urlsplit(issuer_url)
    path = parsed.path.rstrip("/")
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    issuer_base = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    oidc_url = f"{issuer_base}/.well-known/openid-configuration"
    rfc8414_path = f"/.well-known/oauth-authorization-server{path}"
    rfc8414_url = f"{origin}{rfc8414_path}"
    return oidc_url, rfc8414_url


def _is_acceptable_jwk(value: object) -> bool:
    """Return whether a JWK is eligible for the pinned RS256 signature check.

    Args:
        value: Candidate key from the issuer JWKS.
    """
    if not isinstance(value, dict):
        return False
    if value.get("kty") != "RSA" or value.get("use") not in (None, "sig"):
        return False
    if value.get("alg") not in (None, "RS256"):
        return False
    key_ops = value.get("key_ops")
    return key_ops is None or (isinstance(key_ops, list) and "verify" in key_ops)


def _parse_scopes(claims: Mapping[str, Any]) -> set[str] | None:
    """Parse recognized Jamf OAuth scopes from a verified JWT payload.

    Args:
        claims: JWT claims after cryptographic and standard-claim validation.

    Returns:
        Supported scopes, or ``None`` for a malformed scope claim.
    """
    raw_scopes = claims.get("scope", claims.get("scp", []))
    if isinstance(raw_scopes, str):
        scopes = raw_scopes.split()
    elif isinstance(raw_scopes, list) and all(isinstance(scope, str) for scope in raw_scopes):
        scopes = raw_scopes
    else:
        return None
    return set(scopes) & SUPPORTED_SCOPES


def _first_string_claim(claims: Mapping[str, Any], *names: str) -> str | None:
    """Return the first non-empty string identity claim.

    Args:
        claims: Verified JWT claims.
        *names: Claim names in precedence order.

    Returns:
        A claim string, or ``None`` if no usable identity claim exists.
    """
    for name in names:
        value = claims.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def build_remote_auth(
    environ: Mapping[str, str] | None = None,
) -> tuple[AuthSettings, TokenVerifier]:
    """Build SDK auth settings and a verifier for the selected remote mode.

    OAuth remains the default and uses an external issuer. Explicit bearer mode
    uses configured opaque tokens and intentionally publishes no OAuth metadata.
    """
    values = os.environ if environ is None else environ
    if remote_auth_mode_from_env(values) == "bearer":
        config = RemoteBearerAuthConfig.from_env(values)
        auth = BearerAuthSettings(
            issuer_url=None,
            resource_server_url=None,
            required_scopes=[READ_SCOPE],
            validate_token_resource=False,
        )
        return auth, StaticBearerTokenVerifier(config)

    config = RemoteAuthConfig.from_env(environ)
    auth = AuthSettings(
        issuer_url=config.issuer_url,
        resource_server_url=config.resource_url,
        # The SDK applies these at its HTTP route. Per-tool middleware adds
        # write/admin requirements for calls that need broader access.
        required_scopes=[READ_SCOPE],
        validate_token_resource=True,
    )
    return auth, JwtJwksTokenVerifier(config)


def build_remote_tool_scope_map() -> Mapping[str, frozenset[str]]:
    """Derive tool scopes from the existing registry's read-only annotations.

    Every registered tool must have a scope policy or remote startup fails.
    Unknown request names are left to the SDK's protocol validation.
    """
    from .tools import get_registered_tools
    from .tools._registry import get_tool_annotations

    scopes: dict[str, frozenset[str]] = {}
    for function, _tool_type in get_registered_tools():
        name = function.__name__
        if name in REMOTE_DISABLED_TOOL_NAMES:
            continue
        annotation = get_tool_annotations(function)
        read_only = getattr(annotation, "read_only_hint", None)
        if name in ADMIN_TOOL_NAMES:
            scopes[name] = frozenset({READ_SCOPE, WRITE_SCOPE, ADMIN_SCOPE})
        elif read_only is True:
            scopes[name] = frozenset({READ_SCOPE})
        elif read_only is False:
            scopes[name] = frozenset({READ_SCOPE, WRITE_SCOPE})
        else:
            raise RemoteAuthConfigurationError(
                f"Remote tool {name!r} has no registered read-only/write authorization annotation"
            )
    return MappingProxyType(scopes)


def required_scopes_for_tool(tool_name: str) -> frozenset[str] | None:
    """Return the remote authorization scopes required by a registered tool.

    Args:
        tool_name: Exact MCP tool name.

    Returns:
        Required scopes, or ``None`` when the tool is unregistered or unannotated.
    """
    return build_remote_tool_scope_map().get(tool_name)


def get_remote_resource_url(server: Any) -> str:
    """Return the configured HTTPS resource URL for either remote auth mode."""
    verifier = getattr(server, "_token_verifier", None)
    if isinstance(verifier, StaticBearerTokenVerifier):
        return verifier.resource_url
    auth = getattr(getattr(server, "settings", None), "auth", None)
    resource_url = getattr(auth, "resource_server_url", None)
    if resource_url is None:
        raise RemoteAuthConfigurationError(
            "The remote HTTP app requires a configured HTTPS resource URL"
        )
    return str(resource_url)


def build_remote_http_app(
    server: Any,
    *,
    tool_scopes: Mapping[str, Sequence[str]] | None = None,
    **app_options: Any,
) -> Starlette:
    """Build the SDK Streamable HTTP app with complete scope metadata.

    OAuth mode advertises ``jamf:read`` as the initial admission scope and
    enforces broader per-tool scopes before dispatch. Static bearer mode uses
    the SDK token-verifier middleware without publishing OAuth metadata.
    """
    auth = getattr(getattr(server, "settings", None), "auth", None)
    verifier = getattr(server, "_token_verifier", None)
    bearer_mode = isinstance(verifier, StaticBearerTokenVerifier)
    if auth is None:
        raise RemoteAuthConfigurationError(
            "The remote HTTP app requires MCPServer with configured authentication"
        )

    if not bearer_mode:
        if auth.issuer_url is None or auth.resource_server_url is None:
            raise RemoteAuthConfigurationError(
                "The remote OAuth HTTP app requires external issuer and resource settings"
            )
    resource_url = get_remote_resource_url(server)

    resource_path = urlsplit(resource_url).path or "/"
    requested_path = app_options.pop("streamable_http_path", resource_path)
    if requested_path != resource_path:
        raise RemoteAuthConfigurationError(
            "streamable_http_path must match the path in JAMF_MCP_RESOURCE_URL"
        )
    configured_transport_security = app_options.get("transport_security")
    resource_parts = urlsplit(resource_url)
    resource_host = resource_parts.netloc
    resource_origin = urlunsplit((resource_parts.scheme, resource_host, "", "", ""))
    if configured_transport_security is None:
        app_options["transport_security"] = TransportSecuritySettings(
            allowed_hosts=[resource_host],
            allowed_origins=[resource_origin],
        )
    elif configured_transport_security.enable_dns_rebinding_protection:
        app_options["transport_security"] = configured_transport_security.model_copy(
            update={
                "allowed_hosts": sorted(
                    set(configured_transport_security.allowed_hosts) | {resource_host}
                ),
                "allowed_origins": sorted(
                    set(configured_transport_security.allowed_origins) | {resource_origin}
                ),
            }
        )
    app = server.streamable_http_app(streamable_http_path=resource_path, **app_options)
    metadata_url: str | None = None
    if not bearer_mode:
        metadata_url = str(build_resource_metadata_url(auth.resource_server_url))
        metadata_path = urlsplit(metadata_url).path
        routes = [
            route for route in app.router.routes if getattr(route, "path", None) != metadata_path
        ]
        routes.extend(
            create_protected_resource_routes(
                resource_url=auth.resource_server_url,
                authorization_servers=[auth.issuer_url],
                scopes_supported=[READ_SCOPE],
            )
        )
        app.router.routes[:] = routes

    # Insert after the SDK authentication and auth-context middleware. This
    # layer sees only the SDK's verified AuthenticatedUser and can reject an
    # insufficiently scoped HTTP request before dispatching any tool handler.
    auth_context_index = next(
        (
            index
            for index, middleware in enumerate(app.user_middleware)
            if middleware.cls is AuthContextMiddleware
        ),
        None,
    )
    if auth_context_index is None:
        raise RemoteAuthConfigurationError(
            "The MCP SDK HTTP app did not install its authentication context middleware"
        )
    scope_map = build_remote_tool_scope_map() if tool_scopes is None else tool_scopes
    max_body_bytes = int(app_options.get("max_request_body_size", 4 * 1024 * 1024))
    app.user_middleware.insert(
        auth_context_index + 1,
        Middleware(
            RemoteScopeHTTPMiddleware,
            tool_scopes=scope_map,
            resource_metadata_url=metadata_url,
            mcp_path=resource_path,
            max_body_bytes=max_body_bytes,
        ),
    )
    app.middleware_stack = None
    return app


class RemoteToolScopeMiddleware:
    """Require registered Jamf scopes for each authenticated ``tools/call``."""

    def __init__(
        self,
        tool_scopes: Mapping[str, Sequence[str]] | None = None,
        *,
        resource_metadata_url: str | None = None,
        advertise_security_schemes: bool = True,
    ) -> None:
        self.tool_scopes = (
            build_remote_tool_scope_map()
            if tool_scopes is None
            else MappingProxyType({name: frozenset(value) for name, value in tool_scopes.items()})
        )
        self.resource_metadata_url = resource_metadata_url
        self.advertise_security_schemes = advertise_security_schemes

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        """Apply per-tool scopes and optionally publish OAuth security metadata."""
        if ctx.method == "tools/list":
            result = await call_next(ctx)
            return _apply_wire_security_schemes(
                result, self.tool_scopes, advertise_oauth=self.advertise_security_schemes
            )
        if ctx.method != "tools/call":
            return await call_next(ctx)

        params = ctx.params or {}
        from .tools._registry import require_known_tool_name

        tool_name = require_known_tool_name(params, frozenset(self.tool_scopes))
        required = self.tool_scopes[tool_name]
        access_token = get_access_token()
        if access_token is None:
            return _tool_denial(
                "Remote access denied: a verified bearer token is required.",
                error="invalid_token",
                resource_metadata_url=self.resource_metadata_url,
            )
        missing = required.difference(access_token.scopes)
        if missing:
            return _tool_denial(
                "Remote access denied: missing required scope(s): " + ", ".join(sorted(missing)),
                resource_metadata_url=self.resource_metadata_url,
                required_scopes=required,
            )
        return await call_next(ctx)


class RemoteScopeHTTPMiddleware:
    """Return HTTP 403 with a bearer challenge before dispatching denied calls."""

    def __init__(
        self,
        app: Any,
        *,
        tool_scopes: Mapping[str, Sequence[str]],
        resource_metadata_url: str | None,
        mcp_path: str,
        max_body_bytes: int,
    ) -> None:
        self.app = app
        self.tool_scopes = tool_scopes
        self.resource_metadata_url = resource_metadata_url
        self.mcp_path = mcp_path
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """Inspect authenticated MCP requests and enforce HTTP-level scope errors."""
        if scope.get("type") != "http" or scope.get("path") != self.mcp_path:
            await self.app(scope, receive, send)
            return

        user = scope.get("user")
        if not isinstance(user, AuthenticatedUser):
            await _send_http_error(
                send,
                status_code=401,
                error="invalid_token",
                description="A valid bearer token is required.",
                required_scopes=frozenset({READ_SCOPE}),
                resource_metadata_url=self.resource_metadata_url,
            )
            return

        scopes = set(user.scopes)
        if scope.get("method") != "POST":
            if READ_SCOPE not in scopes:
                await self._send_scope_error(send, frozenset({READ_SCOPE}))
                return
            await self.app(scope, receive, send)
            return

        body, disconnected, oversized = await self._read_body(receive)
        if disconnected:
            return
        if oversized:
            await _send_http_error(
                send,
                status_code=413,
                error="request_too_large",
                description="MCP request exceeds the configured body size limit.",
            )
            return

        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            payload = None
        tool_calls = _requested_tool_calls(payload)
        if READ_SCOPE not in scopes:
            for request_id, tool_name in tool_calls:
                required = self.tool_scopes.get(tool_name) if tool_name is not None else None
                if required is not None and request_id is not None:
                    await self._send_scope_error(
                        send,
                        frozenset(required),
                        request_id=request_id,
                    )
                    return
            await self._send_scope_error(send, frozenset({READ_SCOPE}))
            return

        for request_id, tool_name in tool_calls:
            required = self.tool_scopes.get(tool_name) if tool_name is not None else None
            if required is None:
                # The SDK owns method/name validation. Only policy-check a
                # registered operation, so typos do not trigger OAuth consent.
                continue
            if not set(required).issubset(scopes):
                if request_id is None:
                    # The SDK's JSON-RPC parser will report a malformed request.
                    continue
                await self._send_scope_error(
                    send,
                    frozenset(required),
                    request_id=request_id,
                )
                return

        replayed = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _read_body(self, receive: Any) -> tuple[bytes, bool, bool]:
        """Buffer an HTTP body for safe tool-name inspection and replay.

        Args:
            receive: Original ASGI receive callable.

        Returns:
            Buffered bytes, whether the request disconnected, and whether the
            body exceeded the configured limit.
        """
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return b"", True, False
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if size + len(chunk) > self.max_body_bytes:
                # Do not retain or join an attacker-controlled oversized body.
                return b"", False, True
            chunks.append(chunk)
            size += len(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks), False, False

    async def _send_scope_error(
        self,
        send: Any,
        required_scopes: frozenset[str],
        *,
        request_id: str | int | None = None,
    ) -> None:
        """Send a 403 response with the complete required scope set."""
        await _send_http_error(
            send,
            status_code=403,
            error="insufficient_scope",
            description="The access token lacks scope required for this MCP operation.",
            required_scopes=required_scopes,
            resource_metadata_url=self.resource_metadata_url,
            request_id=request_id,
        )


def _requested_tool_calls(payload: object) -> list[tuple[str | int | None, str | None]]:
    """Extract call IDs and tool names from one JSON-RPC message or a batch.

    Args:
        payload: Parsed HTTP request body.

    Returns:
        Call IDs and names; ``None`` marks malformed IDs or call parameters.
    """
    messages = payload if isinstance(payload, list) else [payload]
    calls: list[tuple[str | int | None, str | None]] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("method") != "tools/call":
            continue
        params = message.get("params")
        name = params.get("name") if isinstance(params, dict) else None
        request_id = message.get("id")
        if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
            request_id = None
        calls.append((request_id, name if isinstance(name, str) else None))
    return calls


def _apply_wire_security_schemes(
    result: HandlerResult,
    tool_scopes: Mapping[str, Sequence[str]],
    *,
    advertise_oauth: bool,
) -> HandlerResult:
    """Apply auth-mode declarations while preserving SDK tool metadata.

    MCP SDK 2.3 models tool ``_meta`` but not the newer top-level
    ``securitySchemes`` field. Returning a plain dictionary lets the SDK emit
    both forms on the wire without patching its models.

    Args:
        result: The SDK's tools/list result.
        tool_scopes: Exact authorization policy for registered tools.
        advertise_oauth: Add OAuth declarations, or remove them for bearer mode.

    Returns:
        A JSON-compatible tools/list result for the selected authentication mode.
    """
    if hasattr(result, "model_dump"):
        payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    elif isinstance(result, dict):
        payload = deepcopy(result)
    else:
        return result
    if not isinstance(payload, dict) or not isinstance(payload.get("tools"), list):
        return payload

    visible_tools: list[dict[str, Any]] = []
    for tool in payload["tools"]:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        required = tool_scopes.get(name) if isinstance(name, str) else None
        if required is None:
            # Do not advertise tools without an explicit authorization policy.
            continue
        if advertise_oauth:
            security_schemes = [{"type": "oauth2", "scopes": sorted(required)}]
            tool["securitySchemes"] = security_schemes
            metadata = tool.setdefault("_meta", {})
            if isinstance(metadata, dict):
                metadata["securitySchemes"] = security_schemes
        else:
            tool.pop("securitySchemes", None)
            metadata = tool.get("_meta")
            if isinstance(metadata, dict):
                metadata.pop("securitySchemes", None)
        visible_tools.append(tool)
    payload["tools"] = visible_tools
    return payload


def _tool_denial(
    message: str,
    *,
    error: str = "insufficient_scope",
    resource_metadata_url: str | None = None,
    required_scopes: frozenset[str] = frozenset(),
) -> CallToolResult:
    """Build an MCP tool error with the challenge OpenAI clients inspect.

    Args:
        message: User-visible authorization explanation.
        error: OAuth error code for the challenge.
        resource_metadata_url: Protected resource metadata discovery URL.
        required_scopes: Full scope set required to call this tool.

    Returns:
        An error-marked MCP result containing ``mcp/www_authenticate`` metadata.
    """
    challenge = _format_bearer_challenge(
        error,
        message,
        required_scopes=required_scopes,
        resource_metadata_url=resource_metadata_url,
    )
    return CallToolResult(
        content=[TextContent(type="text", text=message)],
        is_error=True,
        meta={"mcp/www_authenticate": [challenge]} if resource_metadata_url else None,
    )


async def _send_http_error(
    send: Any,
    *,
    status_code: int,
    error: str,
    description: str,
    required_scopes: frozenset[str] = frozenset(),
    resource_metadata_url: str | None = None,
    request_id: str | int | None = None,
) -> None:
    """Write an HTTP authorization error and RFC 6750 bearer challenge.

    If ``request_id`` is present, the body is also a JSON-RPC tool error result
    with ``mcp/www_authenticate`` metadata for Apps SDK clients.
    """
    challenge = _format_bearer_challenge(
        error,
        description,
        required_scopes=required_scopes,
        resource_metadata_url=resource_metadata_url,
    )
    if request_id is None:
        payload: dict[str, Any] = {"error": error, "error_description": description}
    else:
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": description}],
                "isError": True,
                "resultType": "complete",
            },
        }
        if resource_metadata_url:
            payload["result"]["_meta"] = {"mcp/www_authenticate": [challenge]}
    body = json.dumps(payload).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", challenge.encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _format_bearer_challenge(
    error: str,
    description: str,
    *,
    required_scopes: frozenset[str] = frozenset(),
    resource_metadata_url: str | None = None,
) -> str:
    """Format an RFC 6750 bearer challenge with MCP resource discovery data."""
    fields = [f'error="{error}"', f'error_description="{_escape_quoted_value(description)}"']
    if required_scopes:
        fields.append(f'scope="{" ".join(sorted(required_scopes))}"')
    if resource_metadata_url:
        fields.append(f'resource_metadata="{_escape_quoted_value(resource_metadata_url)}"')
    return "Bearer " + ", ".join(fields)


def _escape_quoted_value(value: str) -> str:
    """Escape a value embedded in a quoted WWW-Authenticate parameter."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
