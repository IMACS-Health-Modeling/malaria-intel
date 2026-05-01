import { create } from "zustand";

export type MapLayer = "burden" | "outbreaks" | "climate";

interface IntelStore {
  // Active map layers
  activeLayers: MapLayer[];
  toggleLayer: (layer: MapLayer) => void;
  hasLayer: (layer: MapLayer) => boolean;

  // Selected country
  selectedIso3: string | null;
  setSelectedIso3: (iso3: string | null) => void;

  // Scrubber year (for timeseries charts)
  year: number;
  setYear: (year: number) => void;
  playing: boolean;
  setPlaying: (v: boolean) => void;
}

export const useIntelStore = create<IntelStore>((set, get) => ({
  activeLayers: ["burden", "outbreaks"],
  toggleLayer: (layer) =>
    set((s) => ({
      activeLayers: s.activeLayers.includes(layer)
        ? s.activeLayers.filter((l) => l !== layer)
        : [...s.activeLayers, layer],
    })),
  hasLayer: (layer) => get().activeLayers.includes(layer),

  selectedIso3: null,
  setSelectedIso3: (iso3) => set({ selectedIso3: iso3 }),

  year: 2023,
  setYear: (year) => set({ year }),
  playing: false,
  setPlaying: (playing) => set({ playing }),
}));
