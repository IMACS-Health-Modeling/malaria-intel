import { fetchUSEcosystem } from "@/lib/data";
import { EcosystemCanvasClient } from "./EcosystemCanvasClient";

export default async function EcosystemPage() {
  const data = await fetchUSEcosystem();
  return <EcosystemCanvasClient data={data} />;
}
