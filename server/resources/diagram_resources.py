"""
Mermaid Diagram Resources
=========================
Exposes generated diagrams as MCP image resources using proper MCP binary content format
"""

import logging
import os
import base64
from pathlib import Path
from typing import Optional

from mcp_app import mcp

logger = logging.getLogger(__name__)

DIAGRAMS_DIR = Path("/app/data/diagrams")


@mcp.resource("diagram://{diagram_name}")
def get_diagram_resource(diagram_name: str) -> str:
    """
    Get a generated diagram as an image resource.
    
    Per MCP spec, binary content (images) should return:
    {
      "uri": "diagram://filename.png",
      "mimeType": "image/png",
      "blob": "base64-encoded-data"
    }
    
    Args:
        diagram_name: Name of the diagram file (e.g., diagram_abc123_1234567890.png)
    
    Returns:
        Base64-encoded image data
    """
    try:
        # Construct full path
        diagram_path = DIAGRAMS_DIR / diagram_name
        
        if not diagram_path.exists():
            logger.warning(f"Diagram not found: {diagram_path}")
            return f"Error: Diagram '{diagram_name}' not found"
        
        # Read the image file
        with open(diagram_path, 'rb') as f:
            image_data = f.read()
        
        # Encode to base64
        base64_data = base64.b64encode(image_data).decode('utf-8')
        
        logger.info(f"✓ Serving diagram resource: {diagram_name} ({len(image_data)} bytes)")
        
        # Return base64 data - FastMCP will wrap it properly
        return base64_data
        
    except Exception as e:
        logger.error(f"Error serving diagram resource: {e}")
        return f"Error loading diagram: {str(e)}"


@mcp.resource("diagrams://list")
def list_diagrams_resource() -> str:
    """
    List all available diagram files.
    
    Returns:
        Text content with list of available diagrams
    """
    try:
        if not DIAGRAMS_DIR.exists():
            return "No diagrams directory found"
        
        diagrams = sorted(
            [f.name for f in DIAGRAMS_DIR.iterdir() if f.is_file()],
            key=lambda x: DIAGRAMS_DIR.joinpath(x).stat().st_mtime,
            reverse=True
        )
        
        if not diagrams:
            return "No diagrams generated yet"
        
        diagram_list = "\n".join([
            f"- {d} (diagram://{d})"
            for d in diagrams
        ])
        
        return f"Available diagrams ({len(diagrams)}):\n{diagram_list}"
        
    except Exception as e:
        logger.error(f"Error listing diagrams: {e}")
        return f"Error listing diagrams: {str(e)}"

