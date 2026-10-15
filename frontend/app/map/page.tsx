"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { MapScopeTabs } from "@/components/paper-map/map-scope-tabs";
import { PaperMapView } from "@/components/paper-map/paper-map-view";
import { DashboardShell } from "@/components/shell/dashboard-shell";
import { formatIdMonthRange } from "@/lib/id-month";
import { fetchMap, type MapScope, parseScope } from "@/lib/paper-map/paper-map-data";

/** Papers placed by abstract similarity, with the themes clustering found:
 * the recent complete months by default, the full catalog on its tab
 * (`?scope=full`). A STATIC route that reads no API: the files are `just
 * paper-map`'s output, served from corpus/paper-map/<scope>/ (D20). */
function MapContent() {
  const scope = parseScope(useSearchParams().get("scope"));
  const router = useRouter();
  const pathname = usePathname();
  const { data } = useQuery({
    queryKey: ["paper-map", scope],
    queryFn: () => fetchMap(scope),
    staleTime: Infinity,
  });
  const meta = data?.meta;
  const range = meta ? formatIdMonthRange(meta.from_month, meta.to_month) : null;

  function choose(next: MapScope) {
    router.replace(next === "recent" ? pathname : `${pathname}?scope=${next}`, { scroll: false });
  }

  return (
    <DashboardShell current="map" trail={<li className="text-ink font-medium">Map</li>}>
      <div className="flex flex-col gap-4 pt-2 pb-1">
        <div>
          <h1 className="font-serif text-ink max-w-[24ch] text-[clamp(1.7rem,3.4vw,2.35rem)] leading-[1.1] font-bold text-balance">
            Paper map
          </h1>
          <p className="text-ink-2 mt-3 max-w-[62ch] text-[16px] leading-snug">
            {meta ? `${meta.n.toLocaleString("en")} arXiv cs papers` : "arXiv cs papers"}
            {range ? `, ${range},` : ""} placed by the similarity of their abstracts. Themes are
            grouped by AI and may be wrong.
          </p>
        </div>
        <MapScopeTabs scope={scope} onChange={choose} />
      </div>
      <PaperMapView key={scope} scope={scope} />
    </DashboardShell>
  );
}

export default function MapPage() {
  return (
    // `useSearchParams` needs a boundary in a static export build.
    <Suspense fallback={null}>
      <MapContent />
    </Suspense>
  );
}
