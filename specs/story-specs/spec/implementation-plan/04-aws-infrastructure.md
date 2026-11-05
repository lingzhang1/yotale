# Story --- AWS Infrastructure

**Document:** `04-aws-infrastructure.md`\
**Status:** MVP v0.1 --- AWS Deployment Baseline\
**Related specs:** `03-system-architecture.md`, `mvp-build-plan.md`,
`02-core-story-schema.md`

## 1. Purpose

This document defines how Story's cloud components are deployed to AWS.

It covers:

-   AWS services used by the MVP
-   AWS CDK organization
-   stack/resource boundaries
-   environments
-   API deployment
-   temporary media storage
-   secrets
-   IAM
-   observability
-   operational state
-   asynchronous expansion
-   deployment workflow
-   local development
-   explicit infrastructure non-goals

It does **not** redefine Story product behavior or domain-engine
responsibilities.

`03-system-architecture.md` remains the source of truth for system
boundaries.

## 2. Infrastructure Principles

1.  **Everything cloud-side is provisioned with CDK.**
2.  **CDK is written in TypeScript.**
3.  **Application/backend code is Python.**
4.  **Consumer iOS remains native Swift.**
5.  **Start serverless and simple.**
6.  **Logical engines are not AWS microservices.**
7.  **Original user media remains on-device by default.**
8.  **S3 stores only temporary/cloud-required media for MVP.**
9.  **Least-privilege IAM.**
10. **Dev/staging/prod use the same CDK definitions with environment
    configuration.**
11. **Infrastructure must not leak AWS-specific types into domain
    engines.**
12. **Introduce queues/containers only when workload characteristics
    require them.**

## 3. Initial AWS Topology

``` text
                         Native iOS App
                               │
                               │ HTTPS / SSE
                               ▼
                    ┌────────────────────────┐
                    │   AWS App Runner       │
                    │   Python / FastAPI     │
                    │   Story API            │
                    │   + orchestration      │
                    └──────┬─────┬───────────┘
                           │     │
               ┌───────────┘     └────────────┐
               ▼                              ▼
       ┌──────────────┐               ┌───────────────┐
       │ Amazon       │               │ Model Gateway │
       │ S3           │               └───────┬───────┘
       │ temp media   │                       │
       └──────────────┘              ┌────────┴─────────┐
                                     ▼                  ▼
                              Amazon Bedrock      External AI
                                                   providers

                    Optional operational services
                    ┌─────────────────────────────┐
                    │ DynamoDB                    │
                    │ Secrets Manager             │
                    │ CloudWatch                  │
                    │ SQS → Lambda / Fargate      │
                    │       worker (when needed)  │
                    └─────────────────────────────┘
```

## 4. MVP AWS Services

### Required baseline

-   **AWS App Runner** --- always-on managed container runtime for the
    Story API. Supports SSE natively, no cold starts, no VPC required,
    120-second request timeout. Auto-scales on concurrency.
-   **Amazon ECR** --- container image registry for the App Runner
    service image.
-   **Amazon S3** --- private temporary media/proxy objects.
-   **AWS IAM** --- service permissions.
-   **AWS Secrets Manager** --- external provider secrets and sensitive
    configuration.
-   **Amazon CloudWatch** --- logs, metrics, alarms.
-   **AWS CDK** --- infrastructure definition and deployment.

### Add when actually needed

-   **Amazon SQS** --- async job queue when operations exceed 120s or
    must run outside the request path.
-   **AWS Lambda** --- SQS consumer for bounded async jobs (up to 15
    min, 10GB memory).
-   **Amazon DynamoDB** --- async job state, idempotency records,
    operational metadata when server-side state becomes required.
-   **Amazon ECS/Fargate** --- worker tasks that exceed Lambda's limits
    (long video analysis, generative media, GPU workloads).
-   **Amazon EventBridge** --- scheduled cleanup if S3 lifecycle is
    insufficient.
-   **AWS Batch** --- future batch-heavy media/ML workloads.
-   **Amazon Bedrock** --- AWS-hosted model access where model
    quality/capability fits the task.
-   **Amazon API Gateway** --- add in front of App Runner only if
    fine-grained throttling, WAF, or request transformation is required.

