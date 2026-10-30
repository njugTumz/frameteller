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

0. `cd backend && .venv/bin/python scripts/demo_check.py` (about USD 0.003). It wakes the backend, pings Muse
   Spark, SAM 3.1, Voice Transcribe and Azure Text-to-Speech from this machine, and with
   `~/.config/frameteller/admin-production.token` prints today's public and judge budgets and every queue. Add
   `--image` to draw one Muse Image draft (USD 0.01), `--glimmer` to wake Glimmer, `--api staging` for staging.
   Exit code 1 if anything failed.
1. `curl -s https://api.frameteller.com/healthz` → `{"status":"ok"}`. `curl -s https://api.frameteller.com/readyz` → `ready`.
2. `curl -s https://api.frameteller.com/status` → `"paused": false, "full": false`. If `full` is true, the day's
   public cap is spent: see [Daily caps](#daily-caps-by-date). Judges keep their own budget.
3. Open https://app.frameteller.com in the demo browser, allow the microphone, and tell a 20-second test story
   through to two draft panels (about USD 0.05). This checks Voice Transcribe, Spark and Muse Image end to end.
4. Check the Meta Billing page has room under the spend limit, and the Azure budget has no alert today.
5. Nobody pushes to `main` or publishes a release during the demo (CLAUDE.md section 12). The production app only
   changes on a release, but the marketing site redeploys on a push to `main`.
6. Keep the recorded demo video open in another tab as the fallback.

There are no cold starts: production keeps one replica running. A new revision drains the old one for up to
120 s, so a live session or an export in progress finishes during a deploy. If the studio socket drops anyway,
it shows "Updating the studio, your work is safe", refetches the project and carries on.

## Warm Glimmer for launch night, recording and judging

The continuity supervisor's open-weight reviewer, Muse Glimmer, runs on one H100 on Modal (app `frameteller-glimmer`, workspace `geoftums`, [ADR 0013](adr/0013-glimmer-on-modal.md)). It scales to zero after 5 idle minutes. A cold start takes about **3.5 minutes** (measured: 221, 194, 169 and 196 s).

**Cost: USD 3.95 per hour while it is kept warm**, plus about USD 0.35 for the start and the 5-minute scale-down. A 2-hour launch night costs about USD 8.25.

Production runs `REVIEWER=screen` (the GitHub `production` variable), but **visitors never wake the GPU**. Reviews go to Glimmer only while the warm-up script holds a lease on the backend. Without a lease, Spark reviews alone, and the badge says "Checked by Muse Spark". Any request to the Modal endpoint, even `/health`, would start a container, so the backend never asks it whether it is up.

1. **Keep it warm** for the session, starting 10 minutes before. The script wakes Glimmer and checks it answers. Then, every 4 minutes, it sends one tiny request and renews a 10-minute lease on each backend:
   ```bash
   python3 deploy/modal/warm.py --keep 120                     # production, for 2 hours
   python3 deploy/modal/warm.py --keep 60 --api staging        # or staging, for a recording
   python3 deploy/modal/warm.py --keep 90 --api production --api staging
   ```
   Leave the terminal open. Each renewal prints "lease https://api.frameteller.com: warm until …". Badges now say "Checked by Muse Glimmer" for every panel Glimmer passes. Spark decides whatever Glimmer flags ([eval](supervisor-eval.md)).
2. **Stop it:** press Ctrl-C, or let `--keep` run out.
   - The script revokes the leases, so reviews go back to Spark at once.
   - The GPU scales to zero 5 minutes later.
   - If the laptop sleeps or the script dies, the lease runs out by itself within 10 minutes. No visitor review can wake Glimmer after that.
3. **If Glimmer fails during a lease** (a timeout over `GLIMMER_TIMEOUT_S`, 20 s, or an error), the backend revokes the lease itself and Spark reviews. The script's next renewal (up to 4 minutes later) brings Glimmer back once it answers again.

To turn Glimmer off completely, set the GitHub `production` variable `REVIEWER` to `spark` and deploy, or switch the running app at once: `az containerapp update -g rg-frameteller-prod -n ca-frameteller-production --set-env-vars REVIEWER=spark`. `modal app stop frameteller-glimmer` stops a running container and undeploys the endpoint; `modal deploy deploy/modal/glimmer.py` brings it back.

**Check the spend:**
- `modal app list` shows whether a container is running.
- The Modal dashboard's Usage page shows GPU time.
- `modal billing report --for today` shows today's cost per app.
- The workspace spend limit (USD 30) stops Glimmer if it runs away, and the supervisor then falls back to Spark.

**Rotate the endpoint token.** It is ours, not a Meta key. Keep it out of shell history and logs:
```bash
umask 077; python3 -c 'import secrets; print(secrets.token_hex(32), end="")' > ~/.config/frameteller/glimmer.token
modal secret create frameteller-glimmer-token GLIMMER_API_KEY="$(cat ~/.config/frameteller/glimmer.token)" --force
modal deploy deploy/modal/glimmer.py
gh secret set GLIMMER_API_KEY --env staging < ~/.config/frameteller/glimmer.token
gh secret set GLIMMER_API_KEY --env production < ~/.config/frameteller/glimmer.token
```
Then deploy both environments.

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

## The Azure Speech key ("Read it to me")

"Read it to me" uses Azure AI Speech Text-to-Speech with a key ([ADR 0015](adr/0015-script-mode.md)): the
resource (`isaac-maqegffq-eastus2`, region eastus2) is in a tenant our deployment identity cannot see, so keyless
auth is not possible. Without the key the studio still runs and offers narration and the teleprompter.

Store it for both environments, and for local tests and fixture recording, without it ever showing on screen:

```bash
read -s KEY && printf %s "$KEY" | gh secret set AZURE_SPEECH_KEY --env staging -R njugTumz/frameteller \
  && printf %s "$KEY" | gh secret set AZURE_SPEECH_KEY --env production -R njugTumz/frameteller; unset KEY
umask 077; read -s KEY && printf %s "$KEY" > ~/.config/frameteller/speech.key; unset KEY
```

The next deploy passes it to the Container App as the `azure-speech-key` secret. To rotate it, regenerate the
key in the Azure portal (Keys and Endpoint), store it as above and redeploy, or set it in the running app like
the Meta key (`az containerapp secret set ... --secrets "azure-speech-key=$KEY"`). Check it with
`curl -s https://api.frameteller.com/voices | jq .available`.

**The default voice is Ava** (`en-US-AvaMultilingualNeural`) since v1.1.0: for "Read it to me", "Try a sample story"
and a gallery copy "with the Ava voice instead". Projects read before keep the voice they were read in (Brandon),
and their share pages still name it. `curl -s https://api.frameteller.com/voices | jq .default` shows it.

## Spend and errors

| What | Where |
|---|---|
| Meta spend | Meta console, Billing page (the spend limit is set there) |
| Azure spend | Cost Management, budget `budget-frameteller-production` (USD 50/month, emails at 80% and 100%) |
| Today's model spend per call | Application Insights → Logs, below |
| Uptime | Availability test `avail-frameteller-production`: `/healthz` every 5 minutes from 3 locations, emails izotumzybiz@gmail.com when 2 fail |
| Studio state | `GET /status`: `full` means today's public cap is reached. The admin page shows both budgets |

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
`LIMIT_PROJECTS_PER_VISITOR_PER_DAY=3`, `LIMIT_NARRATION_MINUTES_PER_SESSION=3`, `LIMIT_SHOTS_PER_EPISODE=12`,
`LIMIT_RENDERS_PER_PROJECT=60`, `LIMIT_EXPORTS_PER_PROJECT=3`, `LIMIT_EPISODES_PER_SCRIPT=3`,
`LIMIT_SCRIPT_CHARACTERS=4000`, `LIMIT_SPEECH_CHARACTERS_PER_VISITOR_PER_DAY=12000` and, for all visitors
together, `SPEECH_CHARACTERS_PER_DAY=200000` (Text-to-Speech, USD 15 per million characters). Change one for a day with
`az containerapp update --set-env-vars`, like the kill switch.

## The judge pass

Judges get a private link, `https://app.frameteller.com/judge#<JUDGE_TOKEN>` ([ADR 0016](adr/0016-capacity-and-fairness.md)).
The token is in the URL fragment, so it never reaches a log.

- **One link for every judge.** The token is never used up: each browser that opens the link gets its own pass,
  a signed cookie with its own id, valid for 21 days (`JUDGE_PASS_DAYS`). It shows "Judge access" in the top bar.
- **Judges skip** the per-visitor caps and the queues, and spend from their own reserve, which the public cap
  never touches: **USD 25 a day on Nov 5-8** (`JUDGE_BUDGET_DAYS_USD`) and **USD 15 on other days**
  (`JUDGE_BUDGET_PER_DAY_USD`), days at UTC+4.
- **Each pass may start 15 stories a day** (`JUDGE_STORIES_PER_PASS_PER_DAY`). Past that the judge is told their
  stories are saved and new ones open at midnight UTC+4.
- **The admin page** lists today's passes (first seen, stories, spend) and can **lower the reserve at once**
  ("Lower the judges' reserve", no redeploy; "Back to the calendar" clears it). From a terminal:
  `curl -X PUT -H "Authorization: Bearer $(cat ~/.config/frameteller/admin-production.token)" -H 'Content-Type: application/json' -d '{"usd": 5}' https://api.frameteller.com/admin/judge/reserve`

For comparison, the public gets 3 new stories per visitor a day, 5 on Nov 5-8 (`LIMIT_PROJECTS_PER_VISITOR_DAYS`).

Set or rotate the token with `backend/scripts/rotate_token.sh judge production` (see "Rotate the judge or admin
token" below): every pass already given stops working at once. Send the link only in the submission form's
private fields or a direct message. Never commit or post it. Without `JUDGE_TOKEN`, `/judge` answers 404 and
there is no judge lane.

### If the judge link leaks

1. **Lower the reserve first.** On the admin page, set the judges' reserve to a few dollars (or 0 to stop judge
   spending today). It takes effect on the next model call, with no redeploy, and caps what a leaked link can
   cost. Each pass is also held to 15 stories a day.
2. **Look at the passes.** The admin page shows which passes are active today and what each spent. Many new passes
   with heavy spend mean the link is out.
3. **Rotate only before the submission deadline** (Thu Nov 5, 6:00 AM UTC+4), with
   `backend/scripts/rotate_token.sh judge production`, then **update the submission** with the new link.
   After the deadline the judges have the old link and the submission can't change, so keep the token and
   hold spending with the lowered reserve instead.

## The admin page

`https://app.frameteller.com/admin#<ADMIN_TOKEN>` (staging: the staging studio's `/admin#…`). It shows today's budgets per lane, every queue
(in flight, waiting, longest wait), the live sessions, whether Glimmer is warm, and the gallery: pending and
reported entries first, with Watch, Publish, Feature, Hide and Remove. Rotate `ADMIN_TOKEN` with
`backend/scripts/rotate_token.sh admin production` (see below). The token stays in the tab's sessionStorage only. The same token works from a terminal:

```bash
curl -s -H "Authorization: Bearer $(cat ~/.config/frameteller/admin-production.token)" https://api.frameteller.com/admin/overview
```

## Rotate the judge or admin token

```bash
backend/scripts/rotate_token.sh judge production   # or: admin production, judge staging, admin staging
```

The script never prints the token. It:

1. moves `~/.config/frameteller/<kind>-<env>.token` to `<kind>-<env>.token.old` (the old token, in case);
2. writes a new random token (`secrets.token_urlsafe(32)`) to the file, readable by you only;
3. sets the `JUDGE_TOKEN` or `ADMIN_TOKEN` secret of that GitHub environment from the file (`gh secret set`, on stdin);
4. starts the matching deploy: staging deploys `main`; production deploys the **latest release tag**, never
   unreleased code, and waits for approval in the `production` environment.

Once the deploy is live, every judge pass (or admin tab) made with the old token stops working. Build the new
link from the file without echoing it, for example by opening the file in an editor and copying it after
`https://app.frameteller.com/judge#`. For the judge token, update the submission's private field before the
deadline (see "If the judge link leaks"). Run `gh auth status` first: `gh` needs access to the repo's environments.

## Gallery moderation

A submission is checked by the reviewer against [agents/gallery.md](../agents/gallery.md) ([ADR 0017](adr/0017-gallery.md)).
A confident clean pass publishes it; anything else is **pending** until someone looks:

1. Open the admin page. "Needs a look" lists pending entries and anything reported, with the reviewer's note.
2. **Watch** the video, open the share page, then **Publish** or **Remove**. **Feature** puts a published entry
   in the gallery's Featured view; **Hide** takes it out without deleting it.
3. Three reports from different visitors hide a published entry automatically. Check it the same way.

Creators withdraw their own entry from the studio, which deletes it and its video.

## Daily caps by date

The public cap is set per day, counted in UTC+4: `BUDGET_PER_DAY_USD=10` by default, and `BUDGET_DAYS_USD`
raises it on given dates (default `2026-11-02:25,2026-11-05:25,2026-11-06:25,2026-11-07:25,2026-11-08:25`). The
judge reserve comes on top, also by date (see The judge pass). To change a day quickly (a new revision, no redeploy):

```bash
az containerapp update -g $RG -n $APP --set-env-vars "BUDGET_DAYS_USD=2026-11-02:40,2026-11-05:25,2026-11-06:25,2026-11-07:25,2026-11-08:25"
az containerapp update -g $RG -n $APP --set-env-vars JUDGE_BUDGET_PER_DAY_USD=20
```

Then make the same change in `infra/parameters/production.bicepparam` (or the GitHub variable) and commit it,
so the next release keeps it. Raise the Meta Billing spend limit first if the new caps could exceed it.

## Capacity and the waiting room

Limits ([ADR 0016](adr/0016-capacity-and-fairness.md)): `CAPACITY_SESSIONS=24`, `CAPACITY_IMAGES=8`, `CAPACITY_SAM=4`,
`CAPACITY_EXPORTS=2`, `CAPACITY_JOBS=32`. Past a limit, visitors see their place in line. Measured headroom
is in [load-test.md](load-test.md). If the admin page shows long image lines **and no 429s** in the logs,
raise `CAPACITY_IMAGES` (for example to 12). If Meta answers 429, lower it: the calls back off in line anyway.

```kusto
// 429s from Meta in the last hour
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(1h)
| extend line = parse_json(Log_s) | where line.msg == "model call failed" and tostring(line.error) has "rate limited"
| summarize retries = count() by model = tostring(line.model), bin(TimeGenerated, 5m)
```

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
