"use client";

import AerialPins from "@/components/AerialPins";
import ScanPins from "@/components/ScanPins";
import { useBuildingFeed, useEntranceFeed } from "@/lib/simSource";
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
 * from above, which is the nearest real thing, and the route is drawn on that.
 * With no scan there is no route: nothing is drawn over an invented layout.
 */
export default function BuildingViews({
  buildingId,
  preferredScanId = null,
  outside = [],
  inside = [],
}: {
  buildingId: string | null;
  /** The scan the resident picked. /resident opens this one, so this does too. */
  preferredScanId?: string | null;
  outside?: OutsidePin[];
  inside?: InsidePin[];
}) {
  const { data, source, detail, error } = useBuildingFeed(buildingId);

  // Three states, not two. "No API configured" and "an API answered badly" look
  // the same to the render but are opposite problems, and saying the wrong one
  // sends people to go fix something that is already right.
  const configured = source === "api";
  const live = configured && !!data;
  const listed = data?.scan_ids ?? [];
  const scanId =
    preferredScanId && listed.includes(preferredScanId)
      ? preferredScanId
      : (listed[0] ?? null);
  const imagePath = data?.image_url ?? (buildingId ? `/api/buildings/${buildingId}/image` : null);

  // The resident's own entrance pin wins. Without one the API reads the way in off the tile.
  const marked = outside.some((p) => p.kind === "entrance");
  const read = useEntranceFeed(live && !marked ? buildingId : null).data;
  const outsidePins = read ? [...outside, { kind: "entrance" as const, x: read.x, y: read.y }] : outside;

  return (
    <div>
      {/* The record loads from the fixture too, so the address shows either way;
          only the imagery below depends on an API being there. */}
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold">
          {data?.address ?? data?.name ?? "The building itself"}
        </h3>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          {data
            ? `${data.building_id} · ${live ? "CoStar record" : "fixture record"}`
            : !buildingId
              ? "this resident has not picked a building yet"
              : error
                ? `no record: ${error}`
                : "looking up the record…"}
        </p>
      </div>

      {/* --- outside: Vexcel --- */}
      <h4 className="mb-1.5 text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>
        Outside — Vexcel aerial
      </h4>
      {live && imagePath ? (
        <>
          <AerialPins imagePath={imagePath} pins={outsidePins} />
          {read && (
            <p className="mt-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
              The resident has not marked a way in, so this entrance is a vision model&rsquo;s reading of the tile: {read.note}
            </p>
          )}
        </>
      ) : (
        <p
          className="rounded-lg border px-3 py-2 text-xs"
          style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
        >
          {configured
            ? "No aerial tile. The API is configured, so this is that API not returning this building — check the id above against what it serves, and whether the request carried the password."
            : "No aerial tile here. Vexcel is fetched by the API with its own key; point NEXT_PUBLIC_API at a Hearth API that has one and the real tile appears, with the resident's parking and entrance pins on it."}
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
          route
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
                No scan reachable from here.
              </strong>{" "}
              The walkthrough is Matterport&rsquo;s, opened with a model id and a viewer key the API
              hands over — the same ones the resident screen uses, so where that screen shows a scan
              this one will too.{" "}
              {configured
                ? "An API is configured, so this is that API not returning this building rather than a missing setting."
                : "This build has no NEXT_PUBLIC_API, so there is nothing to ask."}
            </>
          )}
        </div>
      )}
    </div>
  );
}
