import { Template } from "aws-cdk-lib/assertions";

/** The API container's environment as {Name, Value} pairs, read from the ECS task definition (every stage). During the
 * beta overlap the App Runner service must carry exactly the same list; this helper asserts that too. */
export function apiEnvVars(t: Template): Array<{ Name: string; Value: any }> {
  const tds = Object.values(t.findResources("AWS::ECS::TaskDefinition")) as any[];
  const api = tds.flatMap((td) => td.Properties.ContainerDefinitions as any[]).filter((c) => c.Name === "api");
  if (api.length !== 1) throw new Error(`expected exactly one api container, found ${api.length}`);
  const ecsEnv: Array<{ Name: string; Value: any }> = api[0].Environment ?? [];
  const ar = Object.values(t.findResources("AWS::AppRunner::Service")) as any[];
  if (ar.length) {
    const arEnv = ar[0].Properties.SourceConfiguration.ImageRepository.ImageConfiguration.RuntimeEnvironmentVariables;
    const norm = (l: Array<{ Name: string; Value: any }>) =>
      JSON.stringify([...l].map((e) => [e.Name, e.Value]).sort((a, b) => String(a[0]).localeCompare(String(b[0]))));
    if (norm(arEnv) !== norm(ecsEnv)) throw new Error("App Runner and ECS env lists differ");
  }
  return ecsEnv;
}

export function apiEnvMap(t: Template): Record<string, any> {
  return Object.fromEntries(apiEnvVars(t).map((e) => [e.Name, e.Value]));
}
