# B0 / P0 Beta Security — Phase 2: AWS WAF & API Abuse-Protection Design

Status: **DESIGN — awaiting owner approval of rules + cost before provisioning.** Nothing deployed.
Account: beta `224033508028`, us-east-1. Scope: WAF only (no per-user throttling, no AI quotas — Phase 3/4).

## 1. Entry-point audit (verified live)

| Fact | Value |
|---|---|
| App Runner service | `story-beta-api` (`...service/story-beta-api/b4df1f58d93a4ef2ba3b573aafb206c1`) |
| Public hostname | `asxtxgjiis.us-east-1.awsapprunner.com` |
| `IsPubliclyAccessible` | **true** (direct public ingress; no CloudFront, no custom domain) |
| VPC connector | none (default egress) |
| Existing WebACL | none (clean slate) |
| WAFv2 direct association | **supported** — resource type `APP_RUNNER_SERVICE`, REGIONAL scope, us-east-1 |

**Decision: associate a REGIONAL WAFv2 Web ACL DIRECTLY to the App Runner service.** No CloudFront — it adds a hop, a second hostname, cost, and TLS/origin complexity with no benefit for a single-service beta. (CloudFront would only help if we needed edge caching or a custom WAF at the edge; we need neither.)

## 2. Reachable hostnames & bypass analysis (req 2)

- **Only one API entry point:** the App Runner default domain above. A direct WAFv2 association protects the service at its front door, so there is no unprotected origin hostname to bypass to (unlike CloudFront→ALB, where the ALB DNS can leak). App Runner does not expose the underlying compute host.
- **Presigned S3 media (req 5):** `POST /v1/media/initiate|complete|multipart/*` only *issue* presigned URLs; the actual bytes PUT/GET go **directly to `*.s3.amazonaws.com`**, NOT through App Runner. The WAF sits on App Runner, so **large media transfers are structurally unaffected** — no size rule, no rate rule, no managed rule ever sees them. This is the key reason the request-size cap below is safe.
- No second ingress, no websocket, no alternate port.

## 3. Smallest beta Web ACL (req 3)

Default action **ALLOW**; rules evaluated in priority order. Scope REGIONAL.

| # | Rule | Mode at launch | Purpose |
|---|---|---|---|
| 0 | `AWSManagedRulesAmazonIpReputationList` | **Block** | Known malicious/bot source IPs. Low false-positive; safe to block immediately. |
| 1 | `AWSManagedRulesKnownBadInputsRuleSet` | **Block** | Known exploit payloads (Log4j, etc.). Low false-positive; block immediately. |
| 2 | `AWSManagedRulesCommonRuleSet` (CRS) | **Count** → Block after observation | Broad OWASP baseline. Can false-positive on legitimate JSON bodies (the AI endpoints post large creative text), so START IN COUNT (req 4). |
| 3 | Rate-based rule, IP, limit **600 / 5 min** | **Count** → Block | Per-IP flood protection. 600/5min (~2 rps sustained) is generous for a human beta tester but stops scripted abuse. Count first to confirm no legitimate tester trips it. |
| 4 | Request-body size constraint, **> 2 MB → Block** | **Block** | Reject oversized JSON bodies. Safe because media bytes never traverse App Runner (they go to S3); the largest legitimate API body is an asset-understanding multipart of a few contact-sheet JPEGs, well under 2 MB. (If AU multipart approaches the cap we raise this one number — recorded as a tunable.) |

Notes:
- **CRS body-inspection limit:** WAF inspects the first 8 KB of a body by default (or up to 64 KB with an association config on App Runner). The AI endpoints post bodies larger than 8 KB; CRS in Count mode first tells us whether the inspected prefix causes false positives before we block.
- Rules 0,1,4 block at launch (low risk). Rules 2,3 start in **Count** and flip to Block only after we review real beta traffic (req 4).

## 4. Count→Block transition plan (req 4)

