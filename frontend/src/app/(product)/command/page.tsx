import {
  getGlobalSummary,
  getCommandCountries,
  getActiveThreats,
  getGlobalTimeseries,
  getEndemicBoundaries,
} from "@/lib/data";
import { CommandCanvas } from "./CommandCanvas";

export default async function CommandPage() {
  const [summary, countries, threats, timeseries, boundaries] = await Promise.all([
    getGlobalSummary(),
    getCommandCountries(),
    getActiveThreats(),
    getGlobalTimeseries(),
    getEndemicBoundaries(),
  ]);

  return (
    <CommandCanvas
      summary={summary}
      countries={countries}
      threats={threats}
      timeseries={timeseries}
      boundaries={boundaries}
    />
  );
}
