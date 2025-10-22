"""
Configuration management for Inputer Performance Monitor.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv


class MCPServerConfig(BaseModel):
    """Configuration for Chrome DevTools MCP server."""

    port: int = Field(default=3001, description="MCP server port")
    executable_path: Optional[str] = Field(default=None, description="Chrome executable path")
    headless: bool = Field(default=True, description="Run Chrome in headless mode")
    disable_gpu: bool = Field(default=True, description="Disable GPU acceleration")
    no_sandbox: bool = Field(default=True, description="Disable sandbox")
    timeout: int = Field(default=30000, description="Server startup timeout (ms)")

    # Mobile emulation settings
    viewport_width: int = Field(default=430, description="Viewport width (iPhone 16 Pro Max: 430px)")
    viewport_height: int = Field(default=932, description="Viewport height (iPhone 16 Pro Max: 932px)")
    device_scale_factor: float = Field(default=3.0, description="Device pixel ratio (iPhone 16 Pro Max: 3x)")
    user_agent: str = Field(
        default="Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.85 Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        description="User agent string for Googlebot Smartphone"
    )
    mobile_emulation: bool = Field(default=True, description="Enable mobile device emulation")
    network_throttling: Optional[str] = Field(default=None, description="Network throttling profile (Fast 3G, Slow 4G, 3G, or None)")


class InteractionTimingConfig(BaseModel):
    """Configuration for realistic interaction timing."""
    high_priority: List[int] = Field(default=[1000, 3000], description="High priority elements timing range (ms)")
    medium_priority: List[int] = Field(default=[2000, 5000], description="Medium priority elements timing range (ms)")
    low_priority: List[int] = Field(default=[4000, 8000], description="Low priority elements timing range (ms)")


class PerformanceConfig(BaseModel):
    """Configuration for performance testing."""

    max_interactions_per_page: int = Field(default=10, description="Max interactions per page")
    interaction_delay_min: int = Field(default=500, description="Min delay between interactions (ms)")
    interaction_delay_max: int = Field(default=2000, description="Max delay between interactions (ms)")
    page_load_timeout: int = Field(default=30000, description="Page load timeout (ms)")
    element_discovery_timeout: int = Field(default=5000, description="Element discovery timeout (ms)")
    screenshot_capture: bool = Field(default=True, description="Capture screenshots")
    video_capture: bool = Field(default=False, description="Record video of test session")
    interaction_timing: InteractionTimingConfig = Field(default_factory=InteractionTimingConfig, description="Realistic interaction timing")
    start_interactions_early: bool = Field(default=True, description="Start interactions before full page load")
    min_wait_before_first_interaction: int = Field(default=2000, description="Minimum wait before first interaction (ms)")


class DataConfig(BaseModel):
    """Configuration for data storage and reporting."""

    output_dir: str = Field(default="./data", description="Data output directory")
    report_formats: List[str] = Field(default=["json", "csv"], description="Report output formats")
    retention_days: int = Field(default=30, description="Data retention period")


class LoggingConfig(BaseModel):
    """Configuration for logging."""

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format")
    enable_metrics: bool = Field(default=True, description="Enable metrics collection")
    metrics_port: int = Field(default=9090, description="Metrics server port")


class Settings(BaseModel):
    """Main application settings."""

    app_name: str = Field(default="inputer-performance-monitor", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    host: str = Field(default="localhost", description="Application host")
    port: int = Field(default=8000, description="Application port")

    mcp_server: MCPServerConfig = Field(default_factory=MCPServerConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    def __init__(self, config_file: Optional[str] = None, **kwargs):
        """
        Initialize settings from environment variables and config file.

        Args:
            config_file: Path to YAML configuration file
            **kwargs: Additional settings overrides
        """
        # Load environment variables
        load_dotenv()

        # Start with environment variables
        config_data = self._load_from_env()

        # Auto-discover config file if not provided
        if not config_file:
            # Try to find config/config.yaml relative to project root
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # Go up from src/python/config -> src/python -> src -> project_root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
            default_config = os.path.join(project_root, 'config', 'config.yaml')
            if os.path.exists(default_config):
                config_file = default_config

        # Override with config file if found
        if config_file and os.path.exists(config_file):
            file_config = self._load_from_file(config_file)
            config_data.update(file_config)

        # Override with kwargs
        config_data.update(kwargs)

        super().__init__(**config_data)

    def _load_from_env(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        config = {}

        # Application settings
        if os.getenv("APP_NAME"):
            config["app_name"] = os.getenv("APP_NAME")
        if os.getenv("APP_VERSION"):
            config["app_version"] = os.getenv("APP_VERSION")
        if os.getenv("HOST"):
            config["host"] = os.getenv("HOST")
        if os.getenv("PORT"):
            config["port"] = int(os.getenv("PORT"))

        # MCP Server settings
        mcp_config = {}
        if os.getenv("MCP_SERVER_PORT"):
            mcp_config["port"] = int(os.getenv("MCP_SERVER_PORT"))
        if os.getenv("CHROME_EXECUTABLE_PATH"):
            mcp_config["executable_path"] = os.getenv("CHROME_EXECUTABLE_PATH")
        if os.getenv("CHROME_HEADLESS"):
            mcp_config["headless"] = os.getenv("CHROME_HEADLESS").lower() == "true"
        if os.getenv("CHROME_DISABLE_GPU"):
            mcp_config["disable_gpu"] = os.getenv("CHROME_DISABLE_GPU").lower() == "true"
        if os.getenv("CHROME_NO_SANDBOX"):
            mcp_config["no_sandbox"] = os.getenv("CHROME_NO_SANDBOX").lower() == "true"

        # Mobile emulation settings
        if os.getenv("VIEWPORT_WIDTH"):
            mcp_config["viewport_width"] = int(os.getenv("VIEWPORT_WIDTH"))
        if os.getenv("VIEWPORT_HEIGHT"):
            mcp_config["viewport_height"] = int(os.getenv("VIEWPORT_HEIGHT"))
        if os.getenv("DEVICE_SCALE_FACTOR"):
            mcp_config["device_scale_factor"] = float(os.getenv("DEVICE_SCALE_FACTOR"))
        if os.getenv("USER_AGENT"):
            mcp_config["user_agent"] = os.getenv("USER_AGENT")
        if os.getenv("MOBILE_EMULATION"):
            mcp_config["mobile_emulation"] = os.getenv("MOBILE_EMULATION").lower() == "true"

        if mcp_config:
            config["mcp_server"] = mcp_config

        # Performance settings
        perf_config = {}
        if os.getenv("MAX_INTERACTIONS_PER_PAGE"):
            perf_config["max_interactions_per_page"] = int(os.getenv("MAX_INTERACTIONS_PER_PAGE"))
        if os.getenv("INTERACTION_DELAY_MIN"):
            perf_config["interaction_delay_min"] = int(os.getenv("INTERACTION_DELAY_MIN"))
        if os.getenv("INTERACTION_DELAY_MAX"):
            perf_config["interaction_delay_max"] = int(os.getenv("INTERACTION_DELAY_MAX"))
        if os.getenv("PAGE_LOAD_TIMEOUT"):
            perf_config["page_load_timeout"] = int(os.getenv("PAGE_LOAD_TIMEOUT"))
        if os.getenv("ELEMENT_DISCOVERY_TIMEOUT"):
            perf_config["element_discovery_timeout"] = int(os.getenv("ELEMENT_DISCOVERY_TIMEOUT"))
        if os.getenv("SCREENSHOT_CAPTURE"):
            perf_config["screenshot_capture"] = os.getenv("SCREENSHOT_CAPTURE").lower() == "true"
        if perf_config:
            config["performance"] = perf_config

        # Data settings
        data_config = {}
        if os.getenv("DATA_OUTPUT_DIR"):
            data_config["output_dir"] = os.getenv("DATA_OUTPUT_DIR")
        if os.getenv("REPORT_FORMAT"):
            data_config["report_formats"] = os.getenv("REPORT_FORMAT").split(",")
        if data_config:
            config["data"] = data_config

        # Logging settings
        log_config = {}
        if os.getenv("LOG_LEVEL"):
            log_config["level"] = os.getenv("LOG_LEVEL")
        if os.getenv("LOG_FORMAT"):
            log_config["format"] = os.getenv("LOG_FORMAT")
        if os.getenv("ENABLE_METRICS"):
            log_config["enable_metrics"] = os.getenv("ENABLE_METRICS").lower() == "true"
        if os.getenv("METRICS_PORT"):
            log_config["metrics_port"] = int(os.getenv("METRICS_PORT"))
        if log_config:
            config["logging"] = log_config

        return config

    def _load_from_file(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")

        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}

    @validator('logging')
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.level.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v.level}")
        v.level = v.level.upper()
        return v

    def get_data_dir(self, subdir: str = "") -> Path:
        """Get a data directory path, creating it if necessary."""
        path = Path(self.data.output_dir)
        if subdir:
            path = path / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path