"""
Centralized Configuration Module

Provides validated configuration for all services in the MCPValidator3 system.
Environment variables are loaded from .env file via python-dotenv.
"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class ServiceConfig:
    """
    Centralized service configuration with validation.
    
    All service ports, API keys, and settings are managed here.
    """
    
    # =========================================================================
    # Service Ports
    # =========================================================================
    BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
    VALIDATOR_PORT = int(os.getenv("VALIDATOR_PORT", "8002"))
    ORCHESTRATOR_PORT = int(os.getenv("ORCHESTRATOR_PORT", "8100"))
    GENERATOR_PORT = int(os.getenv("GENERATOR_PORT", "8101"))
    UI_CONTROLLER_PORT = int(os.getenv("UI_CONTROLLER_PORT", "8102"))
    
    # =========================================================================
    # API Keys
    # =========================================================================
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")
    
    # =========================================================================
    # Model Configuration
    # =========================================================================
    # Changed default from gpt-4o-mini to gpt-4o for better quality
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    # =========================================================================
    # Timeouts and Limits
    # =========================================================================
    HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30.0"))
    LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120.0"))
    VALIDATION_TIMEOUT = float(os.getenv("VALIDATION_TIMEOUT", "120.0"))
    MAX_CODE_SIZE = int(os.getenv("MAX_CODE_SIZE", "1000000"))  # 1MB
    MAX_LINES = int(os.getenv("MAX_LINES", "10000"))
    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "5"))
    
    # =========================================================================
    # Scoring Configuration
    # =========================================================================
    MIN_SCORE = int(os.getenv("MIN_SCORE", "10"))  # Minimum score for learning gradient
    APPROVAL_THRESHOLD = int(os.getenv("APPROVAL_THRESHOLD", "80"))
    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate configuration at startup.
        
        Returns:
            True if all critical configuration is present, False otherwise.
        """
        warnings = []
        errors = []
        
        # Check API keys
        if not cls.OPENAI_API_KEY:
            warnings.append("OPENAI_API_KEY not set - LLM features will be disabled")
        
        if not cls.GOOGLE_API_KEY:
            warnings.append("GOOGLE_API_KEY not set - Google features will be disabled")
        
        # Validate port ranges
        for port_name, port_value in [
            ("BACKEND_PORT", cls.BACKEND_PORT),
            ("VALIDATOR_PORT", cls.VALIDATOR_PORT),
            ("ORCHESTRATOR_PORT", cls.ORCHESTRATOR_PORT),
            ("GENERATOR_PORT", cls.GENERATOR_PORT),
            ("UI_CONTROLLER_PORT", cls.UI_CONTROLLER_PORT),
        ]:
            if not (1 <= port_value <= 65535):
                errors.append(f"{port_name}={port_value} is not a valid port number")
        
        # Log warnings
        for warning in warnings:
            logger.warning(f"⚠️ CONFIG: {warning}")
        
        # Log errors
        for error in errors:
            logger.error(f"❌ CONFIG: {error}")
        
        return len(errors) == 0
    
    @classmethod
    def get_service_url(cls, service: str, path: str = "") -> str:
        """
        Get URL for a service.
        
        Args:
            service: Service name (backend, validator, orchestrator, generator, ui_controller)
            path: Optional path to append
            
        Returns:
            Full URL for the service
        """
        ports = {
            "backend": cls.BACKEND_PORT,
            "validator": cls.VALIDATOR_PORT,
            "orchestrator": cls.ORCHESTRATOR_PORT,
            "generator": cls.GENERATOR_PORT,
            "ui_controller": cls.UI_CONTROLLER_PORT,
        }
        
        port = ports.get(service.lower())
        if port is None:
            raise ValueError(f"Unknown service: {service}")
        
        base = f"http://127.0.0.1:{port}"
        return f"{base}{path}" if path else base
    
    @classmethod
    def get_all_service_urls(cls) -> dict:
        """Get all service URLs as a dictionary."""
        return {
            "backend": cls.get_service_url("backend"),
            "validator": cls.get_service_url("validator"),
            "orchestrator": cls.get_service_url("orchestrator"),
            "generator": cls.get_service_url("generator"),
            "ui_controller": cls.get_service_url("ui_controller"),
        }
    
    @classmethod
    def print_config(cls) -> None:
        """Print current configuration (excluding secrets)."""
        logger.info("=" * 60)
        logger.info("MCPValidator3 Configuration")
        logger.info("=" * 60)
        logger.info(f"Backend Port:       {cls.BACKEND_PORT}")
        logger.info(f"Validator Port:     {cls.VALIDATOR_PORT}")
        logger.info(f"Orchestrator Port:  {cls.ORCHESTRATOR_PORT}")
        logger.info(f"Generator Port:     {cls.GENERATOR_PORT}")
        logger.info(f"UI Controller Port: {cls.UI_CONTROLLER_PORT}")
        logger.info(f"OpenAI Model:       {cls.OPENAI_MODEL}")
        logger.info(f"OpenAI API Key:     {'SET' if cls.OPENAI_API_KEY else 'NOT SET'}")
        logger.info(f"Google API Key:     {'SET' if cls.GOOGLE_API_KEY else 'NOT SET'}")
        logger.info(f"HTTP Timeout:       {cls.HTTP_TIMEOUT}s")
        logger.info(f"LLM Timeout:        {cls.LLM_TIMEOUT}s")
        logger.info(f"Max Code Size:      {cls.MAX_CODE_SIZE} bytes")
        logger.info(f"Max Lines:          {cls.MAX_LINES}")
        logger.info(f"Max Iterations:     {cls.MAX_ITERATIONS}")
        logger.info(f"Min Score:          {cls.MIN_SCORE}")
        logger.info(f"Approval Threshold: {cls.APPROVAL_THRESHOLD}")
        logger.info("=" * 60)


# Convenience aliases
config = ServiceConfig

