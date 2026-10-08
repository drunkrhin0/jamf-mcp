# Copyright 2026, Jamf Software LLC
"""Jamf Pro API Client.

Provides a unified interface for both Classic API and Jamf Pro API (v1/v2).
Handles authentication, request formatting, and response parsing.
"""

import logging
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

from .auth import JamfAuth

logger = logging.getLogger(__name__)


def dict_to_xml(data: dict) -> str:
    """Convert a dictionary to XML string for Jamf Classic API.

    The Classic API expects XML payloads, not JSON.
    Example: {"computer_group": {"name": "Test", "is_smart": True}}
    becomes: <computer_group><name>Test</name><is_smart>true</is_smart></computer_group>
    """
    def _convert(d: dict, parent: ET.Element) -> None:
        for key, value in d.items():
            if isinstance(value, dict):
                child = ET.SubElement(parent, key)
                _convert(value, child)
            elif isinstance(value, list):
                # For lists, create a container element and child elements
                container = ET.SubElement(parent, key)
                # Determine singular name for list items
                singular_map = {
                    "criteria": "criterion",
                    "computers": "computer",
                    "mobile_devices": "mobile_device",
                }
                item_name = singular_map.get(key, key.rstrip('s') if key.endswith('s') else key)
                for item in value:
                    if isinstance(item, dict):
                        item_elem = ET.SubElement(container, item_name)
                        _convert(item, item_elem)
                    else:
                        item_elem = ET.SubElement(container, item_name)
                        item_elem.text = str(item)
            elif isinstance(value, bool):
                child = ET.SubElement(parent, key)
                child.text = str(value).lower()
            elif value is not None:
                child = ET.SubElement(parent, key)
                child.text = str(value)

    # Get the root element name from the data
    if len(data) == 1:
        root_name = list(data.keys())[0]
        root = ET.Element(root_name)
        _convert(data[root_name], root)
    else:
        root = ET.Element("root")
        _convert(data, root)

    return ET.tostring(root, encoding='unicode')