Do not provision services solely because they may be useful someday.

## 5. CDK Repository Structure

``` text
infrastructure/cdk/
├── bin/
│   └── story.ts
├── lib/
│   ├── story-app.ts
│   ├── stacks/
│   │   ├── story-api-stack.ts
│   │   ├── story-storage-stack.ts
│   │   └── story-observability-stack.ts
│   └── constructs/
│       ├── story-api.ts
│       ├── story-backend.ts
│       ├── temporary-media-bucket.ts
│       └── story-observability.ts
├── config/
│   ├── development.ts
│   ├── staging.ts
│   └── production.ts
├── test/
├── cdk.json
├── package.json
└── tsconfig.json
```

This is a starting structure, not a requirement to create three
CloudFormation stacks immediately.

For the earliest MVP, a single deployable stack is acceptable if it
remains readable. Split stacks when ownership, deployment lifecycle, or
CloudFormation limits justify it.

## 6. Stack Boundaries

Preferred conceptual boundaries:

### Storage

Owns:

-   temporary media S3 bucket
-   lifecycle policies
-   encryption
-   CORS if required for direct signed uploads

### API

Owns:

-   App Runner service
-   ECR repository
-   App Runner IAM role and instance role
-   optional DynamoDB operational table
-   optional SQS queues and Lambda worker

### Observability

Owns or configures:

-   log retention
-   alarms
-   dashboards if useful
-   error/latency metrics

Do **not** create:

``` text
StoryEngineStack
DirectorEngineStack
AssetEngineStack
MusicEngineStack
EditEngineStack
```

Those are code/domain boundaries, not deployment boundaries.

## 7. Environments

Use at least:

``` text
development
staging
production
```

Local development is not an AWS environment.

Each deployed environment should have isolated resources.

Example naming:

``` text
story-development-api
story-staging-api
story-production-api
```

Avoid hard-coding resource names when CloudFormation-generated names are
sufficient.

Environment configuration may include:

-   model selection
-   logging level
-   feature flags
-   upload limits
-   temporary media retention
-   external provider endpoints
-   allowed app/API versions

Never store secrets in environment config files committed to Git.

## 8. AWS Accounts

For a very early prototype, one AWS account with isolated stacks is
acceptable.

Before production or external beta, prefer stronger isolation:

``` text
non-production AWS account
production AWS account
```

If the team already has a multi-account AWS setup, use it rather than
creating Story-specific account machinery.

CDK code should not assume a single fixed account ID.

## 9. Regions

Choose one primary AWS region for MVP and keep the system single-region.

Selection should consider:

-   proximity to initial users
-   Bedrock model availability
-   required AWS services
-   data/privacy constraints

Do not implement multi-region active-active for MVP.

Region is CDK/environment configuration.

## 10. App Runner HTTPS Endpoint

App Runner exposes a managed HTTPS endpoint automatically. There is no
API Gateway, load balancer, or ingress layer required for MVP.

The App Runner service URL is the API base URL used by the iOS app.

API paths remain domain-oriented:

``` text
/v1/creative-intent
/v1/direct/*
/v1/stories/*
/v1/assets/*
/v1/music/*
/v1/edits/*
/v1/uploads/*
```

Never expose model-provider-specific routes (e.g. `/openai/chat`).

Add API Gateway in front of App Runner only if fine-grained throttling,
WAF integration, or request transformation becomes necessary. That is a
future addition, not a baseline requirement.

## 11. App Runner Backend

The Story API runs as a containerized Python application on AWS App
Runner.

App Runner pulls the image from Amazon ECR, manages the container
lifecycle, and exposes an HTTPS endpoint automatically. There is no API
Gateway, no load balancer, and no VPC to configure.

Request flow:

``` text
HTTPS request from iOS
      ↓
App Runner (container)
      ↓
FastAPI router
      ↓
application orchestrator
      ↓
Story/Director/Asset/Music/Edit engines (Python modules)
      ↓
Model Gateway
```

Domain engines must be callable in ordinary Python tests without AWS.
The backend is packaged as a single container image initially.

Do not create separate App Runner services per engine. Engines are code
modules, not deployment boundaries.

### Request timeout

App Runner enforces a **120-second hard request timeout**.

Design for this:

