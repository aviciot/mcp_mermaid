"""
Template MCP Server - Starlette Application
===========================================
MCP server with authentication middleware and auto-discovery
"""

import os
import sys
import signal
import logging
import importlib
import pkgutil
import warnings

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.staticfiles import StaticFiles
import uvicorn

from config import get_config
from mcp_app import mcp

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load configuration
config = get_config()

# Validate configuration (fail fast if misconfigured)
from utils.config_validator import validate_config
validate_config(config)

# ========================================
# AUTO-DISCOVERY CONFIGURATION
# ========================================
AUTO_DISCOVER = os.getenv("AUTO_DISCOVER", "true").lower() in ("1", "true", "yes", "on")

# ========================================
# MODULE LOADING HELPERS
# ========================================
def import_submodules(pkg_name: str):
    """Auto-import all submodules in a package (tools/resources/prompts)."""
    try:
        pkg = __import__(pkg_name)
        for _, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
            if not ispkg and not modname.startswith('_'):
                full_name = f"{pkg_name}.{modname}"
                importlib.import_module(full_name)
                logger.info(f"✅ Loaded: {full_name}")
    except Exception as e:
        logger.error(f"❌ Failed to load {pkg_name}: {e}")

def safe_import(name: str):
    """Static import (fallback when AUTO_DISCOVER disabled)."""
    try:
        module = __import__(name, fromlist=["*"])
        logger.info(f"✅ Imported: {name}")
        return module
    except Exception as e:
        logger.exception(f"❌ Failed to import: {name}: {e}")
        raise

# ========================================
# GRACEFUL SHUTDOWN
# ========================================
def _graceful_shutdown(*_):
    logger.info("🛑 Received shutdown signal, stopping gracefully...")
    sys.exit(0)

for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, _graceful_shutdown)

# ========================================
# STARTUP BANNER
# ========================================
logger.info("=" * 80)
logger.info("🚀 Template MCP Server - Starting Up")
logger.info("=" * 80)
logger.info(f"📦 Version: {config.get('server.version', '1.0.0')}")
logger.info(f"🌐 Port: {os.getenv('MCP_PORT', config.get('server.port', 8000))}")

# Authentication status
auth_enabled = config.is_authentication_enabled()
auth_icon = "✅" if auth_enabled else "❌"
logger.info(f"🔐 Authentication: {auth_icon} {'Enabled' if auth_enabled else 'Disabled'}")

logger.info("-" * 80)

# ========================================
# AUTO-DISCOVER MODULES
# ========================================
if AUTO_DISCOVER:
    logger.info("🔍 Auto-discovery enabled - loading all tools/resources/prompts...")
    for pkg in ("tools", "resources", "prompts"):
        import_submodules(pkg)
else:
    logger.info("📦 Using static imports...")
    for pkg in ("tools", "resources", "prompts"):
        safe_import(pkg)

logger.info("-" * 80)
logger.info("📡 MCP Server: Ready")
logger.info("=" * 80)

# ========================================
# BUILD ASGI APP
# ========================================
os.environ["PYTHONUNBUFFERED"] = "1"
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Get FastMCP HTTP app and create Starlette with its lifespan
mcp_http_app = mcp.http_app()
app = Starlette(lifespan=mcp_http_app.lifespan)


# ========================================
# AUTHENTICATION MIDDLEWARE
# ========================================

# Paths that require token in URL (for browser image loading)
STATIC_FILE_PATHS = ["/diagrams", "/graphs", "/exports"]

