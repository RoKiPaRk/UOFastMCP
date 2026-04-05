"""
Configuration Loader Module
============================

Handles loading configuration from environment variables and INI files.
"""

import os
import logging
import configparser
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("uofast-mcp.config")


def _decrypt_if_needed(value: str, jwt_secret: str, salt: bytes | None) -> str:
    """
    Transparently decrypt an ``ENC:``-prefixed password value.

    If *salt* is ``None`` or *jwt_secret* is empty the value is returned
    as-is (with a warning if it looks encrypted).  This keeps the server
    running even when the encryption key is temporarily unavailable.
    """
    from .credential_store import is_encrypted, decrypt_password

    if not is_encrypted(value):
        if value:
            logger.warning(
                "Plaintext password detected in unidata_config.ini. "
                "Re-run the setup wizard to encrypt credentials."
            )
        return value

    if not salt or not jwt_secret:
        logger.error(
            "Cannot decrypt credential: JWT_SECRET_KEY or encryption salt is missing. "
            "The connection will likely fail — set JWT_SECRET_KEY and restart."
        )
        return value

    try:
        return decrypt_password(value, jwt_secret, salt)
    except ValueError as exc:
        logger.error("Credential decryption failed: %s", exc)
        return value


class ConfigLoader:
    """Loads and manages configuration from various sources."""

    def __init__(self):
        """Initialize the configuration loader."""
        self.config_file_path: Optional[Path] = None
        self.config: Optional[configparser.ConfigParser] = None

    def load_connection_from_env(self) -> Optional[Dict[str, Any]]:
        """
        Load connection parameters from environment variables.

        Returns:
            Dictionary with connection parameters or None if not found
        """
        host = os.getenv("UNIDATA_HOST")
        username = os.getenv("UNIDATA_USERNAME")
        password = os.getenv("UNIDATA_PASSWORD")
        account = os.getenv("UNIDATA_ACCOUNT")

        if host and username and password and account:
            logger.info("Loading connection from environment variables")
            return {
                "host": host,
                "port": int(os.getenv("UNIDATA_PORT", "31438")),
                "username": username,
                "password": password,
                "account": account,
                "service": os.getenv("UNIDATA_SERVICE", "udcs")
            }
        return None

    def find_config_file(self) -> Optional[Path]:
        """
        Find the configuration file in common locations.

        Searches in the following order:
        1. Path specified in UNIDATA_CONFIG_FILE env variable
        2. Current working directory
        3. Script directory
        4. User home directory

        Returns:
            Path to config file or None if not found
        """
        # Check for config file path in environment variable
        env_config_path = os.getenv("UNIDATA_CONFIG_FILE")
        if env_config_path:
            config_path = Path(env_config_path)
            if config_path.exists():
                return config_path
            else:
                logger.warning(
                    f"Config file specified in UNIDATA_CONFIG_FILE not found: "
                    f"{env_config_path}"
                )

        # Check current directory
        current_dir = Path.cwd()
        config_file = current_dir / "unidata_config.ini"
        if config_file.exists():
            return config_file

        # Check script directory
        script_dir = Path(__file__).parent.parent.parent.parent
        config_file = script_dir / "unidata_config.ini"
        if config_file.exists():
            return config_file

        # Check user home directory
        home_config = Path.home() / ".unidata_config.ini"
        if home_config.exists():
            return home_config

        return None

    def load_config_file(self) -> Optional[configparser.ConfigParser]:
        """
        Load and parse the INI configuration file.

        Returns:
            ConfigParser object or None if file not found
        """
        config_path = self.find_config_file()
        if not config_path:
            logger.info("No configuration file found. Checked locations:")
            logger.info("  - Environment variable: UNIDATA_CONFIG_FILE")
            logger.info("  - Current directory: unidata_config.ini")
            logger.info("  - Script directory: unidata_config.ini")
            logger.info("  - Home directory: ~/.unidata_config.ini")
            return None

        try:
            config = configparser.ConfigParser()
            config.read(config_path)
            self.config_file_path = config_path
            self.config = config
            logger.info(f"Loaded configuration from: {config_path}")
            return config

        except Exception as e:
            logger.error(f"Error loading config file {config_path}: {e}")
            return None

    def get_server_settings(
        self,
        config: configparser.ConfigParser
    ) -> Dict[str, Any]:
        """
        Extract server settings from config.

        Args:
            config: ConfigParser object

        Returns:
            Dictionary with server settings
        """
        settings = {
            "min_connections": 0,
            "max_connections": 0,
            "log_level": "INFO",
            "default_connection": "default"
        }

        if config.has_section("server"):
            if config.has_option("server", "min_connections"):
                settings["min_connections"] = config.getint("server", "min_connections")

            if config.has_option("server", "max_connections"):
                settings["max_connections"] = config.getint("server", "max_connections")

            if config.has_option("server", "log_level"):
                settings["log_level"] = config.get("server", "log_level").upper()

            if config.has_option("server", "default_connection"):
                settings["default_connection"] = config.get("server", "default_connection")

        return settings

    def load_connections_from_config(
        self,
        config: configparser.ConfigParser
    ) -> Dict[str, Dict[str, Any]]:
        """
        Extract all connection configurations from the config file.

        Args:
            config: ConfigParser object

        Returns:
            Dictionary mapping connection names to their configurations
        """
        # Encryption setup — read once before the loop.
        jwt_secret = os.getenv("JWT_SECRET_KEY", "")
        salt: bytes | None = None
        if config.has_section("encryption") and config.has_option("encryption", "salt"):
            try:
                salt = bytes.fromhex(config.get("encryption", "salt"))
            except ValueError:
                logger.warning("Malformed encryption salt in config — skipping decryption.")

        connections = {}

        for section in config.sections():
            if section.startswith("connection:"):
                conn_name = section.split(":", 1)[1]
                try:
                    raw_password = config.get(section, "password")
                    conn_config = {
                        "host": config.get(section, "host"),
                        "port": config.getint(section, "port", fallback=31438),
                        "username": config.get(section, "username"),
                        "password": _decrypt_if_needed(raw_password, jwt_secret, salt),
                        "account": config.get(section, "account"),
                        "service": config.get(section, "service", fallback="udcs"),
                        "auto_connect": config.getboolean(
                            section, "auto_connect", fallback=False
                        )
                    }
                    connections[conn_name] = conn_config
                    logger.info(
                        f"Found connection config: {conn_name} -> "
                        f"{conn_config['host']}:{conn_config['port']}"
                    )
                except Exception as e:
                    logger.error(f"Error parsing connection '{conn_name}': {e}")

        return connections

    def setup_logging(self, log_level: str):
        """
        Configure logging level for the application.

        Args:
            log_level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        # Get root logger for uofast-mcp
        app_logger = logging.getLogger("uofast-mcp")
        app_logger.setLevel(getattr(logging, log_level, logging.INFO))
        logger.info(f"Log level set to: {log_level}")