- Interactive AI operations (scene scan, shot plan, story ideas) must
  complete in well under 120s — typically 5-25s
- `AssetUnderstanding` runs as an **on-device persistent job queue** (MVP, FROZEN —
  `06-asset-understanding.md`): a small 24-frame request to the existing App Runner
  `/v1/asset-understanding` endpoint, opportunistic/resumable, result cached locally. It is NOT an
  eager server-side cloud dispatch and NOT a Create-My-Story fan-out. No temp-S3 / presigned upload
  / SQS / Lambda-Fargate worker / Bedrock async for AU; that scaling guidance applies to OTHER
  future heavy jobs only.
- Bedrock calls for multiple Moments must run **concurrently** (fan-out),
  not serially; see the OPS/Metrics section in `03-system-architecture.md`
- Any operation that cannot reliably complete in 90 seconds must be
  dispatched to the async worker (SQS → Lambda) rather than stretching
  the synchronous path

### Async worker

A separate Lambda function consumes an SQS queue for jobs that cannot
run in the request path. The worker uses the same Python engine
interfaces as the App Runner service. Deploy it only when workload
characteristics require it.

If a worker job exceeds Lambda's 15-minute timeout or 10GB memory,
replace that specific job with an ECS Fargate task. Engine interfaces
remain unchanged.

## 12. FastAPI on App Runner

FastAPI is the HTTP framework. It runs directly in the App Runner
container with no adapter layer required.

This gives:

- native SSE for streaming Director/Story Engine responses
- OpenAPI generation
- Pydantic request/response validation
- no Lambda event translation complexity
- straightforward local development (`uvicorn` directly)

Migration path if needed later:

``` text
Today:
App Runner → FastAPI

If fine-grained throttling/WAF needed:
API Gateway → App Runner → FastAPI

If heavy compute requires its own service:
SQS → ECS Fargate task → same Python engine interfaces
```

No engine rewrites are required at any migration step.

## 13. App Runner Configuration

Configure per environment:

-   ECR image URI
-   CPU and memory (start at 1 vCPU / 2GB; scale up from measurements)
-   concurrency (default 100 requests per instance)
-   health check path (`/health`)
-   environment variables (non-secret config)
-   Secrets Manager ARNs for sensitive values
-   CloudWatch log group

Do not over-provision CPU/memory globally because future workloads may
need more. Measure first.

Heavy processing belongs in the async worker path, not in a larger App
Runner instance.

## 14. Temporary Media Bucket

Use a dedicated private S3 bucket for media that must temporarily leave
the phone.

Properties:

-   Block Public Access enabled
-   encryption at rest
-   TLS-only bucket policy
-   lifecycle expiration
-   no permanent public URLs
-   object keys are opaque
-   environment isolation

Suggested object namespace:

``` text
temporary/
  <opaque-request-or-upload-id>/
    <opaque-object-id>
```

Do not include:

-   user names
-   Story titles
-   location descriptions
-   original filenames when unnecessary

in S3 keys.

## 15. S3 Retention

Temporary objects should expire automatically.

Initial target:

``` text
hours to a few days
```

rather than indefinite storage.

Choose the exact retention based on retry requirements and provider
workflow.

Deletion must not rely only on application cleanup; configure S3
Lifecycle as the safety mechanism.

## 16. Presigned Upload Flow

Preferred flow:

``` text
iOS
 │
 │ POST /v1/uploads
 ▼
Story API
 │
 │ authorize/validate request
 │ create opaque upload key
 │ generate presigned URL
 ▼
iOS
 │
 │ upload proxy directly
 ▼
S3
 │
 ▼
backend/model processing
 │
 ▼
structured result
```

Benefits:

-   media bytes do not pass through the App Runner service
-   lower backend memory/bandwidth usage
-   simpler large-object handling

Presigned URLs should:

-   expire quickly
-   allow only required operation
-   target one object key
-   enforce expected content constraints where practical

## 17. Media Processing Rule

S3 is not the user's Story library.

The normal lifecycle is:

``` text
device original
→ local proxy/sample
→ temporary S3 object
→ model/processing
→ structured result
→ local cache of result
→ S3 expiration
```

Permanent original uploads require a future explicit
product/architecture decision.

