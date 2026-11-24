import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as sns from "aws-cdk-lib/aws-sns";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as cwactions from "aws-cdk-lib/aws-cloudwatch-actions";
import * as path from "path";

/**
 * Account deletion D2 (design: specs/story-specs/spec/implementation-plan/account-deletion-design.md, 5.2, 5.4,
 * 5.11). One request table (source of truth + ledger), one Lambda triggered ONLY by a 5-minute EventBridge rule
 * (no queue), and a worker role that holds exactly the operation-to-permission matrix of section 5.11.
 *
 * Inert until D3: nothing creates request items except the operator CLI, so each run scans an empty table.
 */
export interface AccountDeletionProps {
  environment: string;
  /** Same-stack tables (ARNs known). */
  mediaTable: dynamodb.ITable;
  storiesTable: dynamodb.ITable;
  understandingTable: dynamodb.ITable;
  rateLimitTable: dynamodb.ITable;
  jobsTable: dynamodb.ITable;
  mediaBucket: s3.IBucket;
  stagingBucket: s3.IBucket;
  /** Auth-stack tables, referenced by name (the api stack has no hard dependency on the auth stack). */
  usersTableName: string;
  identityClaimsTableName: string;
  userUsageTableName: string;
  /** The SAME resolved pool id the API uses (non-dev environments fail synth without an explicit one). */
  userPoolId: string;
  /** Observability SNS topic; alarms are created only when it exists. */
  alarmTopic?: sns.ITopic;
}

const RETENTION: Record<string, logs.RetentionDays> = {
  development: logs.RetentionDays.ONE_MONTH,
  beta: logs.RetentionDays.TWO_MONTHS,
  production: logs.RetentionDays.THREE_MONTHS,
};

export class AccountDeletion extends Construct {
  public readonly table: dynamodb.Table;
  public readonly worker: lambda.Function;
  public readonly rule: events.Rule;
  public readonly operatorRole: iam.Role;
  public readonly alarms: cloudwatch.Alarm[] = [];

