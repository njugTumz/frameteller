# Runbook: Frameteller production

What to do before a demo, when something breaks, and when a secret must change. Commands assume `az login` on the
subscription and `gh auth login` on `njugTumz/frameteller`.

| Piece | Where |
|---|---|
| Studio | https://app.frameteller.com (Static Web App `swa-frameteller-app-prod`) |
| API | https://api.frameteller.com (Container App `ca-frameteller-production`, one always-on replica, ADR 0009) |
| Marketing | https://frameteller.com (`swa-frameteller-marketing`, its own workflow) |
| Resource group | `rg-frameteller-prod` (eastus2): storage `stftprod…`, Log Analytics, Application Insights `appi-frameteller-production` |
| Deploys | `deploy-production.yml`: a published GitHub release, approved by njugTumz in the `production` environment |
| DNS | Cloudflare. Every record pointing at Azure is **DNS only (grey cloud)**, so Azure can renew its certificates |

Shell variables used below:

```bash
RG=rg-frameteller-prod APP=ca-frameteller-production
```

## Warm-up before a demo (15 minutes before)

1. `curl -s https://api.frameteller.com/healthz` → `{"status":"ok"}`. `curl -s https://api.frameteller.com/readyz` → `ready`.
2. `curl -s https://api.frameteller.com/status` → `"paused": false, "full": false`. If `full` is true, the day's
   USD 10 cap is spent: see [Spend](#spend-and-errors).
3. Open https://app.frameteller.com in the demo browser, allow the microphone, and tell a 20-second test story
   through to two draft panels (about USD 0.05). This checks Voice Transcribe, Spark and Muse Image end to end.
4. Check the Meta Billing page has room under the spend limit, and the Azure budget has no alert today.
5. Nobody pushes to `main` or publishes a release during the demo (CLAUDE.md section 12). The production app only
   changes on a release, but the marketing site redeploys on a push to `main`.
6. Keep the recorded demo video open in another tab as the fallback.

There are no cold starts: production keeps one replica running. A new revision drains the old one for up to
120 s, so a live session or an export in progress finishes during a deploy. If the studio socket drops anyway,
it shows "Updating the studio, your work is safe", refetches the project and carries on.

## Kill switch

Pause the public studio without a rebuild. Shared storyboards (`/s/...`), probes and `/status` stay up; everything
else shows "Back soon" and live sessions close with 4503.

```bash
az containerapp update -n $APP -g $RG --set-env-vars DEMO_PAUSED=true -o none   # pause
az containerapp update -n $APP -g $RG --set-env-vars DEMO_PAUSED=false -o none  # resume
```

This makes a new revision from the same image (about a minute). Open studio tabs learn about it on their next
request. The next release deploy resets `DEMO_PAUSED` to false, because Bicep owns the environment variables.

## Roll back

The app runs in single-revision mode, so a rollback is a deploy of the previous image. Each image is tagged with
its commit SHA.

```bash
az containerapp revision list -n $APP -g $RG --query "[].{name:name,created:properties.createdTime,image:properties.template.containers[0].image,active:properties.active}" -o table
az containerapp update -n $APP -g $RG --image ghcr.io/njugtumz/frameteller-backend:<previous sha> -o none
curl -s https://api.frameteller.com/readyz
```

To roll back the studio too, run **Deploy production** (`workflow_dispatch`) from the previous release tag, and
approve it:

```bash
gh workflow run deploy-production.yml --ref v0.9.0
```

That redeploys both the backend and the studio from the tag. Use the image swap above when only the backend is
broken and every minute counts.

## Rotate the Meta key

Do this at once if the key may have leaked (it starts with `LLM_`; never paste it into a chat, a log or a commit).

1. In the Meta console, create a key `frameteller-production-<date>`.
2. Store it for future deploys, without it ever showing on screen:
   ```bash
   read -s KEY && printf %s "$KEY" | gh secret set MODEL_API_KEY --env production -R njugTumz/frameteller; unset KEY
   ```
3. Put it in the running app (a new revision picks it up):
   ```bash
   read -s KEY && az containerapp secret set -n $APP -g $RG --secrets "model-api-key=$KEY" -o none; unset KEY
   az containerapp update -n $APP -g $RG --set-env-vars KEY_ROTATED_AT=$(date -u +%Y%m%dT%H%M) -o none
   ```
4. Tell a 10-second test story, then delete the old key in the Meta console.

Staging has its own key in the `staging` environment; rotate it the same way with `--env staging` and
`ca-frameteller-staging` in `rg-frameteller-staging`.

## Spend and errors

| What | Where |
|---|---|
| Meta spend | Meta console, Billing page (the spend limit is set there) |
| Azure spend | Cost Management, budget `budget-frameteller-production` (USD 50/month, emails at 80% and 100%) |
| Today's model spend per call | Application Insights → Logs, below |
| Uptime | Availability test `avail-frameteller-production`: `/healthz` every 5 minutes from 3 locations, emails izotumzybiz@gmail.com when 2 fail |
| Studio state | `GET /status`: `full` means today's global cap (USD 10) is reached |

```kusto
// Model calls today: cost and failures per model
ContainerAppConsoleLogs_CL
| where TimeGenerated > startofday(now())
| extend line = parse_json(Log_s) | where line.msg == "model call"
| summarize calls = count(), usd = sum(todouble(line.cost_usd)), failed = countif(tobool(line.ok) == false) by model = tostring(line.model)

// Errors in the last hour, with the request and project ids
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(1h)
| extend line = parse_json(Log_s) | where line.level in ("ERROR", "WARNING")
| project TimeGenerated, line.msg, line.request_id, line.project_id, line.error
```

The public-demo limits are settings (defaults shown): `BUDGET_PER_DAY_USD=10`,
`LIMIT_PROJECTS_PER_VISITOR_PER_DAY=3`, `LIMIT_NARRATION_MINUTES_PER_SESSION=3`, `LIMIT_SHOTS_PER_PROJECT=12`,
`LIMIT_RENDERS_PER_PROJECT=30`, `LIMIT_EXPORTS_PER_PROJECT=3`. Change one for a day with
`az containerapp update --set-env-vars`, like the kill switch.

## When Meta's API is down

Symptoms: "circuit opened" warnings in the logs, the studio says the model is busy (503 `model_busy`) or slow
(504 `model_timeout`), panels stay "Drawing…". `/healthz` and `/readyz` stay green: probes never call Meta.

1. Confirm: check the Meta status page and Discord #office-hours or #questions, and the error query above.
2. Short outage (minutes): do nothing. Calls retry with backoff, and each model's circuit breaker tries again
   after its cooldown. Breakers are per model, so a SAM outage does not stop narration or drawing.
3. Longer outage, or during a live demo: turn on the [kill switch](#kill-switch) so visitors see "Back soon" rather
   than errors, and show the recorded demo video. Shared storyboards and exported animatics keep working, because
   they are served from our storage.
4. Once Meta recovers, turn the kill switch off and do the warm-up test story.

## Custom domains and certificates

`api.frameteller.com` uses a managed certificate on the Container Apps environment. `app.frameteller.com` and
`frameteller.com` use Static Web Apps certificates. Azure renews them by itself, as long as the Cloudflare records
stay **DNS only**: a proxied (orange cloud) record breaks validation and the renewals.

| Type | Name | Content |
|---|---|---|
| TXT | `asuid.api` | the environment's `customDomainVerificationId` (Bicep output) |
| CNAME | `api` | `ca-frameteller-production.<env>.eastus2.azurecontainerapps.io` |
| CNAME | `app` | the production Static Web App's default hostname |

The certificate name is the GitHub `production` variable `API_CERTIFICATE_NAME`; Bicep keeps the binding on every
deploy.

## After the submission

Tag `v1.0-submission` and freeze: no deploys to production and no commits to `main` until judging ends on Nov 16.
Later work goes on a branch. The kill switch and a rollback are the only changes allowed, and only to keep the
demo up.
