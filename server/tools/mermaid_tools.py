"""
Mermaid Diagram Generation Tools
=================================
Tools for generating, validating, and managing Mermaid diagrams
"""

import os
import logging
import hashlib
import subprocess
import time
from pathlib import Path
from typing import Dict, Any

from mcp_app import mcp
from config import get_config

logger = logging.getLogger(__name__)

# Track retry attempts per diagram (in-memory for simplicity)
attempt_tracker: Dict[str, int] = {}


@mcp.tool(
    name="generate_mermaid_diagram",
    description=(
        "Generate diagram image from Mermaid code. Returns image_url to view result.\n\n"
        "Required: mermaid_code (string)\n"
        "Optional: output_format (svg/png/pdf, default=svg), theme (default/dark/forest/neutral), "
        "background (white/transparent), scale (1-3, default=2), width (800-3200px, default=1600)\n\n"
        "Quality: scale=1 (fast), scale=2 (balanced), scale=3 (high). SVG is fastest and recommended.\n"
        "Returns: {success, image_url, file_name} or {success=false, error, suggestion}"
    ),
)
def generate_mermaid_diagram(
    mermaid_code: str,
    output_format: str = "",
    filename: str = "",
    theme: str = "",
    background: str = "",
    scale: int = 2,
    width: int = 1600
):
    """Generate diagram from Mermaid syntax"""
    
    config = get_config()
    mermaid_config = config.get('mermaid', {})
    
    # Get settings from config with defaults
    max_attempts = int(os.getenv('MERMAID_MAX_RETRIES', mermaid_config.get('max_retry_attempts', 5)))
    output_dir = os.getenv('MERMAID_OUTPUT_DIR', mermaid_config.get('output_dir', '/app/data/diagrams'))
    max_size = mermaid_config.get('max_diagram_size', 50000)
    
    # Use config defaults if not provided
    if not output_format:
        output_format = mermaid_config.get('default_format', 'svg')
    if not theme:
        theme = mermaid_config.get('default_theme', 'default')
    if not background:
        background = mermaid_config.get('default_background', 'white')
    
    logger.info(f"🎨 Generating Mermaid diagram | format={output_format} | theme={theme}")
    
    # Validate input
    if not mermaid_code or not mermaid_code.strip():
        return {
            "success": False,
            "error": "mermaid_code is empty - please provide Mermaid diagram syntax",
            "suggestion": "Example: graph TD\n    A[Start] --> B[End]"
        }
    
    if len(mermaid_code) > max_size:
        return {
            "success": False,
            "error": f"Diagram code too large ({len(mermaid_code)} chars, max {max_size})",
            "suggestion": "Simplify the diagram or split into multiple diagrams"
        }
    
    # Validate scale and width
    if scale not in [1, 2, 3]:
        scale = 2  # Default to balanced
        logger.warning(f"Invalid scale {scale}, using default 2")
    
    if not (800 <= width <= 3200):
        width = 1600  # Default to balanced
        logger.warning(f"Invalid width {width}, using default 1600")
    
    if output_format not in ['png', 'svg', 'pdf']:
        return {
            "success": False,
            "error": f"Invalid output_format: {output_format}",
            "suggestion": "Use 'png', 'svg', or 'pdf'"
        }
    
    # Generate hash for tracking attempts
    code_hash = hashlib.md5(mermaid_code.encode()).hexdigest()[:12]
    
    # Check attempt count
    attempts = attempt_tracker.get(code_hash, 0)
    if attempts >= max_attempts:
        attempt_tracker.pop(code_hash, None)  # Reset for next time
        return {
            "success": False,
            "error": f"Maximum retry attempts ({max_attempts}) reached",
            "suggestion": "Unable to generate diagram after multiple attempts. Please verify Mermaid syntax is correct or simplify the diagram.",
            "attempts": attempts,
            "max_attempts": max_attempts
        }
    
    # Increment attempt counter
    attempt_tracker[code_hash] = attempts + 1
    
    # Create output directory if needed
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Generate filenames
    if not filename:
        timestamp = int(time.time())
        filename = f"diagram_{code_hash}_{timestamp}"
    
    input_file = f"/tmp/mermaid_{code_hash}.mmd"
    output_file = os.path.join(output_dir, f"{filename}.{output_format}")
    
    # Write Mermaid code to temp file
    try:
        with open(input_file, 'w', encoding='utf-8') as f:
            f.write(mermaid_code)
        logger.debug(f"📝 Wrote Mermaid code to {input_file}")
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to write temp file: {str(e)}",
            "attempt": attempt_tracker[code_hash],
            "max_attempts": max_attempts
        }
    
    # Build mmdc command with configurable quality settings
    # For SVG, skip scale/width as they don't apply (vector format)
    cmd = [
        "mmdc",
        "-i", input_file,
        "-o", output_file,
        "-t", theme,
        "-b", background
    ]
    
    # Add scale and width only for raster formats (PNG/PDF)
    if output_format in ['png', 'pdf']:
        cmd.extend(["-s", str(scale), "-w", str(width)])
    
    cmd.extend(["-p", "/tmp/puppeteer-config.json"])  # Puppeteer config
    
    # Create puppeteer config with optimized settings
    puppeteer_config = {
        "args": [
            "--no-sandbox", 
            "--disable-setuid-sandbox", 
            "--disable-dev-shm-usage"
        ]
    }
    try:
        import json
        with open("/tmp/puppeteer-config.json", "w") as f:
            json.dump(puppeteer_config, f)
    except Exception as e:
        logger.warning(f"Could not create puppeteer config: {e}")
    
    logger.info(f"🚀 Running: {' '.join(cmd)}")
    
    # Execute mmdc
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Clean up temp file
        try:
            os.remove(input_file)
        except:
            pass
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.warning(f"⚠️ mmdc failed: {error_msg}")
            
            return {
                "success": False,
                "error": error_msg,
                "suggestion": parse_mermaid_error(error_msg),
                "attempt": attempt_tracker[code_hash],
                "max_attempts": max_attempts,
                "prompt": f"Mermaid syntax error detected (attempt {attempt_tracker[code_hash]}/{max_attempts}). Please fix the errors and try again."
            }
        
        # Success!
        attempt_tracker.pop(code_hash, None)  # Reset counter
        
        # Get file size
        file_size = os.path.getsize(output_file)
        
        # Get diagram filename
        diagram_filename = Path(output_file).name
        
        logger.info(f"✓ Generated diagram: {output_file} ({file_size} bytes)")
        
        # Build HTTP URL with auth token that MCPJam Inspector can load in the browser
        base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8401")
        auth_token = os.getenv("AUTH_TOKEN", "avicohen")
        image_url = f"{base_url}/diagrams/{diagram_filename}?token={auth_token}"
        
        return {
            "success": True,
            "message": f"✓ Generated {output_format.upper()} diagram ({file_size} bytes)",
            "image_url": image_url,
            "file_name": diagram_filename,
            "format": output_format,
            "size_bytes": file_size
        }
        
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Diagram generation timed out (30s limit)",
            "suggestion": "Diagram is too complex - try simplifying it",
            "attempt": attempt_tracker[code_hash],
            "max_attempts": max_attempts
        }
    except Exception as e:
        logger.error(f"❌ Error generating diagram: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "attempt": attempt_tracker[code_hash],
            "max_attempts": max_attempts
        }


