# =============================================================================
# Terraform - Static Snowflake Infrastructure for PostgreSQL CDC
# =============================================================================

terraform {
  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 2.0"
    }
  }
}

# Authentication via environment variables:
# SNOWFLAKE_ORGANIZATION_NAME, SNOWFLAKE_ACCOUNT_NAME, SNOWFLAKE_USER
# SNOWFLAKE_AUTHENTICATOR=PROGRAMMATIC_ACCESS_TOKEN, SNOWFLAKE_PASSWORD=<PAT>
provider "snowflake" {
  role      = "ACCOUNTADMIN"
  warehouse = "COMPUTE_WH"
}

variable "pg_host" {
  description = "PostgreSQL host"
  type        = string
}

variable "pg_username" {
  description = "PostgreSQL username"
  type        = string
  sensitive   = true
}

variable "pg_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
}

# =============================================================================
# Database and Schemas
# =============================================================================

resource "snowflake_database" "replica_db" {
  name    = "DBAPI_REPLICA_DB"
  comment = "PostgreSQL CDC replication database"
}

resource "snowflake_schema" "utils" {
  database = snowflake_database.replica_db.name
  name     = "UTILS"
  comment  = "Procedures, tasks, and registry tables"
}

resource "snowflake_schema" "public" {
  database = snowflake_database.replica_db.name
  name     = "PUBLIC"
  comment  = "Secrets and network rules"
}

# =============================================================================
# Registry Tables
# =============================================================================

resource "snowflake_execute" "database_registry" {
  execute = <<-SQL
    CREATE TABLE ${snowflake_database.replica_db.name}.${snowflake_schema.utils.name}.DATABASE_REGISTRY (
      DATABASE_ID VARCHAR(100) PRIMARY KEY,
      SOURCE_DB_NAME VARCHAR(200) NOT NULL,
      HOST VARCHAR(500) NOT NULL,
      PORT INTEGER DEFAULT 5432,
      SOURCE_SCHEMA VARCHAR(100) DEFAULT 'public',
      TARGET_SCHEMA VARCHAR(100) NOT NULL,
      IS_ACTIVE BOOLEAN DEFAULT TRUE,
      CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
      UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
    )
  SQL
  revert  = "DROP TABLE IF EXISTS ${snowflake_database.replica_db.name}.${snowflake_schema.utils.name}.DATABASE_REGISTRY"
  query   = "SELECT COUNT(*) FROM ${snowflake_database.replica_db.name}.${snowflake_schema.utils.name}.DATABASE_REGISTRY"
}

resource "snowflake_execute" "table_registry" {
  execute = <<-SQL
    CREATE TABLE ${snowflake_database.replica_db.name}.${snowflake_schema.utils.name}.TABLE_REGISTRY (
      TABLE_ID VARCHAR(200) PRIMARY KEY,
      DATABASE_ID VARCHAR(100) NOT NULL,
      SOURCE_SCHEMA VARCHAR(100),
      SOURCE_TABLE VARCHAR(200) NOT NULL,
      TARGET_SCHEMA VARCHAR(100) NOT NULL,
      TARGET_TABLE VARCHAR(200) NOT NULL,
      PRIMARY_KEY_COLUMN VARCHAR(100) NOT NULL,
      SYNC_ENABLED BOOLEAN DEFAULT TRUE,
      SYNC_METHOD VARCHAR(20) DEFAULT 'full',
      CDC_COLUMN VARCHAR(100),
      WAL_SLOT_NAME VARCHAR(100),
      LAST_WATERMARK VARCHAR(100),
      LAST_SYNC_AT TIMESTAMP_NTZ,
      LAST_SYNC_STATUS VARCHAR(500),
      LAST_SYNC_RECORDS INTEGER,
      LAST_CDC_ROWS INTEGER,
      BATCH_SIZE INTEGER DEFAULT 100000,
      SCHEMA_FINGERPRINT VARCHAR(50),
      SCHEMA_VERSION INTEGER DEFAULT 1,
      CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
      UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
    )
  SQL
  revert  = "DROP TABLE IF EXISTS ${snowflake_database.replica_db.name}.${snowflake_schema.utils.name}.TABLE_REGISTRY"
  query   = "SELECT COUNT(*) FROM ${snowflake_database.replica_db.name}.${snowflake_schema.utils.name}.TABLE_REGISTRY"
}

