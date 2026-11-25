/**
 * EcsApiService — the Story API on standard ECS Fargate behind a CDK-owned Application Load Balancer.
 *
 * Replaces App Runner, which is closed to new AWS accounts (ecs-fargate-migration-plan.md). One construct for every
 * stage; the stage only changes the task count, the hostname and its certificate, and whether WAF is attached.
 *
 *  - Own VPC per stage: two public subnets in two AZs, no NAT gateway (tasks get public IPs for outbound calls to
 *    OpenAI, Gemini, Unsplash and Epidemic). Deterministic, no default-VPC lookup.
 *  - Task: 1 vCPU / 2 GB, the image pinned by digest, the SAME env list App Runner gets (passed in by the stack).
 *  - ALB: HTTPS 443 with the stage certificate, HTTP 80 redirects to HTTPS, idle timeout 180 s so no request App
 *    Runner served (120 s cap) fails here; the iOS client's 180 s request timeout stays the outer limit.
 *  - Rolling deployment with the ECS circuit breaker and automatic rollback.
 *  - WAF (beta, production): the same rule set as the beta App Runner web ACL, associated with the ALB.
 */
import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as acm from "aws-cdk-lib/aws-certificatemanager";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as wafv2 from "aws-cdk-lib/aws-wafv2";
import { apiWafRules } from "./story-beta-waf-stack";

export const API_CONTAINER_NAME = "api";
export const API_CONTAINER_PORT = 8080;
export const ALB_IDLE_TIMEOUT_SECONDS = 180;

export interface EcsApiServiceProps {
  readonly environment: string;
  readonly repository: ecr.IRepository;
  /** sha256:... digest; absent only for local development/test synth (falls back to :latest). */
  readonly imageDigest?: string;
  /** Runtime role (today's App Runner instance role, also trusted by ECS tasks). */
  readonly taskRole: iam.IRole;
  /** The exact env list the API needs (shared with App Runner during the beta overlap). */
  readonly environmentVariables: Record<string, string>;
  readonly desiredCount: number;
  /** ACM certificate for the stage hostname; absent -> HTTP listener only (unit-test synth). */
  readonly certificateArn?: string;
  readonly hostname?: string;
  readonly enableWaf: boolean;
  readonly logRetention: logs.RetentionDays;
}

export class EcsApiService extends Construct {
  public readonly vpc: ec2.Vpc;
  public readonly cluster: ecs.Cluster;
  public readonly service: ecs.FargateService;
  public readonly loadBalancer: elbv2.ApplicationLoadBalancer;
  public readonly targetGroup: elbv2.ApplicationTargetGroup;
  public readonly webAcl?: wafv2.CfnWebACL;

  constructor(scope: Construct, id: string, props: EcsApiServiceProps) {
    super(scope, id);
    const env = props.environment;
    const name = `story-${env}-api`;

    this.vpc = new ec2.Vpc(this, "Vpc", {
      vpcName: name,
      // Named AZs (not maxAzs): no synth-time AZ lookup, so offline CI synth and every account produce the same VPC.
      availabilityZones: [`${cdk.Stack.of(this).region}a`, `${cdk.Stack.of(this).region}b`],
      natGateways: 0,
      subnetConfiguration: [{ name: "public", subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 }],
    });

    this.cluster = new ecs.Cluster(this, "Cluster", { clusterName: name, vpc: this.vpc });

    const executionRole = new iam.Role(this, "ExecutionRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      description: `Pulls the Story API image and writes its logs (${env})`,
    });
    props.repository.grantPull(executionRole);

