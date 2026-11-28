import * as cdk from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { StoryApiStack } from "../lib/story-api-stack";
import { apiEnvMap } from "./api-env";

// Owner 2026-11-28: production's shared AI spend breaker is $500/month; other stages keep $60.
const ctx = (pool: string) => ({ imageDigest: "sha256:abc", cognitoUserPoolId: pool, cognitoAppClientId: "client",
                                 allowNoObservability: "true" });
const env = (environment: string, c: Record<string, unknown>) => apiEnvMap(Template.fromStack(new StoryApiStack(
  new cdk.App({ context: c }), `story-${environment}-api`, { environment, env: { account: "123456789012", region: "us-east-1" } })));

test("production global breaker is $500; beta and development stay $60", () => {
  delete process.env.STORY_QUOTA_GLOBAL_MONTHLY_USD;
  expect(env("production", ctx("us-east-1_prod")).STORY_QUOTA_GLOBAL_MONTHLY_USD).toBe("500");
  expect(env("beta", ctx("us-east-1_beta")).STORY_QUOTA_GLOBAL_MONTHLY_USD).toBe("60");
  expect(env("development", {}).STORY_QUOTA_GLOBAL_MONTHLY_USD).toBe("60");
});