resource "snowflake_execute" "sync_log" {
  execute = <<-SQL
    CREATE TABLE ${snowflake_database.replica_db.name}.${snowflake_schema.utils.name}.SYNC_LOG (
      LOG_ID INTEGER AUTOINCREMENT PRIMARY KEY,
      TABLE_ID VARCHAR(200) NOT NULL,
      SYNC_STATUS VARCHAR(500),
      SYNC_RECORDS INTEGER,
      SYNC_DURATION_SEC FLOAT,
      NEW_WATERMARK VARCHAR(100),
      CDC_ROWS INTEGER,
      LOGGED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
    )
  SQL
  revert  = "DROP TABLE IF EXISTS ${snowflake_database.replica_db.name}.${snowflake_schema.utils.name}.SYNC_LOG"
  query   = "SELECT COUNT(*) FROM ${snowflake_database.replica_db.name}.${snowflake_schema.utils.name}.SYNC_LOG"

  depends_on = [snowflake_execute.table_registry]
}

# =============================================================================
# Secret
# =============================================================================

resource "snowflake_execute" "pg_secret" {
  execute = <<-SQL
    CREATE SECRET ${snowflake_database.replica_db.name}.${snowflake_schema.public.name}.PG_SECRET
      TYPE = PASSWORD
      USERNAME = '${var.pg_username}'
      PASSWORD = '${var.pg_password}'
  SQL
  revert  = "DROP SECRET IF EXISTS ${snowflake_database.replica_db.name}.${snowflake_schema.public.name}.PG_SECRET"
  query   = "DESCRIBE SECRET ${snowflake_database.replica_db.name}.${snowflake_schema.public.name}.PG_SECRET"

  depends_on = [snowflake_schema.public]
}

# =============================================================================
# Network Rule
# =============================================================================

resource "snowflake_execute" "pg_network_rule" {
  execute = <<-SQL
    CREATE NETWORK RULE ${snowflake_database.replica_db.name}.${snowflake_schema.public.name}.PG_NETWORK_RULE
      TYPE = HOST_PORT
      MODE = EGRESS
      VALUE_LIST = ('${var.pg_host}:5432')
  SQL
  revert  = "DROP NETWORK RULE IF EXISTS ${snowflake_database.replica_db.name}.${snowflake_schema.public.name}.PG_NETWORK_RULE"
  query   = "DESCRIBE NETWORK RULE ${snowflake_database.replica_db.name}.${snowflake_schema.public.name}.PG_NETWORK_RULE"

  depends_on = [snowflake_schema.public]
}

# =============================================================================
# External Access Integration
# =============================================================================

resource "snowflake_execute" "pg_integration" {
  execute = <<-SQL
    CREATE EXTERNAL ACCESS INTEGRATION PG_ACCESS_INTEGRATION
      ALLOWED_NETWORK_RULES = (${snowflake_database.replica_db.name}.${snowflake_schema.public.name}.PG_NETWORK_RULE)
      ALLOWED_AUTHENTICATION_SECRETS = (${snowflake_database.replica_db.name}.${snowflake_schema.public.name}.PG_SECRET)
      ENABLED = TRUE
  SQL
  revert  = "DROP INTEGRATION IF EXISTS PG_ACCESS_INTEGRATION"
  query   = "DESCRIBE INTEGRATION PG_ACCESS_INTEGRATION"

  depends_on = [snowflake_execute.pg_secret, snowflake_execute.pg_network_rule]
}

# =============================================================================
# Stage
# =============================================================================

resource "snowflake_execute" "sync_stage" {
  execute = "CREATE STAGE ${snowflake_database.replica_db.name}.${snowflake_schema.utils.name}.SYNC_STAGE"
  revert  = "DROP STAGE IF EXISTS ${snowflake_database.replica_db.name}.${snowflake_schema.utils.name}.SYNC_STAGE"
  query   = "DESCRIBE STAGE ${snowflake_database.replica_db.name}.${snowflake_schema.utils.name}.SYNC_STAGE"

  depends_on = [snowflake_schema.utils]
}

# =============================================================================
# Outputs
# =============================================================================

output "database_name" {
  value = snowflake_database.replica_db.name
}

output "integration_name" {
  value = "PG_ACCESS_INTEGRATION"
}
