/** Shared types and constants for the US map — safe to import in client components */

export const MAP_W = 975;
export const MAP_H = 610;

export interface StatePath {
  /** Display name normalised to match StateData.name */
  stateName: string;
  /** SVG path string pre-computed server-side with geoAlbersUsa */
  d: string;
  /** Centroid [x, y] in SVG coordinate space */
  centroid: [number, number] | null;
}
