"""
dbapi-cdc: Config-driven CDC replication to Snowflake.

Uses Snowpark's session.read.dbapi() for efficient data extraction.

Example (local/CLI):
    from dbapi_cdc import Replicator, load_config
    from dbapi_cdc.session import get_session
    
    config = load_config("config.yaml")
    session = get_session(connection_name="myconnection")
    
    replicator = Replicator(session, config)
    results = replicator.sync_all()

Example (stored procedure - deployed via snow snowpark deploy):
    # In Snowflake, call:
    CALL DBAPI_REPLICA_DB.UTILS.SYNC_SINGLE_TABLE('blfra_prod', 'blfra_prod_rec_items');

Example (deploy task DAG):
    from dbapi_cdc import deploy_cdc_dag
    from snowflake.snowpark import Session
    
    session = Session.builder.config("connection_name", "myconnection").create()
    deploy_cdc_dag(session)
    
    # Or via CLI:
    python -m dbapi_cdc.dag --connection myconnection
"""

__version__ = "0.1.0"

from .extractor import Extractor, ExtractionConfig
from .loader import Loader, LoadConfig
from .replicator import Replicator, ReplicationConfig, load_config
from .state import StateManager
def __getattr__(name):
    if name in ("deploy_cdc_dag", "drop_cdc_dag", "DAGConfig"):
        from . import dag
        return getattr(dag, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "Extractor",
    "ExtractionConfig",
    "Loader", 
    "LoadConfig",
    "Replicator",
    "ReplicationConfig",
    "load_config",
    "StateManager",
    "deploy_cdc_dag",
    "drop_cdc_dag",
    "DAGConfig",
]
