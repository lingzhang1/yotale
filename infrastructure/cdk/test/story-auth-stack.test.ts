import * as cdk from "aws-cdk-lib";
import { Template, Match } from "aws-cdk-lib/assertions";
import { StoryAuthStack } from "../lib/story-auth-stack";

function synth(context: Record<string, unknown> = {}): Template {
  const app = new cdk.App({ context });
  const stack = new StoryAuthStack(app, "story-test-auth", {
    environment: "test",
    env: { account: "123456789012", region: "us-east-1" },
  });
  return Template.fromStack(stack);
}

describe("StoryAuthStack (P0 Beta Auth, Increment 1)", () => {
  const template = synth();
  // A second synth WITH Apple creds present (simulates post-Apple-portal provisioning).
  const withApple = synth({ appleSecretName: "YoTale-Apple-SignIn-Test" });

  test("provisions exactly one Cognito user pool", () => {
    template.resourceCountIs("AWS::Cognito::UserPool", 1);
  });

  test("user pool is on the Essentials feature plan (required for native EMAIL_OTP)", () => {
    template.hasResourceProperties("AWS::Cognito::UserPool", {
      UserPoolTier: "ESSENTIALS",
    });
  });

  test("EMAIL_OTP is an allowed first-auth factor; PASSWORD is pool-level only (Cognito requires it)", () => {
    // Cognito rejects an EMAIL_OTP-only factor list, so PASSWORD must appear at the pool level. The real
    // no-password guarantee is enforced on the CLIENT (no SRP/password flow — asserted in the next test).
    template.hasResourceProperties("AWS::Cognito::UserPool", {
      Policies: Match.objectLike({
        SignInPolicy: { AllowedFirstAuthFactors: Match.arrayWith(["EMAIL_OTP"]) },
      }),
    });
  });

  test("app client has NO SRP/password flow; only USER_AUTH + REFRESH (correction 3)", () => {
    const clients = template.findResources("AWS::Cognito::UserPoolClient");
    const client = Object.values(clients)[0] as any;
    const flows: string[] = client.Properties.ExplicitAuthFlows;
    expect(flows).toEqual(expect.arrayContaining(["ALLOW_USER_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]));
    expect(flows).not.toContain("ALLOW_USER_SRP_AUTH");
    expect(flows).not.toContain("ALLOW_USER_PASSWORD_AUTH");
    expect(flows).not.toContain("ALLOW_ADMIN_USER_PASSWORD_AUTH");
  });

  test("Apple OAuth code-grant flow + callback configured, and a Cognito domain exists (correction 2)", () => {
    template.hasResourceProperties("AWS::Cognito::UserPoolClient", {
      AllowedOAuthFlows: Match.arrayWith(["code"]),
      CallbackURLs: Match.arrayWith(["story://auth"]),
    });
    template.resourceCountIs("AWS::Cognito::UserPoolDomain", 1);
    withApple.hasResourceProperties("AWS::Cognito::UserPoolClient", {
      SupportedIdentityProviders: Match.arrayWith(["SignInWithApple", "COGNITO"]),
    });
  });

  test("atomic identity-claim table exists for uniqueness (correction 1 — not GSI-only)", () => {
    template.hasResourceProperties("AWS::DynamoDB::Table", {
      TableName: Match.stringLikeRegexp("identity-claims"),
      KeySchema: Match.arrayWith([{ AttributeName: "claim_key", KeyType: "HASH" }]),
    });
  });

  test("NO custom-auth Lambda triggers are wired (native EMAIL_OTP preferred over custom)", () => {
    // Increment 1 uses native EMAIL_OTP; there must be no DefineAuthChallenge/CreateAuthChallenge/VerifyAuth
    // Lambda config on the pool.
    const pools = template.findResources("AWS::Cognito::UserPool");
    const pool = Object.values(pools)[0] as any;
    const triggers = pool.Properties.LambdaConfig ?? {};
    expect(triggers.DefineAuthChallenge).toBeUndefined();
    expect(triggers.CreateAuthChallenge).toBeUndefined();
    expect(triggers.VerifyAuthChallengeResponse).toBeUndefined();
  });

  test("Sign in with Apple IdP is configured WHEN an Apple secret name is supplied", () => {
    withApple.hasResourceProperties("AWS::Cognito::UserPoolIdentityProvider", {
      ProviderType: "SignInWithApple",
      ProviderName: "SignInWithApple",
      ProviderDetails: Match.objectLike({ authorize_scopes: "email name" }),
    });
  });

  test("Apple credentials are Secrets Manager dynamic references, never literal key material", () => {
    const idps = withApple.findResources("AWS::Cognito::UserPoolIdentityProvider");
    const [logicalId] = Object.keys(idps);
    expect(logicalId).toMatch(/^AppleIdp/); // stable logical id (no replacement on upgrade)
    const details = idps[logicalId].Properties.ProviderDetails;
    for (const [prop, field] of [
      ["client_id", "services_id"], ["team_id", "team_id"], ["key_id", "key_id"], ["private_key", "private_key"],
    ]) {
      expect(details[prop]).toBe(`{{resolve:secretsmanager:YoTale-Apple-SignIn-Test:SecretString:${field}::}}`);
    }
    const whole = JSON.stringify(withApple.toJSON());
    expect(whole).not.toContain("BEGIN PRIVATE KEY");
  });

  test("Apple-only client keeps its provider order (no client update when Google is absent)", () => {
    withApple.hasResourceProperties("AWS::Cognito::UserPoolClient", {
      SupportedIdentityProviders: ["SignInWithApple", "COGNITO"],
    });
    withApple.resourceCountIs("AWS::Cognito::UserPoolIdentityProvider", 1);
  });

  test("Google IdP: dynamic-reference credentials, email mapping, and listed on the client", () => {
    const withGoogle = synth({ appleSecretName: "YoTale-Apple-SignIn-Test", googleSecretName: "YoTale-Google-SignIn-Test" });
    withGoogle.hasResourceProperties("AWS::Cognito::UserPoolIdentityProvider", {
      ProviderName: "Google",
      ProviderType: "Google",
      ProviderDetails: {
        client_id: "{{resolve:secretsmanager:YoTale-Google-SignIn-Test:SecretString:client_id::}}",
        client_secret: "{{resolve:secretsmanager:YoTale-Google-SignIn-Test:SecretString:client_secret::}}",
        authorize_scopes: "openid email profile",
      },
      AttributeMapping: { email: "email", email_verified: "email_verified" },
    });
    withGoogle.hasResourceProperties("AWS::Cognito::UserPoolClient", {
      SupportedIdentityProviders: ["SignInWithApple", "Google", "COGNITO"],
    });
  });

  test("Google without Apple fails synth (App Store Guideline 4.8)", () => {
    expect(() => synth({ googleSecretName: "YoTale-Google-SignIn-Test" })).toThrow(/Guideline 4.8/);
  });

  test("dev-provision reality: NO Apple IdP without creds; EMAIL_OTP still works (correction 9)", () => {
    // Apple creds are not yet available — the dev stack provisions without the Apple IdP.
    template.resourceCountIs("AWS::Cognito::UserPoolIdentityProvider", 0);
    template.hasResourceProperties("AWS::Cognito::UserPoolClient", {
      SupportedIdentityProviders: ["COGNITO"],
    });
  });

  test("app client is public (no secret) for native iOS", () => {
    template.hasResourceProperties("AWS::Cognito::UserPoolClient", {
      GenerateSecret: false,
    });
  });

  test("StoryUser table separates immutable story_user_id from cognito_sub (reverse-lookup GSI)", () => {
    template.hasResourceProperties("AWS::DynamoDB::Table", {
      KeySchema: Match.arrayWith([{ AttributeName: "story_user_id", KeyType: "HASH" }]),
      GlobalSecondaryIndexes: Match.arrayWith([
        Match.objectLike({ IndexName: "by_cognito_sub" }),
        Match.objectLike({ IndexName: "by_provider_identity" }),
      ]),
    });
  });

  test("UserUsage table keyed (story_user_id, quota_period) for atomic quota reservation", () => {
    template.hasResourceProperties("AWS::DynamoDB::Table", {
      KeySchema: Match.arrayWith([
        { AttributeName: "story_user_id", KeyType: "HASH" },
        { AttributeName: "quota_period", KeyType: "RANGE" },
      ]),
    });
  });

  test("identity + usage data is RETAINed (never auto-deleted)", () => {
    template.allResourcesProperties("AWS::DynamoDB::Table", {
      PointInTimeRecoverySpecification: { PointInTimeRecoveryEnabled: true },
    });
    const pool = Object.values(template.findResources("AWS::Cognito::UserPool"))[0] as any;
    expect(pool.DeletionPolicy).toBe("Retain");
  });

  test("DEFAULT (dev/test): Cognito uses its default email sender — NO DEVELOPER SES EmailConfiguration", () => {
    const pool = Object.values(template.findResources("AWS::Cognito::UserPool"))[0] as any;
    const emailCfg = pool.Properties.EmailConfiguration;
    // Either absent entirely, or present without DEVELOPER sending account.
    if (emailCfg) {
      expect(emailCfg.EmailSendingAccount).not.toBe("DEVELOPER");
    } else {
      expect(emailCfg).toBeUndefined();
    }
  });

  test("beta: same-account SES wired in DEVELOPER mode with correct From + deploy-account SourceArn (point 7)", () => {
    const betaSes = synth({ sesFromEmail: "no-reply@beta.yotale.ai" });
    betaSes.hasResourceProperties("AWS::Cognito::UserPool", {
      EmailConfiguration: Match.objectLike({
        EmailSendingAccount: "DEVELOPER",
        From: "no-reply@beta.yotale.ai",
        // SourceArn is built from the DEPLOY-time account ref (Fn::Sub ${AWS::AccountId}), never a
        // synth-time literal — so it cannot be frozen to the wrong account by ambient credentials.
        SourceArn: {
          "Fn::Sub": "arn:aws:ses:us-east-1:${AWS::AccountId}:identity/beta.yotale.ai",
        },
      }),
    });
  });

  test("beta SES same-account guard THROWS when the synth account != sesAccountId", () => {
    // synth() builds the stack with account 123456789012; a mismatching sesAccountId must fail fast.
    expect(() =>
      synth({ sesFromEmail: "no-reply@beta.yotale.ai", sesAccountId: "224033508028" })
    ).toThrow(/SES same-account guard/);
  });
});
