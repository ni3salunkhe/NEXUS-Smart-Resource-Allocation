import logging
import logging.handlers
import os
import traceback
from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

def setup_logging(service_name: str):
    """
    Configures logging for a specific service.
    Logs to console and rotating files in the 'logs' directory.
    """
    log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../logs"))
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger()
    # Clear existing handlers if any
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Info File Handler (Rotating)
    info_file = os.path.join(log_dir, f"{service_name}.log")
    info_handler = logging.handlers.RotatingFileHandler(
        info_file, maxBytes=10*1024*1024, backupCount=5
    )
    info_handler.setFormatter(formatter)
    info_handler.setLevel(logging.INFO)
    root_logger.addHandler(info_handler)

    # Error File Handler (Rotating)
    error_file = os.path.join(log_dir, f"{service_name}_err.log")
    error_handler = logging.handlers.RotatingFileHandler(
        error_file, maxBytes=10*1024*1024, backupCount=5
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    root_logger.addHandler(error_handler)

    logging.info(f"Logging initialized for service: {service_name}")

class GlobalExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            logger = logging.getLogger("global_error_handler")
            error_msg = f"Unhandled Exception: {str(e)}"
            tb = traceback.format_exc()
            logger.error(f"{error_msg}\n{tb}")
            
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error", "error": str(e)}
            )

def add_global_error_handler(app: FastAPI):
    app.add_middleware(GlobalExceptionMiddleware)
    
    @app.exception_handler(Exception)
    async def universal_exception_handler(request: Request, exc: Exception):
        logger = logging.getLogger("exception_handler")
        tb = traceback.format_exc()
        logger.error(f"Global Exception caught: {str(exc)}\n{tb}")
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred.", "msg": str(exc)}
        )
