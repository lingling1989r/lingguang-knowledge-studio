# Security

This is a local single-user workbench, not a production multi-tenant SaaS.
Do not expose it directly to the Internet. Host/Origin guards are loopback-only.
Never commit .state/, tokens, API keys, downloaded media or private notes.
RSS outbound DNS validation is not a replacement for network-level egress controls.
Private deployment, tenant OAuth, COS and MCP are design proposals, not shipped features.
For vulnerabilities, avoid posting secrets in public issues; use GitHub private vulnerability reporting if enabled.
