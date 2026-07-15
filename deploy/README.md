# EventHorizon GCP Deployment

The production stack runs on one Compute Engine VM in `us-central1-a`:

- Caddy serves the React build and proxies REST, WebSocket, and SSE traffic.
- The backend and LangGraph agent are private Docker services.
- PostgreSQL and generated artifacts live on the attached persistent disk.
- GitHub Actions uses Workload Identity Federation; no service-account key is stored in GitHub.
- A billing-budget Pub/Sub topic and authenticated poller stop the VM at 90% of the trial budget, independent of billing-account currency.
- A calendar-based systemd timer stops the VM before the expected trial end as a second guard.

## Required Secret Manager secrets

- `eventhorizon-runtime-env`: full production env based on `.env.production.example`.
- `eventhorizon-firebase-credentials`: the Firebase service-account JSON.

## Operations

```bash
sudo /opt/eventhorizon/deploy/vm/healthcheck.sh
sudo docker compose --env-file /opt/eventhorizon/.env -f /opt/eventhorizon/docker-compose.prod.yml logs --tail=200
sudo docker compose --env-file /opt/eventhorizon/.env -f /opt/eventhorizon/docker-compose.prod.yml restart backend agent
```

Budget notifications are delayed and are not a real-time hard spending cap. The 90% stop threshold leaves buffer below the trial credit, but the billing console remains the source of truth. The VM also has a September 20, 2026 calendar stop ahead of the September 24 credit expiry. Persistent disks, addresses, and registries can still accrue small charges after a VM is stopped, so delete the deployment when the trial ends.
