import * as cdk from "aws-cdk-lib";
import { Template, Match } from "aws-cdk-lib/assertions";
import { StoryApiStack } from "../lib/story-api-stack";

// Account deletion D2: synthesized-policy inspection (design 5.11 verification criterion).
function synth(environment: string, extra: Record<string, unknown> = {}): Template {
  const app = new cdk.App({ context: extra as Record<string, string> });
  const stack = new StoryApiStack(app, `story-${environment}-api`, {
    environment,
    env: { account: "123456789012", region: "us-east-1" },
    ...(extra.observability ? { enableObservability: true, alarmDestination: "alerts@example.com" } : {}),
  } as any);
  return Template.fromStack(stack);
}

function workerPolicy(t: Template): any[] {
  const roles = t.findResources("AWS::IAM::Role");
  const fn = Object.values(t.findResources("AWS::Lambda::Function"))
    .find((f: any) => f.Properties.FunctionName === "story-test-account-deletion") as any;
  const roleId = fn.Properties.Role["Fn::GetAtt"][0];
  expect(roles[roleId]).toBeDefined();
  const policies = Object.values(t.findResources("AWS::IAM::Policy"))
    .filter((p: any) => p.Properties.Roles.some((r: any) => r.Ref === roleId)) as any[];
  return policies.flatMap((p) => p.Properties.PolicyDocument.Statement);
}

describe("Account deletion (D2)", () => {
  const t = synth("test");

  test("request table: pk/sk, PITR, deletion protection, retained", () => {
    t.hasResource("AWS::DynamoDB::Table", {
      Properties: Match.objectLike({
        TableName: "story-test-account-deletions",
        KeySchema: [{ AttributeName: "pk", KeyType: "HASH" }, { AttributeName: "sk", KeyType: "RANGE" }],
        PointInTimeRecoverySpecification: { PointInTimeRecoveryEnabled: true },
        DeletionProtectionEnabled: true,
      }),
      DeletionPolicy: "Retain",
    });
  });

  test("worker: 300 s, handler, no reserved concurrency, no event source mapping", () => {
    t.hasResourceProperties("AWS::Lambda::Function", {
      FunctionName: "story-test-account-deletion", Handler: "account_deletion.worker.handler",
      Timeout: 300, Runtime: "python3.12",
      Environment: { Variables: Match.objectLike({ STORY_ENVIRONMENT: "test",
                                                   STORY_COGNITO_USER_POOL_ID: "us-east-1_AzfHOEdA5" }) },
    });
    const fn = Object.values(t.findResources("AWS::Lambda::Function"))
      .find((f: any) => f.Properties.FunctionName === "story-test-account-deletion") as any;
    expect(fn.Properties.ReservedConcurrentExecutions).toBeUndefined();
    const esms = Object.values(t.findResources("AWS::Lambda::EventSourceMapping")) as any[];
    expect(JSON.stringify(esms)).not.toContain("AccountDeletion");
  });

  test("schedule: every 5 minutes, retries 0, max event age 300 s", () => {
    t.hasResourceProperties("AWS::Events::Rule", {
      Name: "story-test-account-deletion", ScheduleExpression: "rate(5 minutes)",
      Targets: [Match.objectLike({ RetryPolicy: { MaximumRetryAttempts: 0, MaximumEventAgeInSeconds: 300 } })],
    });
  });

  test("worker policy matches the 5.11 matrix", () => {
    const st = workerPolicy(t);
    const actions = st.flatMap((s) => ([] as string[]).concat(s.Action));
    // no queue, no ledger PutObject, no delete on the request, users or claims tables
    expect(actions.some((a) => a.startsWith("sqs:"))).toBe(false);
    expect(actions).not.toContain("s3:PutObject");
    const bySid = Object.fromEntries(st.filter((s) => s.Sid).map((s) => [s.Sid, s]));
    expect([].concat(bySid.DeletionRequests.Action)).not.toContain("dynamodb:DeleteItem");
    expect(bySid.UsersTombstone.Action).toEqual(["dynamodb:GetItem", "dynamodb:UpdateItem"]);
    expect(JSON.stringify(st)).not.toContain("identity-claims");
    expect(bySid.MediaList.Condition).toEqual({ StringLike: { "s3:prefix": ["media/*", "evidence/*"] } });
    expect(bySid.StagingList.Condition).toEqual({ StringLike: { "s3:prefix": ["jobs/*"] } });
    const objRes = JSON.stringify(bySid.MediaDelete.Resource);
    expect(objRes).toContain("/media/*");
    expect(objRes).toContain("/evidence/*");
    expect(JSON.stringify(bySid.StagingDelete.Resource)).toContain("/jobs/*");
    expect(bySid.CognitoAccountDeletion.Resource)
      .toBe("arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_AzfHOEdA5");
    // no wildcard resource outside the Lambda basic-execution managed policy
    for (const s of st) expect(JSON.stringify(s.Resource)).not.toBe('"*"');
  });

  test("created for beta with the beta pool; not for production", () => {
    const beta = synth("beta", { imageDigest: "sha256:abc", cognitoUserPoolId: "us-east-1_beta",
                                 cognitoAppClientId: "client", allowNoObservability: "true" });
    beta.resourcePropertiesCountIs("AWS::DynamoDB::Table", { TableName: "story-beta-account-deletions" }, 1);
    beta.hasResourceProperties("AWS::Lambda::Function", {
      FunctionName: "story-beta-account-deletion",
      Environment: { Variables: Match.objectLike({ STORY_COGNITO_USER_POOL_ID: "us-east-1_beta" }) },
    });
    const prod = synth("production", { imageDigest: "sha256:abc", cognitoUserPoolId: "us-east-1_prod",
                                       cognitoAppClientId: "client", allowNoObservability: "true" });
    prod.resourcePropertiesCountIs("AWS::DynamoDB::Table", { TableName: "story-production-account-deletions" }, 0);
  });

  test("operator role: account principals only, 1 h, worker grants plus restored-table replay", () => {
    t.hasResourceProperties("AWS::IAM::Role", {
      RoleName: "story-test-account-deletion-operator", MaxSessionDuration: 3600,
      AssumeRolePolicyDocument: Match.objectLike({ Statement: [Match.objectLike({
        Principal: { AWS: { "Fn::Join": ["", ["arn:", { Ref: "AWS::Partition" }, ":iam::123456789012:root"]] } } })] }),
    });
    const policies = Object.values(t.findResources("AWS::IAM::Policy")) as any[];
    const op = policies.filter((p) => p.Properties.Roles.some((r: any) => JSON.stringify(r).includes("OperatorRole")))
      .flatMap((p) => p.Properties.PolicyDocument.Statement);
    const sids = op.map((s: any) => s.Sid);
    expect(sids).toEqual(expect.arrayContaining(["DeletionRequests", "UsersTombstone", "CognitoAccountDeletion",
                                                 "RestoreReplay"]));
    expect(op.find((s: any) => s.Sid === "RestoreReplay").Resource)
      .toBe("arn:aws:dynamodb:us-east-1:123456789012:table/story-test-*-restored*");
    expect(JSON.stringify(op)).not.toContain("sqs:");
  });

  test("alarms exist with observability", () => {
    const o = synth("test", { observability: true });
    for (const n of ["stalled", "overdue", "late-found", "heartbeat-missing", "errors"]) {
      o.hasResourceProperties("AWS::CloudWatch::Alarm", { AlarmName: `story-test-account-deletion-${n}` });
    }
    o.hasResourceProperties("AWS::CloudWatch::Alarm", {
      AlarmName: "story-test-account-deletion-heartbeat-missing", TreatMissingData: "breaching",
      EvaluationPeriods: 6, ComparisonOperator: "LessThanThreshold",
    });
  });
});