@mcp.tool(
    name="validate_mermaid_syntax",
    description=(
        "Validate Mermaid syntax without generating image. Returns {valid, diagram_type, errors[]}"
    ),
)
def validate_mermaid_syntax(mermaid_code: str):
    """Validate Mermaid syntax without generating image"""
    
    logger.info("🔍 Validating Mermaid syntax")
    
    if not mermaid_code or not mermaid_code.strip():
        return {
            "valid": False,
            "errors": ["Empty diagram code"],
            "suggestion": "Provide Mermaid diagram syntax"
        }
    
    errors = []
    warnings = []
    
    # Detect diagram type
    diagram_type = detect_diagram_type(mermaid_code)
    if not diagram_type:
        errors.append("Unable to detect diagram type - must start with: graph, flowchart, sequenceDiagram, classDiagram, erDiagram, etc.")
    
    # Basic syntax checks
    lines = mermaid_code.strip().split('\n')
    
    # Check for common issues
    if len(lines) < 2:
        warnings.append("Diagram has only one line - might be incomplete")
    
    # Count nodes (rough estimate)
    node_count = len([line for line in lines if '-->' in line or '---' in line])
    
    if node_count == 0 and diagram_type in ['graph', 'flowchart']:
        warnings.append("No connections found (-->  or ---) - diagram might be empty")
    
    # Check for unclosed brackets
    open_brackets = mermaid_code.count('[') + mermaid_code.count('(') + mermaid_code.count('{')
    close_brackets = mermaid_code.count(']') + mermaid_code.count(')') + mermaid_code.count('}')
    if open_brackets != close_brackets:
        errors.append(f"Mismatched brackets: {open_brackets} open, {close_brackets} closed")
    
    valid = len(errors) == 0
    
    result = {
        "valid": valid,
        "diagram_type": diagram_type or "unknown",
        "node_count": node_count,
        "line_count": len(lines)
    }
    
    if errors:
        result["errors"] = errors
    if warnings:
        result["warnings"] = warnings
    
    if valid:
        result["prompt"] = f"✓ Mermaid syntax appears valid. Diagram type: {diagram_type}, {node_count} connections found."
    else:
        result["prompt"] = f"✗ Mermaid syntax errors detected: {', '.join(errors)}"
    
    return result