## 18. DynamoDB

DynamoDB is optional initially.

Introduce it when server-side state is actually required.

Suitable MVP uses:

-   idempotency records
-   async Job records
-   temporary upload metadata
-   operational request state
-   rate-limit/supporting metadata

Do not mirror every local Story/Moment/Asset into DynamoDB.

A possible future single-table or small-table design should be written
only when these requirements become real.

## 19. SQS and Async Jobs

Do not require SQS for the first walking skeleton.

Introduce SQS when work becomes:

-   too slow for an interactive request
-   bursty
-   retry-sensitive
-   independent of the user's open app session

Future path:

``` text
API
 │
 ▼
create Job record
 │
 ▼
SQS
 │
 ▼
Python worker
 │
 ├── Lambda for bounded jobs
 │
 └── ECS/Fargate for heavy jobs
 │
 ▼
update Job
```

Use dead-letter queues for production async queues.

## 20. Heavy Compute

Lambda is not the permanent answer for every Story workload.

Potential future workloads:

-   long-video understanding
-   batch frame extraction
-   hundreds/thousands of assets
-   generative video
-   GPU-dependent processing
-   large local-library cloud analysis

When needed:

``` text
API → SQS → ECS/Fargate or AWS Batch
```

The Python engine interface should remain the same regardless of
execution environment.

## 21. Model Gateway and Bedrock

Model Gateway is the only backend module that knows provider-specific
model APIs.

It may route to:

``` text
Amazon Bedrock
external approved AI providers
```

Bedrock is preferred when it provides the required capability/quality
and simplifies security/operations, but Story must not be
architecturally locked to Bedrock.

The domain sees tasks such as:

``` text
generate structured StoryPlan
analyze scene images
analyze asset proxy
```

not provider model IDs.

## 22. External AI Providers

If a required model is outside AWS:

``` text
App Runner backend
→ Model Gateway
→ external HTTPS API
```

Provider credentials live in Secrets Manager.

Do not route external provider traffic through the iOS app.

Before external beta, document which providers receive:

-   user text
-   image proxies
-   video proxies
-   metadata

and review their retention/training/privacy terms.

## 23. Secrets Manager

Store sensitive values such as:

-   external AI API keys
-   provider credentials
-   webhook secrets if introduced

Do not store ordinary non-sensitive configuration in Secrets Manager
unnecessarily.

The App Runner service and any Lambda workers receive only the secrets
they need, injected via IAM role at runtime.

Do not place secrets in:

-   Git
-   CDK source
-   iOS app
-   CloudFormation outputs
-   logs

## 24. IAM

Use least privilege.

Examples:

The App Runner service instance role may need:

-   `s3:PutObject` / presign-related access to the temporary media bucket
-   `s3:GetObject` for processing inputs
-   Bedrock invoke permissions for selected models
-   read access to required Secrets Manager secrets
-   DynamoDB / SQS permissions only if those resources are enabled

The Lambda async worker role may need:

-   `sqs:ReceiveMessage`, `sqs:DeleteMessage` on the job queue
-   `s3:GetObject` / `s3:PutObject` on the output bucket
-   DynamoDB write access for job state updates

Avoid broad policies such as:

``` text
Action: "*"
Resource: "*"
```

except where an AWS service genuinely requires a narrowly justified
wildcard.

Each future worker should receive its own execution role if its
permissions differ materially.

## 25. Encryption

Baseline:

-   HTTPS/TLS in transit
-   S3 encryption at rest
-   DynamoDB encryption at rest
-   Secrets Manager encryption
-   CloudWatch-managed encryption defaults unless stricter requirements
    emerge

Use AWS-managed keys initially unless customer-managed KMS keys are
required by security/privacy needs.

Do not add KMS complexity without a concrete requirement.

## 26. CloudWatch

Capture:

-   App Runner 5xx / 4xx rate
-   App Runner request latency (p50 / p95 / p99)
-   App Runner request timeout count (502s approaching 120s limit)
-   model-operation latency
-   model failures
-   structured-output validation failures
-   temporary upload failures
-   Lambda worker errors and duration (when SQS worker is enabled)

Application logs should include a correlation/request ID.

Do not log raw photos/videos.

