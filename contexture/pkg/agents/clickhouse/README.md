# ClickHouse Agent

This directory contains the ClickHouse datasource agent implementation for Contexture.

## Files

- **connector.go** - Main ClickHouse connector implementation for topology collection
- **clickhouse.go** - ClickHouse configuration handling and initialization

## Usage

Set the environment variable to use the ClickHouse connector:

```bash
export CONNECTOR=clickhouse
```

## Configuration

ClickHouse configuration is loaded from `config/clickhouse_config.yaml`:

```yaml
clickhouse_instances:
  - host: localhost
    port: 9000
    username: default
    password: password
    database: default
```

## See Also

- [ClickHouse Documentation](../../../docs/CLICKHOUSE.md)
- [OCS Server](../../ocs)