1. Deploy with rules 2 (CRS) and 3 (rate) in **Count**; 0,1,4 in Block.
2. Observe ≥ 48–72 h of real beta-tester traffic in the WAF logs + CloudWatch `CountedRequests` per rule.
3. Review Counted samples for false positives (legitimate AI/creative payloads tripping CRS; a tester tripping the rate limit).
4. If clean, flip CRS and the rate rule to **Block** (a one-line CDK `overrideAction`/`action` change + redeploy, its own small PR).
5. Keep a documented rollback (§6).

## 5. Presigned media safety (req 5)

Covered by architecture (§2): media bytes never reach App Runner, so no WAF rule can touch them. The request-size cap (rule 4) applies only to API JSON bodies on App Runner. **Verified:** `media_store` issues presigned PUT/GET; the client transfers to/from S3 directly.

## 6. Logging, redaction, false-positive review, alarms, rollback (req 6, 9)

- **Logging:** WAF logging to a dedicated CloudWatch Logs group `aws-waf-logs-story-beta` (WAFv2 requires the `aws-waf-logs-` prefix). Retention 30 days.
- **Redaction:** redact `authorization` and `cookie` headers in the logging config (`RedactedFields`) so bearer tokens / session values never land in logs (req 6 + Phase 5 #10). Bodies are not logged (only matched-rule metadata).
- **False-positive review:** a saved CloudWatch Logs Insights query over the log group filtering `action="COUNT"` grouped by `terminatingRuleId`, reviewed during the Count window.
- **Alarms (req 9 — REUSE Observability SNS, do NOT create one):** CloudWatch alarms on the WAF `BlockedRequests` and rate-rule `CountedRequests` metrics, with their `alarmAction` pointed at the Observability thread's existing SNS topic **`story-beta-observability-alarms`** (by name/ARN lookup), not a new topic. If that topic is absent at deploy time, the alarms are created without an action (wired in a follow-up) rather than minting a duplicate topic.
- **Emergency disable/rollback:** fastest path is `aws wafv2 disassociate-web-acl --resource-arn <app-runner-arn>` (removes protection in seconds, no redeploy, no data loss) — documented as the break-glass. Full removal is a CDK destroy of the WAF stack. Flipping a single rule back to Count is a small CDK change.

## 7. Cost estimate for a small external beta (req 7)

us-east-1 WAFv2 pricing: $5.00 / Web ACL / month + $1.00 / rule / month + $0.60 / million requests.

| Item | Qty | Monthly |
|---|---|---|
| Web ACL | 1 | $5.00 |
| Rules (2 managed CRS-family + IpRep + KnownBadInputs + rate + size = 5 billable rule slots; managed groups count as 1 each) | ~5 | $5.00 |
| Requests (small beta, est. < 1 M/mo) | < 1 M | < $0.60 |
| WAF logging (CloudWatch Logs ingest/storage, low volume) | — | ~$1–3 |
| **Total** | | **~$11–14 / month** |

Negligible for beta. No per-request surprise because media (the high-volume byte path) bypasses WAF.

## 8. Exact CDK resources, IAM, expected diff (req 8)

New **gated** stack `StoryBetaWafStack` (instantiated only with `-c deployWaf=true`, like the other gates), deployed to beta:
- `wafv2.CfnWebACL` (scope REGIONAL, default Allow) with the 5 rules above (managed-rule-group statements + `RateBasedStatement` + `SizeConstraintStatement`).
- `wafv2.CfnWebACLAssociation` (ResourceArn = the App Runner service ARN, WebACLArn = the ACL).
- `wafv2.CfnLoggingConfiguration` → CloudWatch Logs group `aws-waf-logs-story-beta` with `RedactedFields` [authorization, cookie].
- `logs.LogGroup` (retention 30d).
- `cloudwatch.Alarm` × 2 (BlockedRequests, rate CountedRequests) with `alarmAction` → existing Observability SNS topic (looked up by ARN; no topic created here).
- **IAM:** the deploy path already uses the scoped `story-beta-cfn-exec` role; it needs `wafv2:*` (scoped), `logs:CreateLogGroup/PutRetentionPolicy`, `cloudwatch:PutMetricAlarm` added to that role's policy (a small, reviewed addition — called out for approval, not applied yet).
- **Expected CloudFormation diff:** purely additive — 1 WebACL, 1 association, 1 logging config, 1 log group, 2 alarms. **No change** to App Runner, Cognito, DynamoDB, S3, SQS, Lambda, or the worker. The association is the only resource that *references* App Runner (it does not modify it).

## 9. What this increment does NOT do (req 10)

No per-user throttling, no AI quotas — those are Phase 3/4 (application-layer, keyed by `story_user_id`). WAF here is network/IP-layer only.

## STOP — awaiting owner approval

Per the directive: **no WAF is provisioned until the owner reviews these rules and costs.** On approval, the next step is authoring `StoryBetaWafStack` + the `story-beta-cfn-exec` policy addition, a synth + an authoritative `cdk diff` (expected additive-only), then STOP again before the actual deploy.

## 10. Owner amendments resolved (2026-10-21) + CDK implementation

Implemented in `infrastructure/cdk/lib/story-beta-waf-stack.ts` (gated `-c deployWaf=true`), 9 synth tests, full CDK suite 56/56 green. Authoritative beta `cdk diff` = **additive-only** (WebACL, Association, LogGroup, LoggingConfiguration, 2 Alarms + bootstrap-version param). No change to App Runner/Cognito/DynamoDB/S3/SQS/Lambda/auth.

- **Rule 5 (body > 2 MB) now COUNT**, not Block, until real request sizes + WAF inspection limits are observed.
- **Request-body inspection limit (confirmed):** WAFv2 inspects the first 8 KB of a body by default; on App Runner the association supports up to 64 KB with `AssociationConfig`. The size-constraint rule uses `oversizeHandling: CONTINUE` so a body larger than the inspected window is still evaluated by the size rule (it does not silently pass). This is why rule 5 starts in Count — to confirm the AI endpoints' large JSON bodies behave as expected before any blocking.
- **Presigned S3 preserved:** media bytes never traverse App Runner (API only issues presigned URLs); the WAF cannot touch them. Verified in `media_store`.
- **SNS reuse (no duplicate, no silent action-less alarms):** the stack imports the Observability topic ARN via `-c wafAlarmTopicArn=`; if absent, synthesis FAILS loudly. It creates no SNS topic. Both alarms carry the imported SNS action (asserted by test).
- **Least-privilege IAM (no `wafv2:*`):** the WAF stack is a SEPARATE stack deployed through the standard CDK bootstrap CloudFormation execution role — the scoped `story-beta-cfn-exec` role (owned by the api stack) is NOT modified, so the api stack is untouched. If a dedicated scoped WAF-deploy role is later preferred, the minimum actions are: `wafv2:CreateWebACL/GetWebACL/UpdateWebACL/DeleteWebACL`, `wafv2:AssociateWebACL/DisassociateWebACL/ListResourcesForWebACL`, `wafv2:PutLoggingConfiguration/GetLoggingConfiguration/DeleteLoggingConfiguration`, `wafv2:TagResource`, `logs:CreateLogGroup/PutRetentionPolicy/DeleteLogGroup`, `cloudwatch:PutMetricAlarm/DeleteAlarms` — scoped to the beta account/region and the `story-beta-*` resource names where WAFv2 supports resource-level ARNs (WebACL ARN; several wafv2 actions are account/region-scoped only by AWS design).
- **Logs:** `aws-waf-logs-story-beta`, 30-day retention, `authorization`/`cookie`/`x-api-key` headers redacted.
- **Count→Block, false-positive review, rollback:** per §4/§6. Break-glass = `aws wafv2 disassociate-web-acl`.
- **Final cost:** ~$11–14/month (ACL $5 + ~5 rule slots $5 + <$0.60 requests + ~$1–3 logging).

## STOP — final resource/IAM review before provisioning

Deploy command (NOT run yet):
`cdk deploy story-beta-waf -c deployWaf=true -c environment=beta -c appRunnerServiceArn=<arn> -c wafAlarmTopicArn=<observability topic arn>`
The Observability SNS topic must exist first (deploy the observability stack to beta, or pass its ARN). Awaiting owner approval of resources + IAM.
