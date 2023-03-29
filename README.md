# PostgreSQL Test Application

PostgreSQL stack tester charm - this is a simple application used exclusively for integrations test of
[postgresql-k8s][postgresql-k8s], [postgresql][postgresql], [pgbouncer-k8s][pgbouncer-k8s],
[pgbouncer][pgbouncer], [postgresql-k8s-bundle][postgresql-k8s-bundle] and
[postgresql-bundle][postgresql-bundle].

## Relations

This charm implements relations interfaces:
* postgresql_client
* pgsql (legacy)

On using the `pgsql` legacy relation interface with either [postgresql] or [postgresql-k8s] charms, its
necessary to config the database name with:

```shell
> juju config postgresql-k8s postgresql-interface-database=continuous_writes_database
```

## Actions

Actions are listed on [actions page](https://charmhub.io/postgresql-test-app/actions)


[postgresql-k8s]: https://charmhub.io/postgresql-k8s?channel=edge
[postgresql]: https://charmhub.io/postgresql?channel=edge
[pgbouncer-k8s]: https://charmhub.io/pgbouncer-k8s?channel=edge
[pgbouncer]: https://charmhub.io/pgbouncer?channel=edge
[postgresql-k8s-bundle]: https://charmhub.io/postgresql-k8s-bundle?channel=edge
[postgresql-bundle]: https://charmhub.io/postgresql-bundle?channel=edge

## References

* [PostgreSQL Test App at Charmhub](https://charmhub.io/postgresql-test-app)