Avoid logging full user prompts/descriptions unless explicitly needed
and reviewed.

## 27. Alarms

Before staging/external beta, create basic alarms for:

-   elevated App Runner 5xx rate
-   App Runner p99 latency approaching 90 seconds (pre-timeout warning)
-   App Runner request timeouts (502 from 120s breach)
-   model/AI operation errors
-   abnormal latency on AI calls
-   async dead-letter queue depth if SQS exists

Avoid building a large observability platform before real usage.

## 28. Cost Visibility

Tag AWS resources with:

``` text
Project=Story
Environment=<development|staging|production>
ManagedBy=CDK
```

Where practical, track AI provider cost separately from AWS
infrastructure cost.

Cost-sensitive resources to watch:

-   App Runner vCPU / memory hours
-   S3 storage / transfer
-   Bedrock inference
-   external model APIs
-   Lambda worker duration / memory (when enabled)
-   future container jobs

The likely early cost driver is AI inference rather than App Runner
infrastructure.

## 29. Networking

Do not place App Runner in a VPC by default.

App Runner reaches AWS services (S3, Secrets Manager, Bedrock, DynamoDB)
and external AI APIs over public endpoints without a VPC.

A VPC adds NAT gateway cost (~$32/mo) and configuration complexity.

Introduce VPC networking only when a concrete private-resource
requirement exists (e.g. a Lambda worker needing access to an RDS
instance in a private subnet).

## 30. CORS

The native iOS application does not require browser CORS in the same way
a web frontend does.

Do not broadly enable `*` CORS just because API Gateway examples do so.

S3 CORS should be added only if the actual upload mechanism/client
requires it.

## 31. Authentication

MVP has no mandatory user account.

Do not introduce Cognito merely because the system runs on AWS.

Use the local anonymous identity and application-level request strategy
defined in `03-system-architecture.md`.

If abuse prevention requires stronger anonymous attestation later,
design that separately.

Cognito/account infrastructure should be introduced only when product
requirements require accounts.

## 32. Rate Limiting and Abuse Control

Before public exposure:

-   configure App Runner concurrency limits appropriately
-   enforce request and media size limits in FastAPI middleware
-   validate content types at the application layer
-   enforce per-installation / per-request quotas if necessary
-   protect expensive AI operations from unbounded retries

If WAF or fine-grained throttling is required, add API Gateway in front
of App Runner at that point.

Do not depend on client UI alone to protect expensive endpoints.

## 33. CDK Constructs vs Stacks

Use constructs to encapsulate reusable resource patterns.

Example:

``` text
TemporaryMediaBucket construct
├── private S3 bucket
├── lifecycle expiration
├── encryption
└── access helpers
```

Stacks represent deployment/lifecycle boundaries.

Do not turn every construct into a separate stack.

## 34. CDK Dependency Direction

Allowed:

``` text
infrastructure/cdk
→ references built Python artifact locations
→ provisions AWS resources
→ injects configuration into runtime
```

Disallowed:

``` text
Python Story Engine
→ imports CDK

Python Director Engine
→ imports CloudFormation/CDK types

Swift iOS
→ imports CDK-generated runtime code as domain logic
```

AWS adapters may live at the backend infrastructure/application edge,
not in core engines.

## 35. CDK Outputs

Useful non-secret outputs may include:

-   API base URL
-   environment name
-   region

Do not output:

-   secrets
-   presigned URLs
-   private object keys unnecessarily

The iOS development/staging build configuration may consume the deployed
API base URL through build configuration, not hard-coded source edits.

## 36. Local Development

Developers should be able to run the Python application locally without
deploying AWS for every code change.

Preferred loop:

``` text
local FastAPI
+ mock engines
+ optional real Model Gateway
+ local/test media fixtures
```

AWS-specific integration tests can target the development stack.

Do not require LocalStack unless it proves materially useful; native
mocks/fakes are simpler for most domain tests.

## 37. Development Deployment

The development AWS environment supports integration testing of:

-   App Runner service deployment
-   ECR image build and push
-   S3 presigned uploads
-   IAM roles and permissions
-   Secrets Manager injection
-   Bedrock model calls
-   DynamoDB / SQS when enabled

It should not contain irreplaceable user data.

