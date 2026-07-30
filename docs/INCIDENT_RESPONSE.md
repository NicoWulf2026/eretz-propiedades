# Incident response

For a secret, data-integrity, or unauthorized-write incident:

1. stop the affected runner and preserve logs;
2. contain only the exact source or capability involved;
3. record timestamps, identifiers, hashes, and counts without secret values;
4. rotate/revoke credentials through an authorized human owner;
5. determine working-tree, history, artifact, database, and deployment scope;
6. restore from a verified backup or apply an auditable forward repair;
7. run security and data-integrity regression checks;
8. close only after containment, eradication, recovery, and owner sign-off.

Do not rewrite shared Git history without a separately approved coordination
plan.

