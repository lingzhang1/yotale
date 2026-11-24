import * as cdk from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { StoryApiStack } from "../lib/story-api-stack";

// Step 8 of the production release plan: production gets the same least-privilege GitHub OIDC deploy role and scoped
// CloudFormation execution role as development and beta, trusting ONLY the `production` GitHub Environment.
const PROD_CTX = { imageDigest: "sha256:abc", cognitoUserPoolId: "us-east-1_prod", cognitoAppClientId: "client",
                   allowNoObservability: "true" };

function stack(environment: string, ctx: Record<string, unknown>): StoryApiStack {
  return new StoryApiStack(new cdk.App({ context: { environment, ...ctx } }), `story-${environment}-api`, {
    environment, env: { account: "123456789012", region: "us-east-1" },
  });
}

describe("production deploy role", () => {
  const prod = stack("production", PROD_CTX);
  const t = Template.fromStack(prod);
  const roles = t.findResources("AWS::IAM::Role");
  const byName = (n: string) => Object.values(roles).find((r: any) => r.Properties.RoleName === n) as any;
  const policies = JSON.stringify(t.findResources("AWS::IAM::Policy"));

  test("OIDC provider, deploy role and cfn-exec role exist", () => {
    t.resourceCountIs("Custom::AWSCDKOpenIdConnectProvider", 1);
    expect(byName("story-production-github-deploy")).toBeDefined();
    expect(byName("story-production-cfn-exec")).toBeDefined();
    t.hasOutput("GitHubDeployRoleArn", {});
    t.hasOutput("CfnExecRoleArn", {});
  });

  test("deploy role trusts only the production GitHub Environment of lingzhang1/yotale", () => {
    const trust = JSON.stringify(byName("story-production-github-deploy").Properties.AssumeRolePolicyDocument);
    expect(trust).toContain("repo:lingzhang1@*/yotale@*:environment:production");
    expect(trust).toContain("sts.amazonaws.com");
    for (const other of ["development", "beta", "gamma", "*"]) {
      expect(trust).not.toContain(`:environment:${other}"`);
    }
    expect(byName("story-production-github-deploy").Properties.MaxSessionDuration).toBe(3600);
  });

  test("deploy role can never delete the stack and passes only its own cfn-exec role", () => {
    expect(policies).not.toContain("cloudformation:DeleteStack");
    expect(policies).toContain("PassOnlyScopedCfnExec");
    // Every CloudFormation statement is scoped to the production api stack or CDKToolkit.
    expect(policies).toContain("stack/story-production-api/*");
    expect(policies).not.toContain("stack/story-beta-api");
    expect(policies).not.toContain("stack/story-development-api");
  });

  test("production stack has termination protection; other stages do not", () => {
    expect(prod.terminationProtection).toBe(true);
    expect(stack("beta", { ...PROD_CTX, cognitoUserPoolId: "us-east-1_beta" }).terminationProtection).toBe(false);
    expect(stack("development", {}).terminationProtection).toBe(false);
  });
});