  constructor(scope: Construct, id: string, props: AccountDeletionProps) {
    super(scope, id);
    const env = props.environment;
    const stack = cdk.Stack.of(this);
    const tableArn = (name: string) => `arn:aws:dynamodb:${stack.region}:${stack.account}:table/${name}`;

    // ---- request table (design 5.2): PK pk, SK sk; never deleted, never expired --------------------------
    this.table = new dynamodb.Table(this, "RequestsTable", {
      tableName: `story-${env}-account-deletions`,
      partitionKey: { name: "pk", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "sk", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecovery: true,
      deletionProtection: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // ---- worker Lambda (design 5.4): same zip asset as the edit-plan worker --------------------------------
    const logGroup = new logs.LogGroup(this, "WorkerLogs", {
      logGroupName: `/aws/lambda/story-${env}-account-deletion`,
      retention: RETENTION[env] ?? logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });
    this.worker = new lambda.Function(this, "Worker", {
      functionName: `story-${env}-account-deletion`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "account_deletion.worker.handler",
      code: lambda.Code.fromAsset(path.join(__dirname, "..", ".worker-asset")),
      timeout: cdk.Duration.seconds(300),     // run budget 240 s; lease 360 s > timeout
      memorySize: 512,
      logGroup,
      // No reserved concurrency (a fresh account's limit of 10 forbids it). The conditional lease is the
      // mutual exclusion between overlapping runs.
      environment: {
        PYTHONPATH: "/var/task:/var/task/packages",
        STORY_ENVIRONMENT: env,
        STORY_ACCOUNT_DELETIONS_TABLE: this.table.tableName,
        STORY_USERS_TABLE: props.usersTableName,
        STORY_IDENTITY_CLAIMS_TABLE: props.identityClaimsTableName,
        STORY_USER_USAGE_TABLE: props.userUsageTableName,
        STORY_MEDIA_TABLE: props.mediaTable.tableName,
        STORY_STORIES_TABLE: props.storiesTable.tableName,
        STORY_UNDERSTANDING_TABLE: props.understandingTable.tableName,
        STORY_RATE_LIMIT_TABLE: props.rateLimitTable.tableName,
        STORY_JOBS_TABLE: props.jobsTable.tableName,
        STORY_MEDIA_BUCKET: props.mediaBucket.bucketName,
        STORY_STAGING_BUCKET: props.stagingBucket.bucketName,
        STORY_COGNITO_USER_POOL_ID: props.userPoolId,
      },
    });

    // ---- schedule: every 5 minutes, no retries, no stacking of old events ----------------------------------
    this.rule = new events.Rule(this, "Schedule", {
      ruleName: `story-${env}-account-deletion`,
      schedule: events.Schedule.rate(cdk.Duration.minutes(5)),
    });
    this.rule.addTarget(new targets.LambdaFunction(this.worker, {
      retryAttempts: 0,
      maxEventAge: cdk.Duration.minutes(5),
    }));

    // ---- IAM: the operation-to-permission matrix (design 5.11) ---------------------------------------------
    // Break-glass operator role (design 5.10, 5.11): the same grants as the worker, for the operator CLI
    // (count / request / resume / replay-after-restore). Assumable only by IAM principals of THIS account that are
    // themselves allowed sts:AssumeRole on it (the SSO administrator), 1-hour sessions, never by a service.
    this.operatorRole = new iam.Role(this, "OperatorRole", {
      roleName: `story-${env}-account-deletion-operator`,
      description: "Break-glass role for the account-deletion operator CLI (same grants as the worker)",
      assumedBy: new iam.AccountRootPrincipal(),
      maxSessionDuration: cdk.Duration.hours(1),
    });
    const allow = (sid: string, actions: string[], resources: string[], conditions?: Record<string, any>) => {
      const st = () => new iam.PolicyStatement({ sid, effect: iam.Effect.ALLOW, actions, resources,
                                                 ...(conditions ? { conditions } : {}) });
      this.worker.addToRolePolicy(st());
      this.operatorRole.addToPolicy(st());
    };
    // request table: no DeleteItem (request, child and pointer items are never deleted)
    allow("DeletionRequests", ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query",
                               "dynamodb:Scan"], [this.table.tableArn]);
    // users row: read + tombstone (UpdateItem); never PutItem or DeleteItem
    allow("UsersTombstone", ["dynamodb:GetItem", "dynamodb:UpdateItem"], [tableArn(props.usersTableName)]);
    allow("ContentDelete", ["dynamodb:Query", "dynamodb:BatchWriteItem", "dynamodb:DeleteItem"],
          [props.mediaTable.tableArn, props.storiesTable.tableArn, props.understandingTable.tableArn,
           props.rateLimitTable.tableArn]);
    // usage partition + global Apple bindings (8.2(a): delete). DeleteItem cannot be scoped to one uid
    // (dynamodb:LeadingKeys needs a per-request value); compensated by acting only on leased request items.
    allow("UsageDelete", ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:BatchWriteItem", "dynamodb:DeleteItem"],
          [tableArn(props.userUsageTableName)]);
    allow("JobsCancelDelete", ["dynamodb:Scan", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"],
          [props.jobsTable.tableArn]);
    allow("MediaList", ["s3:ListBucket"], [props.mediaBucket.bucketArn],
          { StringLike: { "s3:prefix": ["media/*", "evidence/*"] } });
    // ListBucketMultipartUploads is granted without an s3:prefix condition: the prefix key is documented for
    // ListBucket, and an unevaluated condition key would deny every call. It lists upload keys only.
    allow("MediaListUploads", ["s3:ListBucketMultipartUploads"], [props.mediaBucket.bucketArn]);
    allow("MediaDelete", ["s3:DeleteObject", "s3:AbortMultipartUpload"],
          [props.mediaBucket.arnForObjects("media/*"), props.mediaBucket.arnForObjects("evidence/*")]);
    allow("StagingList", ["s3:ListBucket"], [props.stagingBucket.bucketArn],
          { StringLike: { "s3:prefix": ["jobs/*"] } });
    allow("StagingDelete", ["s3:DeleteObject"], [props.stagingBucket.arnForObjects("jobs/*")]);
    allow("CognitoAccountDeletion",
          ["cognito-idp:AdminDisableUser", "cognito-idp:AdminUserGlobalSignOut", "cognito-idp:AdminGetUser",
           "cognito-idp:ListUsers", "cognito-idp:AdminDeleteUser"],
          [`arn:aws:cognito-idp:${stack.region}:${stack.account}:userpool/${props.userPoolId}`]);

    // Operator only: replay into PITR-restored copies of the auth tables (design 5.8). Restore them under a name
    // containing "-restored" (e.g. story-<env>-users-restored-20261201); nothing else matches.
    this.operatorRole.addToPolicy(new iam.PolicyStatement({
      sid: "RestoreReplay", effect: iam.Effect.ALLOW,
      actions: ["dynamodb:Scan", "dynamodb:Query", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem",
                "dynamodb:BatchWriteItem"],
      resources: [`arn:aws:dynamodb:${stack.region}:${stack.account}:table/story-${env}-*-restored*`],
    }));

    // ---- alarms (design 5.4), only where the Observability SNS topic exists ---------------------------------
    if (props.alarmTopic) {
      const action = new cwactions.SnsAction(props.alarmTopic);
      const m = (name: string, statistic: string) => new cloudwatch.Metric({
        namespace: "Story/Beta", metricName: name, statistic, period: cdk.Duration.minutes(5),
        dimensionsMap: { env },
      });
      const GTE = cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD;
      const mk = (id: string, metric: cloudwatch.IMetric, threshold: number, evaluationPeriods: number,
                  op: cloudwatch.ComparisonOperator, missing: cloudwatch.TreatMissingData) => {
        const a = new cloudwatch.Alarm(this, id, {
          alarmName: `story-${env}-${id}`, metric, threshold, evaluationPeriods, comparisonOperator: op,
          treatMissingData: missing,
        });
        a.addAlarmAction(action);
        this.alarms.push(a);
      };
      const NB = cloudwatch.TreatMissingData.NOT_BREACHING;
      mk("account-deletion-stalled", m("AccountDeletionStalled", "Sum"), 1, 1, GTE, NB);
      mk("account-deletion-overdue", m("AccountDeletionOverdue", "Maximum"), 1, 1, GTE, NB);
      mk("account-deletion-late-found", m("AccountDeletionLateFound", "Sum"), 1, 1, GTE, NB);
      // no heartbeat for 30 minutes (6 periods): a disabled rule or a Lambda failing at import
      mk("account-deletion-heartbeat-missing", m("AccountDeletionHeartbeat", "Sum"), 1, 6,
         cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD, cloudwatch.TreatMissingData.BREACHING);
      mk("account-deletion-errors", this.worker.metricErrors({ period: cdk.Duration.minutes(5), statistic: "Sum" }),
         1, 1, GTE, NB);
    }

    new cdk.CfnOutput(scope, "AccountDeletionsTableName", { value: this.table.tableName });
    new cdk.CfnOutput(scope, "AccountDeletionWorkerName", { value: this.worker.functionName });
    new cdk.CfnOutput(scope, "AccountDeletionOperatorRoleArn", { value: this.operatorRole.roleArn });
  }
}