Developers should be able to destroy/redeploy it safely.

## 38. Staging

Staging should resemble production topology.

Use it for:

-   TestFlight integration
-   real AI provider testing
-   end-to-end temporary media
-   privacy/security verification
-   performance measurements
-   deployment verification

Staging data is not production data.

## 39. Production

Production differs primarily through configuration and isolation, not a
separate hand-written infrastructure implementation.

Production should have:

-   stricter alarms
-   appropriate log retention
-   protected secrets
-   deployment controls
-   production provider credentials
-   production throttles/quotas
-   explicit S3 retention
-   backup settings for any persistent server-side state that becomes
    important

## 40. CI/CD

Initial pipeline concept:

``` text
pull request
→ Python tests
→ contract tests
→ CDK tests
→ CDK synth
→ build backend artifact
→ deploy development

main/release
→ tests
→ synth
→ deploy staging
→ verification
→ controlled production deploy
```

The exact CI provider is not architecturally important.

Do not auto-deploy production from arbitrary branches.

## 41. CDK Bootstrap

Each target account/region must be CDK-bootstrapped.

Bootstrap is environment setup, not Story application behavior.

Document the bootstrap command and required deployment role once the AWS
accounts/regions are chosen.

Do not commit account credentials.

## 42. Contract Deployment

OpenAPI/JSON Schema remains source-controlled under `contracts/`.

The deployment pipeline should fail if:

-   backend responses violate required schemas
-   OpenAPI generation is inconsistent where contract checks are
    enforced
-   contract tests fail

CDK should not become the source of API semantics.

## 43. Container Image Packaging

Package the Python backend as a Docker container image pushed to Amazon
ECR. App Runner pulls from ECR on each deploy.

The image should include:

-   `apps/api`
-   required Python engine packages
-   required runtime dependencies

Do not include in the image:

-   Figma prototype
-   specs
-   iOS source
-   unnecessary test fixtures
-   CDK node modules

Use a multi-stage Dockerfile: build dependencies in one stage, copy only
the runtime artifact to the final stage to minimize image size.

If the image becomes very large, evaluate splitting the async worker
into a separate, smaller image rather than fragmenting domain engines
prematurely.

## 44. Media Upload Limits

Set explicit limits for temporary uploads.

The client should generate task-appropriate proxies before upload.

The API should reject unsupported types/sizes.

Do not make the first implementation accept arbitrary full-resolution
video simply because S3 supports large objects.

## 45. S3 Event Processing

Do not automatically attach a complex S3-event pipeline to every upload.

For MVP, the application may explicitly initiate processing after
upload.

Introduce S3 event notifications only when asynchronous upload-triggered
processing becomes useful.

This keeps request/job semantics visible in the application layer.

## 46. Cleanup

Primary cleanup:

-   S3 Lifecycle expiration

Optional cleanup:

-   application deletes temporary object after successful processing

Lifecycle remains the safety net if application cleanup fails.

DynamoDB job/upload records, if introduced, should also have TTL where
appropriate.

## 47. Failure Behavior

Infrastructure failures must preserve the local-first guarantee.

Examples:

``` text
S3 upload fails
→ local original remains safe

App Runner/model fails
→ Story/Moment remains local

App Runner unavailable
→ capture still persists locally

rendering
→ remains on-device and independent of AWS once EditPlan is available
```

AWS availability must not determine whether the user's already-captured
media survives.

## 48. Disaster Recovery

MVP has little authoritative cloud user state.

Therefore disaster-recovery complexity is intentionally low.

Critical recoverable assets are:

-   infrastructure source/CDK
-   backend source
-   contracts
-   secrets/configuration
-   any future server-side persistent operational data

User Story/media authority remains on-device for MVP.

Revisit backup/restore architecture when cloud sync or accounts become
authoritative.

## 49. Infrastructure Testing

CDK tests should verify important properties, for example:

-   S3 Block Public Access enabled
-   lifecycle expiration configured
-   App Runner service receives only required environment variables/secrets
-   Lambda async worker (when enabled) receives only required environment variables
-   IAM grants are scoped
-   API routes exist on the App Runner service
-   production resources use expected retention/protection settings

Do not snapshot-test every generated CloudFormation line if targeted
assertions provide clearer value.

