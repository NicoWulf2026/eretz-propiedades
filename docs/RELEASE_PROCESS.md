# Release process

A release candidate requires passing backend and frontend CI, zero known
high-severity dependency findings, a reviewed additive migration set, a
recovery plan, no unresolved internal scraper errors, and explicit human
approval for production changes.

Tag the exact commit, record artifact hashes, deploy through the normal hosting
environment, verify security headers and public queries, then run a read-only
smoke test. Roll back the application to the prior artifact; handle database
changes through reviewed forward migrations or a tested backup restore.

