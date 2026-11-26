import * as cdk from "aws-cdk-lib";
import { Template, Match } from "aws-cdk-lib/assertions";
import { StoryApiStack } from "../lib/story-api-stack";
import { apiWafRules } from "../lib/story-beta-waf-stack";
import { apiEnvVars } from "./api-env";

// ecs-fargate-migration-plan.md: every stage on ECS Fargate behind a CDK-owned ALB; beta keeps App Runner during the
// overlap; production runs two tasks.
const DIGEST = "sha256:" + "a".repeat(64);
const RELEASE = (pool: string) => ({ imageDigest: DIGEST, cognitoUserPoolId: pool, cognitoAppClientId: "client",
                                     observability: "true", alarmDestination: "alerts@yotale.ai" });
const synth = (environment: string, ctx: Record<string, unknown> = {}) => {
  const app = new cdk.App({ context: ctx });
  return Template.fromStack(new StoryApiStack(app, `story-${environment}-api`, {
    environment, enableObservability: ctx.observability === "true", alarmDestination: "alerts@yotale.ai",
    env: { account: "123456789012", region: "us-east-1" } }));
};
const dev = synth("development", { imageDigest: DIGEST });
const beta = synth("beta", RELEASE("us-east-1_beta"));
const prod = synth("production", RELEASE("us-east-1_prod"));
const apiImage = (t: Template) => {
  const tds = Object.values(t.findResources("AWS::ECS::TaskDefinition")) as any[];
  return tds.flatMap((td) => td.Properties.ContainerDefinitions).find((c: any) => c.Name === "api");
};

