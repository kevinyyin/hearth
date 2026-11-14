"use client";

import AerialPins from "@/components/AerialPins";
import ScanPins from "@/components/ScanPins";
import FloorPlan from "@/components/sim/FloorPlan";
import { useBuildingFeed } from "@/lib/simSource";
import type { InsidePin, OutsidePin } from "@/lib/types";

/**
 * The building as the sponsor data actually has it, rather than as a drawing.
 *
 * Worth being precise about which source is which, because "the CoStar map" is
 * three different things:
 *   - CoStar is a records extract. It has stories, construction, elevators and
 *     the Matterport model ids. It has no imagery and no floor polygon.
 *   - The outside view is Vexcel's top-down tile, served by the API at
 *     /api/buildings/<id>/image behind the password.
 *   - The inside view is a Matterport scan, opened from the model id CoStar
 *     listed, with the SDK key the API hands over.
 *
 * So there is no floor plan to fetch from anyone. When a scan exists we open it
 * from above, which is the nearest real thing; when none of it is reachable the
 * schematic below is a stand-in and says so.
 */
export default function BuildingViews({
  buildingId,
  outside = [],
  inside = [],
}: {
  buildingId: string | null;
  outside?: OutsidePin[];
  inside?: InsidePin[];
}) {
  const { data, source, detail, error } = useBuildingFeed(buildingId);

  const live = source === "api" && !!data;
  const scanId = data?.scan_ids?.[0] ?? null;
  const imagePath = data?.image_url ?? (buildingId ? `/api/buildings/${buildingId}/image` : null);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold">The building itself</h3>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          {live ? `${data?.name ?? buildingId} · ${detail}` : "no building data reachable"}
          {error && ` · ${error}`}
        </p>
      </div>

      {/* --- outside: Vexcel --- */}
      <h4 className="mb-1.5 text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>
        Outside — Vexcel aerial
      </h4>
      {live && imagePath ? (
        <AerialPins imagePath={imagePath} pins={outside} />
      ) : (
        <p
          className="rounded-lg border px-3 py-2 text-xs"
          style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
        >
          No aerial tile here. Vexcel is fetched by the API with its own key; point
          NEXT_PUBLIC_API at a Hearth API that has one and the real tile appears, with the
          resident&rsquo;s parking and entrance pins on it.
        </p>
      )}

      {/* --- inside: Matterport --- */}
      <h4
        className="mt-4 mb-1.5 text-xs font-semibold"
        style={{ color: "var(--text-secondary)" }}
      >
        Inside — Matterport scan
      </h4>
      {live && scanId ? (
        <ScanPins
          scanId={scanId}
          sdkKey={data?.scan_sdk_key ?? null}
          pins={inside}
          view="floorplan"
        />
      ) : (
        <div
          className="rounded-lg border px-3 py-2.5 text-xs"
          style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
        >
          {live ? (
            "CoStar lists no Matterport model for this building, so there is no interior to open. Most apartment models in the kit are unit floor plans rather than entrances; hotel lobby scans are the ones that show a way in."
          ) : (
            <>
              <strong style={{ color: "var(--text-primary)" }}>
                The 3D space cannot load on this machine.
              </strong>{" "}
              The walkthrough is Matterport&rsquo;s, opened in an iframe with a viewer key that only
              the API holds, from a model id that only the CoStar extract holds. Neither is in this
              checkout, and neither can be — the key would be in the browser bundle and the extract
              is kept out of the repository on purpose. Set{" "}
              <code>NEXT_PUBLIC_API</code> to a Hearth API that has both and the real scan opens
              here, from above, with the resident&rsquo;s pins in it.
            </>
          )}
        </div>
      )}

      {/* --- the stand-in, and the route, which no source provides --- */}
      <h4
        className="mt-4 mb-1.5 text-xs font-semibold"
        style={{ color: "var(--text-secondary)" }}
      >
        Recommended path — planned, not fetched
      </h4>
      <FloorPlan showEntrance showMachine showBlocked showPath />
      <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
        Neither CoStar nor Matterport gives a floor polygon, so the grid this route is planned
        over is a schematic. The planning is real — it runs over the layout and around what the
        resident reported — but the layout is a stand-in until someone traces one from a scan.
      </p>
    </div>
  );
}