@mcp.tool(
    name="list_diagram_types",
    description=(
        "List supported Mermaid diagram types (flowchart, sequence, class, ER, gantt, etc.) with examples"
    ),
)
        "Use this to understand what diagram types are available."
    ),
)
def list_diagram_types():
    """List all supported Mermaid diagram types"""
    
    diagram_types = [
        {
            "type": "flowchart / graph",
            "description": "Flowcharts and directional graphs",
            "example": "flowchart TD\n    A[Start] --> B{Decision}\n    B -->|Yes| C[Do Something]\n    B -->|No| D[Do Something Else]"
        },
        {
            "type": "sequenceDiagram",
            "description": "Sequence diagrams for interactions between actors",
            "example": "sequenceDiagram\n    Alice->>John: Hello John\n    John-->>Alice: Hi Alice"
        },
        {
            "type": "classDiagram",
            "description": "UML class diagrams",
            "example": "classDiagram\n    class Animal\n    Animal : +String name\n    Animal : +makeSound()"
        },
        {
            "type": "erDiagram",
            "description": "Entity relationship diagrams for databases",
            "example": "erDiagram\n    CUSTOMER ||--o{ ORDER : places\n    ORDER ||--|{ LINE-ITEM : contains"
        },
        {
            "type": "stateDiagram",
            "description": "State machine diagrams",
            "example": "stateDiagram-v2\n    [*] --> Still\n    Still --> Moving\n    Moving --> [*]"
        },
        {
            "type": "gantt",
            "description": "Gantt charts for project timelines",
            "example": "gantt\n    title Project Timeline\n    section Planning\n    Task 1 :a1, 2024-01-01, 30d"
        },
        {
            "type": "pie",
            "description": "Pie charts",
            "example": "pie title Pets\n    \"Dogs\" : 386\n    \"Cats\" : 85\n    \"Rats\" : 15"
        },
        {
            "type": "gitGraph",
            "description": "Git commit graphs",
            "example": "gitGraph\n    commit\n    branch develop\n    checkout develop\n    commit"
        }
    ]
    
    return {
        "diagram_types": diagram_types,
        "total_count": len(diagram_types),
        "prompt": f"Mermaid supports {len(diagram_types)} diagram types. Most popular: flowchart, sequenceDiagram, erDiagram, classDiagram."
    }


# Helper functions

def detect_diagram_type(code: str) -> str:
    """Detect diagram type from Mermaid code"""
    code_lower = code.strip().lower()
    
    if code_lower.startswith('graph ') or code_lower.startswith('flowchart'):
        return "flowchart"
    elif code_lower.startswith('sequencediagram'):
        return "sequenceDiagram"
    elif code_lower.startswith('classdiagram'):
        return "classDiagram"
    elif code_lower.startswith('erdiagram'):
        return "erDiagram"
    elif code_lower.startswith('statediagram'):
        return "stateDiagram"
    elif code_lower.startswith('gantt'):
        return "gantt"
    elif code_lower.startswith('pie'):
        return "pie"
    elif code_lower.startswith('gitgraph'):
        return "gitGraph"
    
    return ""


def parse_mermaid_error(error_msg: str) -> str:
    """Parse mmdc error message and provide helpful suggestions"""
    
    error_lower = error_msg.lower()
    
    if 'syntax error' in error_lower:
        return "Syntax error detected. Check for: missing semicolons, incorrect arrow syntax (use --> or ---), mismatched brackets."
    elif 'parse error' in error_lower:
        return "Parse error. Verify diagram type declaration (graph TD, sequenceDiagram, etc.) and node connections."
    elif 'unexpected' in error_lower:
        return "Unexpected token found. Check for typos in keywords or special characters."
    elif 'timeout' in error_lower:
        return "Rendering timed out. Diagram might be too complex - try simplifying."
    else:
        return "Check Mermaid syntax at: https://mermaid.js.org/syntax/"