describe("ECS Fargate API", () => {
  test("every stage has exactly one ECS API service; only beta keeps App Runner (overlap)", () => {
    for (const t of [dev, beta, prod]) t.resourceCountIs("AWS::ECS::Service", 1);
    dev.resourceCountIs("AWS::AppRunner::Service", 0);
    prod.resourceCountIs("AWS::AppRunner::Service", 0);
    beta.resourceCountIs("AWS::AppRunner::Service", 1);
  });

  test("beta overlap: App Runner and ECS run the same digest and the same env list", () => {
    const ar = Object.values(beta.findResources("AWS::AppRunner::Service"))[0] as any;
    expect(JSON.stringify(ar.Properties.SourceConfiguration.ImageRepository.ImageIdentifier)).toContain(`@${DIGEST}`);
    expect(JSON.stringify(apiImage(beta).Image)).toContain(`@${DIGEST}`);
    expect(() => apiEnvVars(beta)).not.toThrow();   // throws if the two env lists differ
  });

  test("image pinned by digest; 1 vCPU / 2 GB; port 8080", () => {
    for (const t of [dev, beta, prod]) {
      expect(JSON.stringify(apiImage(t).Image)).toContain(`@${DIGEST}`);
      t.hasResourceProperties("AWS::ECS::TaskDefinition", { Cpu: "1024", Memory: "2048",
        RequiresCompatibilities: ["FARGATE"] });
    }
  });

  test("production runs two tasks; dev and beta one; circuit breaker with rollback", () => {
    const desired = (t: Template) => (Object.values(t.findResources("AWS::ECS::Service"))[0] as any).Properties.DesiredCount;
    expect(desired(prod)).toBe(2);
    expect(desired(dev)).toBe(1);
    expect(desired(beta)).toBe(1);
    prod.hasResourceProperties("AWS::ECS::Service", { DeploymentConfiguration: Match.objectLike({
      DeploymentCircuitBreaker: { Enable: true, Rollback: true }, MinimumHealthyPercent: 100 }) });
    prod.hasResourceProperties("AWS::ApplicationAutoScaling::ScalableTarget", { MinCapacity: 2 });
  });

  test("ALB idle timeout is 180 s (no request App Runner served fails at the ALB)", () => {
    for (const t of [dev, beta, prod]) {
      t.hasResourceProperties("AWS::ElasticLoadBalancingV2::LoadBalancer", {
        LoadBalancerAttributes: Match.arrayWith([{ Key: "idle_timeout.timeout_seconds", Value: "180" }]),
      });
    }
  });

  test("HTTPS with the stage certificate; HTTP redirects to HTTPS", () => {
    prod.hasResourceProperties("AWS::ElasticLoadBalancingV2::Listener", {
      Port: 443, Protocol: "HTTPS",
      Certificates: [{ CertificateArn: Match.stringLikeRegexp("arn:aws:acm:us-east-1:854689494157:certificate/") }],
    });
    prod.hasResourceProperties("AWS::ElasticLoadBalancingV2::Listener", {
      Port: 80, DefaultActions: [Match.objectLike({ Type: "redirect",
        RedirectConfig: Match.objectLike({ Protocol: "HTTPS", Port: "443", StatusCode: "HTTP_301" }) })],
    });
    dev.hasResourceProperties("AWS::ElasticLoadBalancingV2::Listener", {
      Port: 443, Certificates: [{ CertificateArn: Match.stringLikeRegexp(":989088054552:certificate/") }] });
    beta.hasResourceProperties("AWS::ElasticLoadBalancingV2::Listener", {
      Port: 443, Certificates: [{ CertificateArn: Match.stringLikeRegexp(":224033508028:certificate/") }] });
  });

  test("tasks accept traffic only from the load balancer; no NAT gateway", () => {
    for (const t of [dev, beta, prod]) {
      t.resourceCountIs("AWS::EC2::NatGateway", 0);
      const ingress = Object.values(t.findResources("AWS::EC2::SecurityGroupIngress")) as any[];
      const toTasks = ingress.filter((i) => i.Properties.FromPort === 8080);
      expect(toTasks.length).toBe(1);
      expect(toTasks[0].Properties.SourceSecurityGroupId).toBeDefined();
      expect(toTasks[0].Properties.CidrIp).toBeUndefined();
    }
  });

  test("WAF on the ALB in beta and production with the same rules as the beta App Runner web ACL; none in dev", () => {
    dev.resourceCountIs("AWS::WAFv2::WebACL", 0);
    for (const [t, env] of [[beta, "beta"], [prod, "production"]] as const) {
      t.resourceCountIs("AWS::WAFv2::WebACL", 1);
      t.resourceCountIs("AWS::WAFv2::WebACLAssociation", 1);
      const acl = Object.values(t.findResources("AWS::WAFv2::WebACL"))[0] as any;
      expect(acl.Properties.Name).toBe(`story-${env}-alb-waf`);
      const want = JSON.parse(JSON.stringify(apiWafRules({ rateBlock: true })));
      expect(acl.Properties.Rules.map((r: any) => r.Name)).toEqual(want.map((r: any) => r.name));
      const rate = acl.Properties.Rules.find((r: any) => r.Name === "RateLimitPerIp");
      expect(rate.Action).toEqual({ Block: {} });
      const crs = acl.Properties.Rules.find((r: any) => r.Name === "CommonRuleSet");
      expect(crs.OverrideAction).toEqual({ Count: {} });
    }
  });

  test("API alarms: ALB target 5xx, ALB 5xx, unhealthy targets; App Runner 5xx only in beta", () => {
    for (const [t, env] of [[beta, "beta"], [prod, "production"]] as const) {
      for (const n of ["api-target-5xx", "api-elb-5xx", "api-unhealthy-targets"])
        t.hasResourceProperties("AWS::CloudWatch::Alarm", { AlarmName: `story-${env}-${n}` });
    }
    beta.hasResourceProperties("AWS::CloudWatch::Alarm", { AlarmName: "story-beta-apprunner-5xx" });
    const prodAlarms = JSON.stringify(prod.findResources("AWS::CloudWatch::Alarm"));
    expect(prodAlarms).not.toContain("apprunner");
  });

  test("runtime role is trusted by ECS tasks; App Runner trust only in beta", () => {
    const trust = (t: Template) => JSON.stringify(Object.values(t.findResources("AWS::IAM::Role"))
      .filter((r: any) => JSON.stringify(r.Properties.Description ?? "").includes("Runtime role for the Story API"))
      .map((r: any) => r.Properties.AssumeRolePolicyDocument));
    expect(trust(prod)).toContain("ecs-tasks.amazonaws.com");
    expect(trust(prod)).not.toContain("apprunner");
    expect(trust(beta)).toContain("tasks.apprunner.amazonaws.com");
  });

  test("deploy role can read ECS, target health and the ALB web ACL for the post-deploy gate", () => {
    const pol = JSON.stringify(prod.findResources("AWS::IAM::Policy"));
    for (const a of ["ecs:DescribeServices", "ecs:DescribeTaskDefinition", "elasticloadbalancing:DescribeTargetHealth",
                     "wafv2:GetWebACLForResource", "wafv2:GetWebACL"]) expect(pol).toContain(a);
    expect(pol).not.toContain("cloudformation:DeleteStack");
  });

  test("outputs: CNAME target and the stage base URL", () => {
    prod.hasOutput("ApiLoadBalancerDns", {});
    prod.hasOutput("ApiBaseUrl", { Value: "https://api.yotale.ai" });
    beta.hasOutput("ApiBaseUrl", { Value: "https://api-beta.yotale.ai" });
    dev.hasOutput("ApiBaseUrl", { Value: "https://api-dev.yotale.ai" });
  });
});
