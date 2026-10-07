# Security and Data Handling

Do not report real credentials, tokens, private keys, customer records, personal/health/financial records or unsanitized logs through public Issues or PRs. Use synthetic fixtures and redact identifying network/host details.

No private disclosure email or portal is established by this bootstrap. Until the maintainer establishes a private channel, report only a non-sensitive request for secure contact; keep exploit details and sensitive evidence out of public discussion. Do not invent contact information.

If a secret may have been exposed, notify the owner privately through an established channel and revoke/rotate it there. Removing a file in a later commit does not remove historical exposure. History rewriting and visibility changes need a reviewed remediation plan; do not force-push automatically.

Only public-safe, rights-cleared source and sanitized fixtures belong here.

.gitignore is a convenience control, not a secret scanner or access-control boundary. Audit both current contents and reachable history before publication. Review binary/image metadata and embedded records separately from text credential scans. Do not treat a heuristic scan as proof of absence.