describe("Account deletion (D3) API wiring", () => {
  const envVars = (t: Template) => {
    const svc = Object.values(t.findResources("AWS::AppRunner::Service"))[0] as any;
    return (svc.Properties.SourceConfiguration.ImageRepository.ImageConfiguration.RuntimeEnvironmentVariables as
      Array<{ Name: string; Value: unknown }>);
  };

  test("App Runner gets the request table where it exists, and not elsewhere", () => {
    const dev = envVars(synth("test")).find((e) => e.Name === "STORY_ACCOUNT_DELETIONS_TABLE");
    expect(dev?.Value).toBe("story-test-account-deletions");
    const beta = synth("beta", { imageDigest: "sha256:abc", cognitoUserPoolId: "us-east-1_beta",
                                 cognitoAppClientId: "client", allowNoObservability: "true" });
    expect(envVars(beta).find((e) => e.Name === "STORY_ACCOUNT_DELETIONS_TABLE")?.Value).toBe("story-beta-account-deletions");
  });

  test("the API may only accept and read requests (no UpdateItem or DeleteItem on the table)", () => {
    const st = (Object.values(synth("test").findResources("AWS::IAM::Policy")) as any[])
      .flatMap((p) => p.Properties.PolicyDocument.Statement)
      .find((s: any) => s.Sid === "AccountDeletionAccept");
    expect(st.Action).toEqual(["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:ConditionCheckItem"]);
  });
});

describe("deploy role (release gate)", () => {
  test("may list the pool's identity providers, read-only, on the configured pool only", () => {
    const t = synth("test");
    const policies = Object.values(t.findResources("AWS::IAM::Policy")) as any[];
    const st = policies.flatMap((p) => p.Properties.PolicyDocument.Statement)
      .find((s: any) => s.Sid === "ReleaseGateIdentityProviders");
    expect(st.Action).toBe("cognito-idp:ListIdentityProviders");
    expect(st.Resource).toBe("arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_AzfHOEdA5");
  });
});

describe("Sign in with Apple notifications (D7)", () => {
  const envVars = (t: Template) => {
    const svc = Object.values(t.findResources("AWS::AppRunner::Service"))[0] as any;
    return (svc.Properties.SourceConfiguration.ImageRepository.ImageConfiguration.RuntimeEnvironmentVariables as
      Array<{ Name: string; Value: unknown }>);
  };
  const betaCtx = { imageDigest: "sha256:abc", cognitoUserPoolId: "us-east-1_beta", cognitoAppClientId: "client",
                    allowNoObservability: "true" };

  test("beta gets its Services ID as the audience and a sign-out-only grant on its pool", () => {
    const beta = synth("beta", betaCtx);
    expect(envVars(beta).find((e) => e.Name === "STORY_APPLE_SIGNIN_AUDIENCE")?.Value)
      .toBe("com.lingzhang.story.signin.beta");
    const st = (Object.values(beta.findResources("AWS::IAM::Policy")) as any[])
      .flatMap((p) => p.Properties.PolicyDocument.Statement).find((s: any) => s.Sid === "AppleSignInRevocation");
    expect(st.Action).toBe("cognito-idp:AdminUserGlobalSignOut");
    expect(st.Resource).toBe("arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_beta");
  });

  test("an environment without a Services ID gets neither", () => {
    const t = synth("test");
    expect(envVars(t).some((e) => e.Name === "STORY_APPLE_SIGNIN_AUDIENCE")).toBe(false);
  });
});