class JamfAPIError(Exception):
    """Raised when a Jamf API request fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class JamfClient:
    """Client for interacting with Jamf Pro APIs.

    Supports both the Classic API (/JSSResource) and the Jamf Pro API (/api/v1, /api/v2).
    Automatically handles authentication and token refresh.
    """

    # Default timeout for API requests (in seconds)
    DEFAULT_TIMEOUT = 30.0

    def __init__(self, auth: JamfAuth, timeout: float = DEFAULT_TIMEOUT):
        """Initialize Jamf API client.

        Args:
            auth: JamfAuth instance for handling authentication
            timeout: Request timeout in seconds
        """
        self.auth = auth
        self.base_url = auth.base_url
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    @classmethod
    def from_env(cls, timeout: float = DEFAULT_TIMEOUT) -> "JamfClient":
        """Create JamfClient from environment variables.

        Args:
            timeout: Request timeout in seconds

        Returns:
            Configured JamfClient instance
        """
        auth = JamfAuth.from_env()
        return cls(auth=auth, timeout=timeout)

    @asynccontextmanager
    async def _get_client(self):
        """Get or create HTTP client as async context manager.

        Yields:
            httpx.AsyncClient instance
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)

        try:
            yield self._client
        except Exception:
            raise

    async def close(self):
        """Close the HTTP client and invalidate token."""
        if self._client:
            async with self._get_client() as client:
                await self.auth.invalidate_token(client)
            await self._client.aclose()
            self._client = None

    async def _get_headers(self, client: httpx.AsyncClient, accept: str = "application/json") -> dict:
        """Get request headers with authentication.

        Args:
            client: HTTP client for token requests
            accept: Accept header value

        Returns:
            Dict of headers including Authorization
        """
        token = await self.auth.get_token(client)
        return {
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
        accept: str = "application/json",
    ) -> Any:
        """Make an authenticated request to the Jamf API.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            endpoint: API endpoint path (e.g., /api/v1/computers)
            data: Request body data (for POST, PUT, PATCH)
            params: Query parameters
            accept: Accept header value

        Returns:
            Parsed JSON response or raw text for non-JSON responses

        Raises:
            JamfAPIError: If the request fails
        """
        url = urljoin(self.base_url, endpoint)

        async with self._get_client() as client:
            headers = await self._get_headers(client, accept=accept)

            try:
                response = await client.request(
                    method=method,
                    url=url,
                    json=data if data else None,
                    params=params,
                    headers=headers,
                )

                # Log request details for debugging
                logger.debug(
                    "%s %s -> %d",
                    method,
                    endpoint,
                    response.status_code,
                )

                response.raise_for_status()

                # Try to parse JSON, fall back to text
                # Note: Classic API may return JSON with text/plain content-type
                content_type = response.headers.get("content-type", "")
                if content_type.startswith("application/json"):
                    return response.json()

                # Try parsing as JSON even for other content types (e.g., text/plain)
                if response.text:
                    try:
                        return response.json()
                    except Exception:
                        pass

                return response.text

            except httpx.HTTPStatusError as e:
                logger.error(
                    "API request failed: %s %s -> %d",
                    method,
                    endpoint,
                    e.response.status_code,
                )
                error_body = e.response.text
                raise JamfAPIError(
                    f"Jamf API error: {e.response.status_code}",
                    status_code=e.response.status_code,
                    response_body=error_body,
                ) from e
            except httpx.RequestError as e:
                logger.error("Request error: %s", type(e).__name__)
                raise JamfAPIError(f"Request failed: {str(e)}") from e

    # ==========================================================================
    # Classic API Methods (/JSSResource)
    # ==========================================================================

    async def classic_get(
        self,
        resource: str,
        resource_id: Optional[int] = None,
    ) -> dict:
        """GET request to Classic API.

        Args:
            resource: Resource type (e.g., "computers", "mobiledevices")
            resource_id: Optional resource ID for single item retrieval

        Returns:
            Parsed JSON response
        """
        if resource_id:
            endpoint = f"/JSSResource/{resource}/id/{resource_id}"
        else:
            endpoint = f"/JSSResource/{resource}"

        return await self._request("GET", endpoint)

    async def classic_post(self, resource: str, data: dict) -> dict:
        """POST request to Classic API (create).

        Args:
            resource: Resource type
            data: Resource data to create (will be converted to XML)

        Returns:
            Parsed JSON response
        """
        endpoint = f"/JSSResource/{resource}/id/0"
        return await self._classic_xml_request("POST", endpoint, data)

    async def classic_put(self, resource: str, resource_id: int, data: dict) -> dict:
        """PUT request to Classic API (update).

        Args:
            resource: Resource type
            resource_id: ID of resource to update
            data: Updated resource data (will be converted to XML)

        Returns:
            Parsed JSON response
        """
        endpoint = f"/JSSResource/{resource}/id/{resource_id}"
        return await self._classic_xml_request("PUT", endpoint, data)

    async def _classic_xml_request(
        self,
        method: str,
        endpoint: str,
        data: dict,
    ) -> Any:
        """Make an XML request to the Classic API.

        Classic API requires XML for POST/PUT operations.

        Args:
            method: HTTP method (POST, PUT)
            endpoint: API endpoint path
            data: Request body data (will be converted to XML)

        Returns:
            Parsed JSON response

        Raises:
            JamfAPIError: If the request fails
        """
        url = urljoin(self.base_url, endpoint)
        xml_content = dict_to_xml(data)

        async with self._get_client() as client:
            headers = await self._get_headers(client, accept="application/json")
            headers["Content-Type"] = "application/xml"

            try:
                response = await client.request(
                    method=method,
                    url=url,
                    content=xml_content,
                    headers=headers,
                )

                logger.debug(
                    "%s %s (XML) -> %d",
                    method,
                    endpoint,
                    response.status_code,
                )

                response.raise_for_status()

                # Classic API may return XML even when we request JSON
                # Try to parse as JSON first
                if response.text:
                    try:
                        return response.json()
                    except Exception:
                        # Parse XML response
                        return self._parse_xml_response(response.text)

                return {}

            except httpx.HTTPStatusError as e:
                logger.error(
                    "Classic API request failed: %s %s -> %d",
                    method,
                    endpoint,
                    e.response.status_code,
                )
                error_body = e.response.text
                raise JamfAPIError(
                    f"Jamf Classic API error: {e.response.status_code}",
                    status_code=e.response.status_code,
                    response_body=error_body,
                ) from e
            except httpx.RequestError as e:
                logger.error("Classic API request error: %s", type(e).__name__)
                raise JamfAPIError(f"Request error: {str(e)}") from e

    def _parse_xml_response(self, xml_text: str) -> dict:
        """Parse XML response from Classic API into a dict.

        Handles simple XML responses like: <computer_group><id>123</id></computer_group>
        """
        try:
            root = ET.fromstring(xml_text)
            result = {}
            for child in root:
                if child.text:
                    try:
                        result[child.tag] = int(child.text)
                    except ValueError:
                        result[child.tag] = child.text
            return result
        except Exception:
            return {"raw": xml_text}

    # ==========================================================================
    # Jamf Pro API v1 Methods
    # ==========================================================================

    async def v1_get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """GET request to Jamf Pro API v1.

        Args:
            endpoint: Endpoint path (without /api/v1 prefix)
            params: Query parameters

        Returns:
            Parsed JSON response
        """
        full_endpoint = f"/api/v1/{endpoint.lstrip('/')}"
        return await self._request("GET", full_endpoint, params=params)

    async def v1_post(self, endpoint: str, data: dict) -> Any:
        """POST request to Jamf Pro API v1.

        Args:
            endpoint: Endpoint path (without /api/v1 prefix)
            data: Request body data

        Returns:
            Parsed JSON response
        """
        full_endpoint = f"/api/v1/{endpoint.lstrip('/')}"
        return await self._request("POST", full_endpoint, data=data)

    async def v1_patch(self, endpoint: str, data: dict) -> Any:
        """PATCH request to Jamf Pro API v1.

        Args:
            endpoint: Endpoint path (without /api/v1 prefix)
            data: Request body data

        Returns:
            Parsed JSON response
        """
        full_endpoint = f"/api/v1/{endpoint.lstrip('/')}"
        return await self._request("PATCH", full_endpoint, data=data)

    # ==========================================================================
    # Jamf Pro API v2 Methods
    # ==========================================================================

    async def v2_get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """GET request to Jamf Pro API v2.

        Args:
            endpoint: Endpoint path (without /api/v2 prefix)
            params: Query parameters

        Returns:
            Parsed JSON response
        """
        full_endpoint = f"/api/v2/{endpoint.lstrip('/')}"
        return await self._request("GET", full_endpoint, params=params)

    async def v2_patch(self, endpoint: str, data: dict) -> Any:
        """PATCH request to Jamf Pro API v2.

        Args:
            endpoint: Endpoint path (without /api/v2 prefix)
            data: Request body data

        Returns:
            Parsed JSON response
        """
        full_endpoint = f"/api/v2/{endpoint.lstrip('/')}"
        return await self._request("PATCH", full_endpoint, data=data)

    # ==========================================================================
    # Jamf Pro API v3 Methods
    # ==========================================================================

    async def v3_get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """GET request to Jamf Pro API v3.

        Args:
            endpoint: Endpoint path (without /api/v3 prefix)
            params: Query parameters

        Returns:
            Parsed JSON response
        """
        full_endpoint = f"/api/v3/{endpoint.lstrip('/')}"
        return await self._request("GET", full_endpoint, params=params)