## 50. Security Review Checklist Before External Beta

Verify:

-   no public media bucket
-   no provider secrets in app/source
-   presigned URLs expire
-   upload size/type validation exists
-   S3 lifecycle is active
-   logs contain no raw media
-   AI provider data handling is documented
-   API throttling exists
-   IAM policies are reviewed
-   production/staging are isolated appropriately
-   dependency/security scanning is part of CI where practical

## 51. Infrastructure Non-Goals

MVP does not require:

-   EKS/Kubernetes
-   service mesh
-   multi-region active-active
-   permanent cloud media library
-   CloudFront media distribution
-   Cognito/account system
-   one Lambda per engine
-   Step Functions for simple synchronous flows
-   Kafka/Kinesis
-   ElastiCache
-   OpenSearch/vector database
-   GPU infrastructure
-   AWS Batch until workload requires it
-   custom KMS keys without a requirement
-   VPC/NAT by default

## 52. Evolution Path

The AWS architecture should evolve by workload, not speculation.

### Phase A — Walking skeleton

``` text
App Runner (Python FastAPI)
→ mock engines
CloudWatch
```

S3 can be added as soon as real proxy upload is required.

### Phase B — Real AI

``` text
App Runner
→ Model Gateway (concurrent Bedrock calls)
→ Bedrock / external models

S3 temporary media
Secrets Manager
ECR (container image)
```

For MVP, **Asset Understanding runs as an on-device persistent job queue** (see
`06-asset-understanding.md`, FROZEN): each job extracts 24 timestamped frames locally and posts a
small (~1–3 MB) request to the **existing** App Runner `/v1/asset-understanding` endpoint
opportunistically; the result caches locally. **No** SQS, **no** Lambda/Fargate AU worker, **no**
temporary video S3, **no** presigned AU upload, **no** server-side eager/fan-out AU. Each model
call is synchronous and completes within the 120-second App Runner budget; the product workflow is
asynchronous via the on-device queue. Create My Story consumes locally-cached MomentUnderstanding.
The general SQS/Lambda/Fargate guidance below remains valid for OTHER future heavy workloads
(generative media, rendering), not for AU.

### Phase C — Operational async work

When measured latency shows operations approaching 90 seconds:

``` text
App Runner API
→ DynamoDB Job record
→ SQS queue
→ Lambda worker (bounded jobs ≤ 15 min)
```

### Phase D — Heavy media/AI

When worker jobs exceed Lambda limits (long video analysis, generative
media, GPU processing):

``` text
App Runner API
→ Job record
→ SQS
→ ECS Fargate task (heavy/long jobs)
```

The Story/Director/Asset/Edit engine interfaces remain stable through
all phases. App Runner is never replaced; it continues to serve the
interactive request path while workers handle async jobs.

## 53. Architecture Decision Summary

  Concern                    MVP Decision
  -------------------------- --------------------------------------------------
  Cloud                      AWS
  IaC                        AWS CDK
  CDK language               TypeScript
  Consumer app               Native iOS / Swift
  Backend                    Python
  API framework              FastAPI
  API compute                AWS App Runner (always-on, SSE, 120s timeout)
  Async worker               Lambda (SQS consumer, added when needed)
  Heavy worker               ECS Fargate task (when Lambda limits reached)
  Temporary media            S3
  Permanent originals        On-device, not S3
  Server operational state   DynamoDB only when needed
  Async queue                SQS only when needed
  AWS AI                     Bedrock where appropriate
  External AI                Through Model Gateway
  Secrets                    Secrets Manager
  Logs/metrics               CloudWatch
  Permissions                IAM least privilege
  Accounts                   Not required
  Cognito                    Deferred
  VPC                        Not by default
  Regions                    Single region MVP
  Environments               development, staging, production
  Deployment unit            Modular Python backend, not engine microservices

## 54. Final Infrastructure Rule

``` text
Swift owns the consumer device experience.
Python owns Story's cloud intelligence.
TypeScript CDK owns AWS infrastructure.
OpenAPI/JSON Schema connects the boundaries.
```

AWS is the deployment platform, not the product architecture.

The infrastructure should make Story's system architecture easy to
operate without forcing AWS concepts into Story's domain model.
