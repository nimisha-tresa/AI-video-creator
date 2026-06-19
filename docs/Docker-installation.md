Docker installation guidance

Recommendation

- Preferred: All users — install Docker system-wide (Docker Desktop as Administrator on Windows).
- Rationale: Single Docker daemon for all accounts simplifies image/volume sharing, reduces duplicate disk usage and permission issues, and aligns with CI/ops expectations.

When to choose per-user

- Use per-user only when installers cannot be run as Administrator or strict isolation between user accounts is required.
- Tradeoffs: More disk usage, harder image/volume sharing, duplicated config, and potential service/startup complexity.

Windows-specific notes

- Install Docker Desktop as Administrator.
- After install, add non-admin users to the `docker-users` group so they can run Docker without admin privileges:

```powershell
net localgroup docker-users <username> /add
```

- Enable WSL2 backend if you use Linux toolchains: install WSL 2 and enable integration in Docker Desktop settings.

CI / servers

- For CI and production automation, prefer Docker Engine on Linux hosts. Docker Desktop is appropriate for developer machines.

Licensing

- Check Docker Desktop licensing for commercial/business use before deploying across an organization.

Next steps

- Ask if you want this added into the main README with a short link.
