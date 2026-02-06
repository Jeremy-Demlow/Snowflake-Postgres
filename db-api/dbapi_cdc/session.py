"""
Snowflake session management - single source of truth.

Handles connection via:
  1. Snow CLI config (~/.snowflake/config.toml)
  2. Environment variables
  3. SPCS token file (when running inside Snowpark Container Services)
  4. Explicit credentials

Example:
    from dbapi_cdc.session import get_session
    
    # Using Snow CLI connection name
    session = get_session(connection_name="myconnection")
    
    # Or with explicit params
    session = get_session(account="xxx", user="xxx", password="xxx")
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from snowflake.snowpark import Session as SnowparkSession

logger = logging.getLogger(__name__)


def get_session(
    connection_name: Optional[str] = None,
    account: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    role: str = "ACCOUNTADMIN",
    warehouse: str = "COMPUTE_WH",
    database: Optional[str] = None,
    schema: Optional[str] = None,
) -> "SnowparkSession":
    """
    Get a Snowflake Snowpark session using the best available method.
    
    Priority:
    1. Explicit connection_name -> Snow CLI config.toml
    2. SPCS token (if running in container)
    3. Explicit credentials (account/user/password)
    4. Default Snow CLI connection
    5. Environment variables
    
    Args:
        connection_name: Name of connection in ~/.snowflake/config.toml
        account: Snowflake account identifier
        user: Snowflake username
        password: Snowflake password
        role: Role to use (default: ACCOUNTADMIN)
        warehouse: Warehouse to use (default: COMPUTE_WH)
        database: Database to use
        schema: Schema to use
        
    Returns:
        Snowpark Session
    """
    from snowflake.snowpark import Session as SnowparkSession
    
    token_path = Path("/snowflake/session/token")
    
    # Option 1: Explicit connection name - use Snow CLI config
    if connection_name:
        config_path = _find_config_toml()
        if config_path:
            logger.info(f"Using Snow CLI connection: {connection_name}")
            return _create_from_snow_cli(
                connection_name, config_path, database, schema, warehouse
            )
    
    # Option 2: SPCS token (when running in Snowpark Container Services)
    if token_path.exists() and not connection_name:
        logger.info("Using SPCS token authentication")
        return _create_from_token(token_path, database, schema, warehouse)
    
    # Option 3: Explicit credentials
    if account and user and password:
        logger.info(f"Using explicit credentials for {account}")
        return SnowparkSession.builder.configs({
            "account": account,
            "user": user,
            "password": password,
            "role": role,
            "warehouse": warehouse,
            "database": database,
            "schema": schema,
        }).create()
    
    # Option 4: Default Snow CLI connection
    config_path = _find_config_toml()
    if config_path:
        logger.info("Using default Snow CLI connection")
        return _create_from_snow_cli(None, config_path, database, schema, warehouse)
    
    # Option 5: Environment variables
    env_account = os.getenv("SNOWFLAKE_ACCOUNT")
    env_user = os.getenv("SNOWFLAKE_USER")
    env_password = os.getenv("SNOWFLAKE_PASSWORD")
    
    if env_account and env_user and env_password:
        logger.info("Using environment variable credentials")
        return SnowparkSession.builder.configs({
            "account": env_account,
            "user": env_user,
            "password": env_password,
            "role": os.getenv("SNOWFLAKE_ROLE", role),
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", warehouse),
            "database": database or os.getenv("SNOWFLAKE_DATABASE"),
            "schema": schema or os.getenv("SNOWFLAKE_SCHEMA"),
        }).create()
    
    # Option 6: SPCS token as last resort
    if token_path.exists():
        logger.info("Falling back to SPCS token authentication")
        return _create_from_token(token_path, database, schema, warehouse)
    
    raise RuntimeError(
        "No valid Snowflake connection method found. Provide:\n"
        "  - connection_name for Snow CLI config, or\n"
        "  - account/user/password explicitly, or\n"
        "  - SNOWFLAKE_ACCOUNT/USER/PASSWORD env vars"
    )


def _find_config_toml() -> Optional[Path]:
    """Find Snow CLI config.toml file."""
    locations = [
        Path.home() / ".snowflake" / "config.toml",
        Path("/root/.snowflake/config.toml"),
    ]
    for path in locations:
        if path.exists():
            return path
    return None


def _create_from_token(
    token_path: Path,
    database: Optional[str],
    schema: Optional[str],
    warehouse: str,
) -> "SnowparkSession":
    """Create session from SPCS token file."""
    from snowflake.snowpark import Session as SnowparkSession
    
    token = token_path.read_text().strip()
    return SnowparkSession.builder.configs({
        "account": os.environ.get("SNOWFLAKE_ACCOUNT"),
        "host": os.environ.get("SNOWFLAKE_HOST"),
        "authenticator": "oauth",
        "token": token,
        "database": database,
        "schema": schema,
        "warehouse": warehouse,
    }).create()


def _create_from_snow_cli(
    connection_name: Optional[str],
    config_path: Path,
    database: Optional[str],
    schema: Optional[str],
    warehouse: str,
) -> "SnowparkSession":
    """Create session from Snow CLI config.toml."""
    import toml
    from snowflake.snowpark import Session as SnowparkSession
    
    with open(config_path) as f:
        snow_config = toml.load(f)
    
    connections = snow_config.get("connections", {})
    
    # Find connection
    if connection_name:
        if connection_name not in connections:
            raise RuntimeError(f"Connection '{connection_name}' not found in {config_path}")
        conn_data = connections[connection_name]
    else:
        # Find default or first connection
        conn_data = None
        for name, data in connections.items():
            if data.get("default", False):
                conn_data = data
                connection_name = name
                break
        if conn_data is None and connections:
            connection_name = next(iter(connections.keys()))
            conn_data = connections[connection_name]
        if conn_data is None:
            raise RuntimeError(f"No connections found in {config_path}")
    
    logger.info(f"Using connection: {connection_name}")
    
    # Build params
    params = {
        "account": conn_data.get("account"),
        "user": conn_data.get("user"),
        "role": conn_data.get("role", "ACCOUNTADMIN"),
        "warehouse": conn_data.get("warehouse", warehouse),
        "database": database or conn_data.get("database"),
        "schema": schema or conn_data.get("schema"),
    }
    
    # Handle authentication
    if "token" in conn_data:
        params["password"] = conn_data["token"]
    elif "password" in conn_data:
        params["password"] = conn_data["password"]
    elif "authenticator" in conn_data:
        params["authenticator"] = conn_data["authenticator"]
    
    return SnowparkSession.builder.configs(params).create()


class SessionContext:
    """
    Context manager for Snowflake sessions.
    
    Example:
        with SessionContext(connection_name="myconnection") as session:
            df = session.sql("SELECT 1").collect()
    """
    
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._session = None
    
    def __enter__(self) -> "SnowparkSession":
        self._session = get_session(**self.kwargs)
        return self._session
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            try:
                self._session.close()
            except Exception as e:
                logger.warning(f"Error closing session: {e}")
