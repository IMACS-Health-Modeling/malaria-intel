import { fetchWorldMap } from "@/lib/data";
import { FlowsCanvasClient } from "./FlowsCanvasClient";

export default async function FlowsPage() {
  const data = await fetchWorldMap();
  return <FlowsCanvasClient data={data} />;
}
