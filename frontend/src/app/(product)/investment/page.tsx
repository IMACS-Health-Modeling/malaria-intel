import { fetchInvestment, fetchGeographicSpend } from "@/lib/data";
import { InvestmentCanvasClient } from "./InvestmentCanvasClient";

export default async function InvestmentPage() {
  const [data, geoSpend] = await Promise.all([fetchInvestment(), fetchGeographicSpend()]);
  return <InvestmentCanvasClient data={data} geoSpend={geoSpend} />;
}
