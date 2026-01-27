#!/bin/bash
cd /Users/jdemlow/github/Snowflake-Postgres/db-api
/Users/jdemlow/miniconda3/envs/snowflake-postgres/bin/python -m pytest tests/ -v --ignore=tests/test_integration.py
