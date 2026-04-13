import { fetchImpact, fetchCaseTrends } from "@/lib/data";
import { ImpactCanvas } from "./ImpactCanvas";

export default async function ImpactPage() {
  const [data, trends] = await Promise.all([fetchImpact(), fetchCaseTrends()]);
  return <ImpactCanvas data={data} trends={trends} />;
}
