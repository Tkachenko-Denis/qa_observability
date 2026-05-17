SELECT 'CREATE DATABASE airflow_metadata OWNER dq'
WHERE NOT EXISTS (
  SELECT FROM pg_database WHERE datname = 'airflow_metadata'
)\gexec
