"use client";

import { useQuery } from "@tanstack/react-query";

import { PaperMapView } from "@/components/paper-map/paper-map-view";
import { DashboardShell } from "@/components/shell/dashboard-shell";
import { formatIdMonthRange } from "@/lib/id-month";
import { fetchMap } from "@/lib/paper-map/paper-map-data";

/** Every paper from the map's months, placed by abstract similarity, with
 * the themes clustering found. A STATIC route that reads no API: the files
 * are `just paper-map`'s output, served from corpus/paper-map/ (D20). */
export default function MapPage() {
  const { data } = useQuery({ queryKey: ["paper-map"], queryFn: fetchMap, staleTime: Infinity });
  const meta = data?.meta;
  const range = meta ? formatIdMonthRange(meta.from_month, meta.to_month) : null;

  return (
    <DashboardShell current="map" trail={<li className="text-ink font-medium">Map</li>}>
      <div className="pt-2 pb-1">
        <h1 className="font-serif text-ink max-w-[24ch] text-[clamp(1.7rem,3.4vw,2.35rem)] leading-[1.1] font-bold text-balance">
          Paper map
        </h1>
        <p className="text-ink-2 mt-3 max-w-[62ch] text-[16px] leading-snug">
          {meta ? `${meta.n.toLocaleString("en")} arXiv cs papers` : "arXiv cs papers"}
          {range ? `, ${range},` : ""} placed by the similarity of their abstracts. Themes are
          grouped by AI and may be wrong.
        </p>
      </div>
      <PaperMapView />
    </DashboardShell>
  );
}