    const taskDef = new ecs.FargateTaskDefinition(this, "TaskDef", {
      family: name, cpu: 1024, memoryLimitMiB: 2048,
      runtimePlatform: { cpuArchitecture: ecs.CpuArchitecture.X86_64, operatingSystemFamily: ecs.OperatingSystemFamily.LINUX },
      taskRole: props.taskRole, executionRole,
    });
    const logGroup = new logs.LogGroup(this, "Logs", {
      logGroupName: `/ecs/${name}`, retention: props.logRetention, removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const image = props.imageDigest
      ? `${props.repository.repositoryUri}@${props.imageDigest}`
      : `${props.repository.repositoryUri}:latest`;
    taskDef.addContainer("Api", {
      containerName: API_CONTAINER_NAME,
      image: ecs.ContainerImage.fromRegistry(image),
      environment: props.environmentVariables,
      portMappings: [{ containerPort: API_CONTAINER_PORT }],
      logging: ecs.LogDrivers.awsLogs({ logGroup, streamPrefix: "api" }),
      // uvicorn keep-alive must outlive the ALB idle timeout, or the ALB reuses a connection uvicorn already closed
      // (intermittent 502). The image CMD sets --timeout-keep-alive above ALB_IDLE_TIMEOUT_SECONDS.
      stopTimeout: cdk.Duration.seconds(30),
    });

    const albSg = new ec2.SecurityGroup(this, "AlbSg", {
      vpc: this.vpc, description: `${name} load balancer`, allowAllOutbound: false,
    });
    albSg.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443), "HTTPS");
    albSg.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(80), "HTTP redirect to HTTPS");
    const taskSg = new ec2.SecurityGroup(this, "TaskSg", {
      vpc: this.vpc, description: `${name} tasks (ingress only from the load balancer)`, allowAllOutbound: true,
    });
    taskSg.addIngressRule(albSg, ec2.Port.tcp(API_CONTAINER_PORT), "from the load balancer");
    albSg.addEgressRule(taskSg, ec2.Port.tcp(API_CONTAINER_PORT), "to the tasks");

    this.loadBalancer = new elbv2.ApplicationLoadBalancer(this, "Alb", {
      loadBalancerName: name, vpc: this.vpc, internetFacing: true, securityGroup: albSg,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      idleTimeout: cdk.Duration.seconds(ALB_IDLE_TIMEOUT_SECONDS),
      dropInvalidHeaderFields: true,
    });

    this.service = new ecs.FargateService(this, "Service", {
      serviceName: name, cluster: this.cluster, taskDefinition: taskDef,
      desiredCount: props.desiredCount,
      minHealthyPercent: 100, maxHealthyPercent: 200,
      circuitBreaker: { enable: true, rollback: true },
      assignPublicIp: true, vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC }, securityGroups: [taskSg],
      healthCheckGracePeriod: cdk.Duration.seconds(60),
      platformVersion: ecs.FargatePlatformVersion.LATEST,
      enableExecuteCommand: false,
    });

    this.targetGroup = new elbv2.ApplicationTargetGroup(this, "Targets", {
      targetGroupName: name, vpc: this.vpc, port: API_CONTAINER_PORT, protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      healthCheck: {
        path: "/health", interval: cdk.Duration.seconds(10), timeout: cdk.Duration.seconds(5),
        healthyThresholdCount: 2, unhealthyThresholdCount: 5, healthyHttpCodes: "200",
      },
      deregistrationDelay: cdk.Duration.seconds(30),
    });
    this.service.attachToApplicationTargetGroup(this.targetGroup);

    const scaling = this.service.autoScaleTaskCount({
      minCapacity: props.desiredCount, maxCapacity: Math.max(props.desiredCount * 4, 4),
    });
    scaling.scaleOnCpuUtilization("Cpu", { targetUtilizationPercent: 60 });

    if (props.certificateArn) {
      const cert = acm.Certificate.fromCertificateArn(this, "Cert", props.certificateArn);
      this.loadBalancer.addListener("Https", {
        port: 443, protocol: elbv2.ApplicationProtocol.HTTPS, certificates: [cert],
        sslPolicy: elbv2.SslPolicy.RECOMMENDED_TLS, open: false,
        defaultTargetGroups: [this.targetGroup],
      });
      this.loadBalancer.addListener("Http", {
        port: 80, open: false,
        defaultAction: elbv2.ListenerAction.redirect({ protocol: "HTTPS", port: "443", permanent: true }),
      });
    } else {
      this.loadBalancer.addListener("Http", { port: 80, open: false, defaultTargetGroups: [this.targetGroup] });
    }

    if (props.enableWaf) {
      const metric = (n: string) => ({ cloudWatchMetricsEnabled: true, metricName: n, sampledRequestsEnabled: true });
      this.webAcl = new wafv2.CfnWebACL(this, "WebAcl", {
        name: `story-${env}-alb-waf`, scope: "REGIONAL", defaultAction: { allow: {} },
        rules: apiWafRules({ rateBlock: true }),
        visibilityConfig: metric(`story-${env}-alb-waf`),
      });
      new wafv2.CfnWebACLAssociation(this, "WebAclAssociation", {
        resourceArn: this.loadBalancer.loadBalancerArn, webAclArn: this.webAcl.attrArn,
      });
      const wafLogs = new logs.LogGroup(this, "WafLogs", {
        logGroupName: `aws-waf-logs-story-${env}-alb`, retention: logs.RetentionDays.ONE_MONTH,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      });
      new wafv2.CfnLoggingConfiguration(this, "WafLogging", {
        resourceArn: this.webAcl.attrArn,
        logDestinationConfigs: [wafLogs.logGroupArn],
        redactedFields: [
          { singleHeader: { Name: "authorization" } },
          { singleHeader: { Name: "cookie" } },
          { singleHeader: { Name: "x-api-key" } },
        ],
      });
    }

    new cdk.CfnOutput(scope, "ApiLoadBalancerDns", {
      value: this.loadBalancer.loadBalancerDnsName,
      description: props.hostname ? `CNAME target for ${props.hostname}` : "ALB DNS name",
    });
    new cdk.CfnOutput(scope, "ApiBaseUrl", {
      value: props.hostname ? `https://${props.hostname}` : `http://${this.loadBalancer.loadBalancerDnsName}`,
      description: "Story API base URL (ECS)",
    });
  }
}
