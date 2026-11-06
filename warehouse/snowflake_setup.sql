-- One-time Snowflake setup for the Memory Shortage Playbook.
-- Run in a Snowsight worksheet as ACCOUNTADMIN (trial accounts start with this role).
-- Replace the two <PASTE_...> placeholders with the public keys you generate (README step 3).

use role accountadmin;

-- 1. Compute: smallest warehouse, suspends after 60 s idle to save trial credits.
create warehouse if not exists SHORTAGE_WH
  warehouse_size = 'XSMALL' auto_suspend = 60 auto_resume = true initially_suspended = true;

-- 2. Storage: one database, three layers.
create database if not exists MEMORY_SHORTAGE;
create schema if not exists MEMORY_SHORTAGE.RAW;       -- loaded by scripts/load_snowflake.py
create schema if not exists MEMORY_SHORTAGE.STAGING;   -- dbt views
create schema if not exists MEMORY_SHORTAGE.MARTS;     -- dbt tables the app reads

-- 3. Roles: a transformer (loads RAW, runs dbt) and a read-only role for the Streamlit app.
create role if not exists SHORTAGE_TRANSFORMER;
create role if not exists SHORTAGE_READER;
grant role SHORTAGE_TRANSFORMER to role sysadmin;
grant role SHORTAGE_READER to role sysadmin;

grant usage on warehouse SHORTAGE_WH to role SHORTAGE_TRANSFORMER;
grant usage on warehouse SHORTAGE_WH to role SHORTAGE_READER;
grant usage on database MEMORY_SHORTAGE to role SHORTAGE_TRANSFORMER;
grant usage on database MEMORY_SHORTAGE to role SHORTAGE_READER;
grant all privileges on schema MEMORY_SHORTAGE.RAW to role SHORTAGE_TRANSFORMER;
grant all privileges on schema MEMORY_SHORTAGE.STAGING to role SHORTAGE_TRANSFORMER;
grant all privileges on schema MEMORY_SHORTAGE.MARTS to role SHORTAGE_TRANSFORMER;

grant usage on schema MEMORY_SHORTAGE.MARTS to role SHORTAGE_READER;
grant select on all tables in schema MEMORY_SHORTAGE.MARTS to role SHORTAGE_READER;
grant select on future tables in schema MEMORY_SHORTAGE.MARTS to role SHORTAGE_READER;

-- 4. Service users with key-pair auth (no passwords).
create user if not exists SHORTAGE_DBT
  type = service
  default_role = SHORTAGE_TRANSFORMER
  default_warehouse = SHORTAGE_WH
  default_namespace = MEMORY_SHORTAGE.STAGING
  rsa_public_key = '<PASTE_DBT_PUBLIC_KEY>';
grant role SHORTAGE_TRANSFORMER to user SHORTAGE_DBT;

create user if not exists SHORTAGE_APP
  type = service
  default_role = SHORTAGE_READER
  default_warehouse = SHORTAGE_WH
  default_namespace = MEMORY_SHORTAGE.MARTS
  rsa_public_key = '<PASTE_APP_PUBLIC_KEY>';
grant role SHORTAGE_READER to user SHORTAGE_APP;

-- 5. Guardrail: cap trial credit spend on this warehouse.
create resource monitor if not exists SHORTAGE_MONITOR
  with credit_quota = 10 frequency = monthly start_timestamp = immediately
  triggers on 90 percent do suspend on 100 percent do suspend_immediate;
alter warehouse SHORTAGE_WH set resource_monitor = SHORTAGE_MONITOR;

-- Check: should list both users with has_rsa_public_key = true
show users like 'SHORTAGE_%';
