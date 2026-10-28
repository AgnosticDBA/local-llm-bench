# Morgan Ellery — Database Reliability Engineer (fictional)

*This CV is invented for benchmarking. The person does not exist.*

Utrecht, Netherlands · English (native), Spanish (conversational), Dutch (beginner, A1 evening course)

## Summary

Database reliability engineer with 11 years of production PostgreSQL experience, the last six on AWS.
I keep large transactional databases available, fast and recoverable, and I automate the operational work
so that a small team can run a large estate. Comfortable leading incidents and teaching what I learn.

## Experience

### Staff Database Engineer — Brightwater Payments (fictional), Amsterdam · 2021 – present

- Run 60 PostgreSQL clusters on Amazon RDS and Aurora, holding about 40 TB of payment data.
- Designed a cross-region disaster-recovery setup and ran quarterly restore drills that cut recovery time from four hours to 35 minutes.
- Lead engineer in the database on-call rotation; wrote the incident runbooks the team uses today.
- Wrote Terraform modules that provision every RDS instance, parameter group and alarm, reviewed by a team of six.
- Upgraded 40 clusters from PostgreSQL 12 to 15 using logical replication, with under five minutes of downtime each.
- Built Prometheus exporters and Grafana dashboards for replication lag, bloat and connection saturation.
- Reduced monthly AWS database spend by 22 % by right-sizing instances and moving cold data to S3.

### Senior Database Administrator — Kestrel Logistics (fictional), Utrecht · 2017 – 2021

- Operated self-managed PostgreSQL 9.6–11 clusters on EC2 with Patroni and etcd for automatic failover.
- Wrote Python tooling for backup verification, vacuum scheduling and schema-change checks.
- Tuned slow queries with product teams, cutting the p95 latency of the booking API from 900 ms to 140 ms.
- Mentored three junior DBAs, two of whom now lead their own teams.
- Wrote the business case for retiring the last SQL Server reporting instance; another team carried out the migration.

### Database Administrator — Norrland Telecom (fictional), Stockholm · 2013 – 2017

- Administered Oracle 11g and PostgreSQL 9.x databases for billing systems.
- Automated nightly backup checks with shell scripts and cron.

## Skills

- PostgreSQL internals, replication, Patroni, pgBackRest, logical replication
- AWS: RDS, Aurora, EC2, S3, CloudWatch
- Terraform, Ansible, GitHub Actions
- Python, Bash, SQL
- Prometheus, Grafana, PagerDuty
- Oracle (earlier career)

## Education and certification

- BSc Computer Science, Uppsala University
- AWS Certified Database – Specialty
