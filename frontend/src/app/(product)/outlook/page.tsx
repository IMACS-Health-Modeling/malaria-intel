import { fetchOutlook } from "@/lib/data";
import { OutlookCanvas } from "./OutlookCanvas";

export default async function OutlookPage() {
  const data = await fetchOutlook();
  return <OutlookCanvas data={data} />;
}