class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Authentication middleware - validates Bearer token or URL token"""
    
    def _is_static_file_path(self, path: str) -> bool:
        """Check if path is a static file that should use URL token"""
        return any(path.startswith(p + "/") for p in STATIC_FILE_PATHS)
    
    async def dispatch(self, request, call_next):
        # Skip auth for health check endpoints
        if request.url.path in ["/healthz", "/health", "/version", "/_info"]:
            return await call_next(request)
        
        # Check if authentication is enabled
        if not config.is_authentication_enabled():
            logger.debug("Authentication disabled - allowing request")
            return await call_next(request)
        
        expected_token = config.get_auth_token()
        
        # For static files (images), accept token in URL parameter
        if self._is_static_file_path(request.url.path):
            url_token = request.query_params.get("token")
            
            if not url_token:
                logger.warning(f"Missing token parameter for static file: {request.url.path}")
                return JSONResponse(
                    {"error": "Missing token parameter. Use: ?token=YOUR_TOKEN"},
                    status_code=403
                )
            
            if url_token != expected_token:
                logger.warning(f"Invalid token for static file: {request.url.path}")
                return JSONResponse(
                    {"error": "Invalid token parameter"},
                    status_code=403
                )
            
            # Token valid - allow access
            logger.debug(f"Static file access granted: {request.url.path}")
            return await call_next(request)
        
        # For all other requests (MCP tools), require Bearer token in header
        if not config.is_authentication_enabled():
            logger.debug("Authentication disabled - allowing request")
            return await call_next(request)
        
        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            logger.warning("Missing Authorization header")
            return JSONResponse(
                {"error": "Missing Authorization header"},
                status_code=401
            )
        
        # Validate Bearer token format
        if not auth_header.startswith("Bearer "):
            logger.warning("Invalid Authorization header format")
            return JSONResponse(
                {"error": "Invalid Authorization header format. Use: Bearer <token>"},
                status_code=401
            )
        
        # Extract and validate token
        token = auth_header[7:]  # Remove "Bearer " prefix
        expected_token = config.get_auth_token()
        
        if token != expected_token:
            logger.warning("Invalid authentication token")
            return JSONResponse(
                {"error": "Invalid authentication token"},
                status_code=403
            )
        
        # Token valid - proceed
        logger.debug("Authentication successful")
        return await call_next(request)


# Add authentication middleware if enabled
if config.is_authentication_enabled():
    app.add_middleware(AuthenticationMiddleware)
    logger.info("Authentication middleware enabled")

# Add request logging middleware
from utils.request_logging import RequestLoggingMiddleware
app.add_middleware(RequestLoggingMiddleware)
logger.info("Request logging middleware enabled")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================================
# SIMPLE ENDPOINTS
# ========================================

async def health_check(request):
    """Health check endpoint"""
    return PlainTextResponse("OK")


async def version_info(request):
    """Version information endpoint"""
    return JSONResponse({
        "name": config.get('mcp.name', 'template-mcp'),
        "version": config.get('server.version', '1.0.0'),
        "status": "running"
    })


async def deep_health_check(request):
    """
    Deep health check - checks dependencies
    
    Returns 200 if all dependencies are healthy, 503 otherwise
    """
    health = {
        "status": "healthy",
        "checks": {
            "server": "ok"
        }
    }
    
    # Add database health check if you have DB
    # try:
    #     from db.connector import db
    #     if await db.health_check():
    #         health["checks"]["database"] = "ok"
    #     else:
    #         health["checks"]["database"] = "unhealthy"
    #         health["status"] = "unhealthy"
    # except Exception as e:
    #     health["checks"]["database"] = f"error: {str(e)}"
    #     health["status"] = "unhealthy"
    
    status_code = 200 if health["status"] == "healthy" else 503
    return JSONResponse(health, status_code=status_code)


# ========================================
# ROUTES
# ========================================
app.add_route("/healthz", health_check, methods=["GET"])
app.add_route("/health", health_check, methods=["GET"])
app.add_route("/health/deep", deep_health_check, methods=["GET"])
app.add_route("/version", version_info, methods=["GET"])

# ========================================
# SERVE GENERATED DIAGRAMS (for MCPJam Inspector)
# ========================================
DIAGRAMS_DIR = os.getenv("MERMAID_OUTPUT_DIR", "/app/data/diagrams")
if os.path.exists(DIAGRAMS_DIR):
    app.mount("/diagrams", StaticFiles(directory=DIAGRAMS_DIR), name="diagrams")
    logger.info(f"🖼️ Serving diagrams at /diagrams from {DIAGRAMS_DIR}")
else:
    logger.warning(f"⚠️ Diagrams directory not found: {DIAGRAMS_DIR}")

# ========================================
# MOUNT FASTMCP HTTP APP
# ========================================
# Mount FastMCP at root (MUST be last)
app.mount("/", mcp_http_app)

logger.info("✅ FastMCP mounted at /")

# ========================================
# MAIN
# ========================================
if __name__ == "__main__":
    port = int(os.getenv('MCP_PORT', config.get('server.port', 8000)))
    host = config.get('server.host', '0.0.0.0')
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )
