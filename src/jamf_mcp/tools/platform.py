"""Read-only tools for Jamf Platform Blueprints and Compliance Benchmarks."""

from typing import Any
from urllib.parse import quote
from uuid import UUID

from ._common import format_error, format_response, get_platform_client_safe
from ._registry import jamf_tool


async def _read_report(
    segments: tuple[str, ...],
    params: dict[str, Any] | None = None,
) -> str:
    """Read a fixed reporting path and validate pagination before network access."""
    client, error = get_platform_client_safe()
    if error:
        return error
    try:
        if any(not segment or segment in {".", ".."} for segment in segments):
            raise ValueError("Resource identifiers must be nonempty and cannot be dot segments")
        params = params or {}
        if params.get("page", 0) < 0:
            raise ValueError("page must be non-negative")
        if not 1 <= params.get("page-size", params.get("size", 1)) <= 500:
            raise ValueError("Page size must be between 1 and 500")
        if "rule-id" in params and not params["rule-id"]:
            raise ValueError("rule_id is required")
        if "filter" in params and not params["filter"].strip():
            raise ValueError("A nonempty declaration filter is required")
        if params.get("rule-result") not in {None, "PASSED", "FAILED", "UNKNOWN"}:
            raise ValueError("rule_result must be PASSED, FAILED or UNKNOWN")
        path = "/" + "/".join(quote(segment, safe="") for segment in segments)
        return format_response(await client.get(path, params), "Retrieved Jamf Platform report")
    except Exception as error:
        return format_error(error)


@jamf_tool(read_only=True)
async def jamf_platform_get_blueprints(
    blueprint_id: str | None = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """List Blueprints or retrieve a Blueprint definition. Requires blueprints:read.

    Uses the separate Jamf Account Platform environment integration. List results
    are paginated. This tool does not deploy or modify Blueprints.
    """
    client, error = get_platform_client_safe()
    if error:
        return error
    try:
        if blueprint_id is not None:
            blueprint_id = str(UUID(blueprint_id))
            data = await client.get(f"/blueprints/v1/blueprints/{blueprint_id}")
        else:
            if page < 0 or not 1 <= page_size <= 100:
                raise ValueError("page must be non-negative and page_size between 1 and 100")
            data = await client.get(
                "/blueprints/v1/blueprints", {"page": page, "page-size": page_size}
            )
        return format_response(data, "Retrieved Jamf Platform Blueprints")
    except Exception as error:
        return format_error(error)


@jamf_tool(read_only=True)
async def jamf_platform_get_benchmarks(benchmark_id: str | None = None) -> str:
    """List compliance benchmarks or read a definition. Requires compliance-benchmarks:read.

    Definitions describe configured rules, not device pass/fail results. The
    benchmark list endpoint does not expose pagination parameters.
    """
    client, error = get_platform_client_safe()
    if error:
        return error
    try:
        path = "/compliance-benchmarks/v1/benchmarks"
        if benchmark_id is not None:
            if not benchmark_id or benchmark_id in {".", ".."}:
                raise ValueError("benchmark_id must identify a benchmark")
            path += f"/{quote(benchmark_id, safe='')}"
        return format_response(
            await client.get(path), "Retrieved compliance benchmark configuration"
        )
    except Exception as error:
        return format_error(error)


@jamf_tool(read_only=True)
async def jamf_platform_get_benchmark_rules(
    benchmark_id: str,
    page: int = 0,
    page_size: int = 100,
    search: str | None = None,
) -> str:
    """Read benchmark rule statistics, including pass/fail/unknown device counts.

    Requires compliance-benchmarks:read. Results are actual device assessments,
    rather than the benchmark definition. Use each returned rule ID to query devices.
    """
    params: dict[str, Any] = {"page": page, "page-size": page_size}
    if search is not None:
        params["rule-search"] = search
    return await _read_report(
        ("compliance-benchmarks", "v1", "benchmarks", benchmark_id, "rules"),
        params,
    )


@jamf_tool(read_only=True)
async def jamf_platform_get_benchmark_devices(
    benchmark_id: str,
    rule_id: str,
    page: int = 0,
    page_size: int = 100,
    rule_result: str | None = None,
    search: str | None = None,
) -> str:
    """Read device results for one benchmark rule. Requires compliance-benchmarks:read.

    rule_result optionally selects PASSED, FAILED or UNKNOWN. Device IDs returned
    here are Platform IDs, not numeric Jamf Pro inventory IDs. This is a per-rule
    report, not every compliance result for one device.
    """
    params: dict[str, Any] = {"page": page, "page-size": page_size, "rule-id": rule_id}
    if rule_result is not None:
        params["rule-result"] = rule_result
    if search is not None:
        params["device-search"] = search
    return await _read_report(
        ("compliance-benchmarks", "v1", "benchmarks", benchmark_id, "devices"),
        params,
    )


@jamf_tool(read_only=True)
async def jamf_platform_get_benchmark_compliance(benchmark_id: str) -> str:
    """Read a benchmark's aggregate compliance percentage. Requires compliance-benchmarks:read.

    Jamf defines this as the sum of device compliance scores divided by the number
    of devices. Use rule statistics and device results for a failure drill-down.
    """
    return await _read_report(
        ("compliance-benchmarks", "v1", "benchmarks", benchmark_id, "compliance-percentage"),
    )


@jamf_tool(read_only=True)
async def jamf_platform_get_declarations(
    filter: str,
    device_id: str | None = None,
    declaration_identifier: str | None = None,
    page: int = 0,
    page_size: int = 20,
    sort: list[str] | None = None,
) -> str:
    """Read declarations on a device or devices reporting a declaration. Requires declarations:read.

    Supply exactly one of device_id (Platform UUID, not a Pro numeric ID) and
    declaration_identifier. filter is required, for example active==true or
    channel==SYSTEM. Filters apply to declarations already on devices and exclude
    PENDING declarations. An empty report does not prove all assigned Blueprints
    arrived. Optional sort values use field,asc syntax and are sent separately.
    """
    _, error = get_platform_client_safe()
    if error:
        return error
    try:
        if (device_id is None) == (declaration_identifier is None):
            raise ValueError("Supply exactly one of device_id and declaration_identifier")
        if device_id is not None:
            segments = ("ddm", "report", "v1", "devices", str(UUID(device_id)), "declarations")
        else:
            segments = ("ddm", "report", "v1", "declarations", declaration_identifier, "devices")
        params: dict[str, Any] = {"filter": filter, "page": page, "size": page_size}
        if sort:
            params["sort"] = sort
        return await _read_report(segments, params)
    except ValueError as error:
        return format_error(error)


@jamf_tool(read_only=True)
async def jamf_platform_get_device_channels(device_id: str) -> str:
    """Read a Platform device's DDM reporting channels. Requires declarations:read.

    device_id must be the Platform UUID, not the numeric Jamf Pro inventory ID.
    This tool retrieves reporting state and does not send device commands.
    """
    _, error = get_platform_client_safe()
    if error:
        return error
    try:
        return await _read_report(
            ("ddm", "report", "v1", "devices", str(UUID(device_id)), "channels")
        )
    except ValueError as error:
        return format_error(error)
