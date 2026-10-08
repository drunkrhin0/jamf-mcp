# Copyright 2026, Jamf Software LLC
"""Printer management tools for Jamf Pro.

This module provides tools for managing printers in Jamf Pro.
Printers can be deployed to computers via policies for automatic
printer mapping.
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


@jamf_tool(read_only=True)
async def jamf_get_printers(
    printer_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get printers from Jamf Pro.

    Retrieves printer records from Jamf Pro. Printers represent network or
    local printers that can be deployed to computers via policies.

    Args:
        printer_id: Specific printer ID to retrieve full details
        name: Filter printers by name (partial match, case-insensitive)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing printer list with names and IDs, or detailed info
        for a specific printer including URI, model, and PPD settings.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if printer_id:
            result = await client.classic_get("printers", printer_id)
            return format_response(result, f"Retrieved printer ID {printer_id}")

        result = await client.classic_get("printers")

        printers = result.get("printers", [])
        if name:
            printers = [
                p for p in printers if name.lower() in p.get("name", "").lower()
            ]

        start = page * page_size
        end = start + page_size
        paginated = printers[start:end]

        return format_response(
            {"printers": paginated, "totalCount": len(printers)},
            f"Retrieved {len(paginated)} printers (total: {len(printers)})",
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting printers")
        return format_error(e)


@jamf_tool(destructive=False)
async def jamf_create_printer(
    name: str,
    category: Optional[str] = None,
    uri: Optional[str] = None,
    CUPS_name: Optional[str] = None,
    location: Optional[str] = None,
    model: Optional[str] = None,
    info: Optional[str] = None,
    notes: Optional[str] = None,
    make_default: Optional[bool] = None,
    use_generic: Optional[bool] = None,
    ppd: Optional[str] = None,
    ppd_path: Optional[str] = None,
    ppd_contents: Optional[str] = None,
) -> str:
    """Create a new printer in Jamf Pro.

    Creates a printer record that can be deployed to computers via policies
    for automatic printer mapping.

    Args:
        name: Printer name (required)
        category: Printer category
        uri: Printer URI (e.g., lpd://10.1.20.204/)
        CUPS_name: CUPS printer name
        location: Physical location description
        model: Printer model
        info: Additional info
        notes: Notes
        make_default: Set as default printer
        use_generic: Use generic PPD driver
        ppd: PPD filename
        ppd_path: Full path to PPD file
        ppd_contents: PPD file contents

    Returns:
        JSON containing the created printer's ID and confirmation message.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        printer_data: dict = {"name": name}

        optional_fields = {
            "category": category,
            "uri": uri,
            "CUPS_name": CUPS_name,
            "location": location,
            "model": model,
            "info": info,
            "notes": notes,
            "make_default": make_default,
            "use_generic": use_generic,
            "ppd": ppd,
            "ppd_path": ppd_path,
            "ppd_contents": ppd_contents,
        }

        for key, value in optional_fields.items():
            if value is not None:
                printer_data[key] = value

        result = await client.classic_post("printers", {"printer": printer_data})
        return format_response(result, f"Created printer '{name}'")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error creating printer")
        return format_error(e)


@jamf_tool
async def jamf_update_printer(
    printer_id: int,
    name: Optional[str] = None,
    category: Optional[str] = None,
    uri: Optional[str] = None,
    CUPS_name: Optional[str] = None,
    location: Optional[str] = None,
    model: Optional[str] = None,
    info: Optional[str] = None,
    notes: Optional[str] = None,
    make_default: Optional[bool] = None,
    use_generic: Optional[bool] = None,
    ppd: Optional[str] = None,
    ppd_path: Optional[str] = None,
    ppd_contents: Optional[str] = None,
) -> str:
    """Update an existing printer in Jamf Pro.

    Updates a printer record by ID. Only provided fields will be updated;
    omitted fields remain unchanged.

    Args:
        printer_id: ID of the printer to update (required)
        name: New printer name
        category: Printer category
        uri: Printer URI (e.g., lpd://10.1.20.204/)
        CUPS_name: CUPS printer name
        location: Physical location description
        model: Printer model
        info: Additional info
        notes: Notes
        make_default: Set as default printer
        use_generic: Use generic PPD driver
        ppd: PPD filename
        ppd_path: Full path to PPD file
        ppd_contents: PPD file contents

    Returns:
        JSON confirming the printer was updated.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        printer_data: dict = {}

        fields = {
            "name": name,
            "category": category,
            "uri": uri,
            "CUPS_name": CUPS_name,
            "location": location,
            "model": model,
            "info": info,
            "notes": notes,
            "make_default": make_default,
            "use_generic": use_generic,
            "ppd": ppd,
            "ppd_path": ppd_path,
            "ppd_contents": ppd_contents,
        }

        for key, value in fields.items():
            if value is not None:
                printer_data[key] = value

        result = await client.classic_put(
            "printers", printer_id, {"printer": printer_data}
        )
        return format_response(result, f"Updated printer ID {printer_id}")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error updating printer")
        return format_error(e)


