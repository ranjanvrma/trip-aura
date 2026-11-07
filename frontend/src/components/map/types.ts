import type { LatLng } from "../../types";

export interface MapMarker {
  id: string;
  position: LatLng;
  label: string;          // short text inside the pin ("H", "1", "B"...)
  title: string;          // tooltip
  kind: "home" | "activity" | "meal" | "rest";
  color: string;
}

export interface MapPolyline {
  id: string;
  path: LatLng[];
  color: string;
  dashed?: boolean;       // walking legs are drawn dashed
}

export interface MapViewProps {
  markers: MapMarker[];
  polylines: MapPolyline[];
  current?: { position: LatLng; accuracy: number | null } | null;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}
