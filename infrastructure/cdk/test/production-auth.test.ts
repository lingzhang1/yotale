import * as cdk from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { StoryAuthStack } from "../lib/story-auth-stack";
import { StoryApiStack } from "../lib/story-api-stack";
import { apiEnvVars, apiEnvMap } from "./api-env";

// Production release plan step 11: the production auth stack and the production Apple Services ID.
function auth(environment: string, context: Record<string, unknown> = {}): StoryAuthStack {
  return new StoryAuthStack(new cdk.App({ context }), `story-${environment}-auth`, {
    environment, env: { account: "123456789012", region: "us-east-1" },
  });
}

describe("production auth stack", () => {
  const ctx = { appleSecretName: "YoTale-Apple-SignIn-Prod", googleSecretName: "YoTale-Google-SignIn-Prod",
                sesFromEmail: "no-reply@yotale.ai" };
  const prod = auth("production", ctx);
  const t = Template.fromStack(prod);

  test("pool, domain and client are named for production", () => {
    t.hasResourceProperties("AWS::Cognito::UserPool", { UserPoolName: "story-production-users" });
    t.hasResourceProperties("AWS::Cognito::UserPoolDomain", { Domain: "story-production-auth" });
    t.hasResourceProperties("AWS::Cognito::UserPoolClient", { ClientName: "story-production-ios" });
  });

  test("pool has deletion protection and the stack has termination protection", () => {
    t.hasResourceProperties("AWS::Cognito::UserPool", { DeletionProtection: "ACTIVE" });
    expect(prod.terminationProtection).toBe(true);
  });

  test("other stages keep their current settings", () => {
    const beta = auth("beta", ctx);
    expect(beta.terminationProtection).toBe(false);
    const pools = Template.fromStack(beta).findResources("AWS::Cognito::UserPool");
    for (const p of Object.values(pools) as any[]) expect(p.Properties.DeletionProtection).toBeUndefined();
  });

  test("Apple and Google sign-in use the production secrets and SES uses yotale.ai", () => {
    const json = JSON.stringify(t.toJSON());
    expect(json).toContain("YoTale-Apple-SignIn-Prod");
    expect(json).toContain("YoTale-Google-SignIn-Prod");
    expect(json).toContain("identity/yotale.ai");
    expect(json).not.toContain("beta.yotale.ai");
  });
});

describe("production Apple Services ID", () => {
  test("the production API trusts com.lingzhang.story.signin.prod as the Apple notification audience", () => {
    const api = new StoryApiStack(new cdk.App({ context: { imageDigest: "sha256:abc", cognitoUserPoolId: "us-east-1_prod",
                                                             cognitoAppClientId: "client", allowNoObservability: "true" } }),
      "story-production-api", { environment: "production", env: { account: "123456789012", region: "us-east-1" } });
    const vars = apiEnvVars(Template.fromStack(api));
    expect(vars.find((e: any) => e.Name === "STORY_APPLE_SIGNIN_AUDIENCE")?.Value).toBe("com.lingzhang.story.signin.prod");
  });
});
