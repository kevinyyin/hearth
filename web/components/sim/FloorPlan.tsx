"use client";

import {
  BLOCKED,
  COLS,
  ENTRANCE,
  MACHINE,
  ROWS,
  corners,
  planPath,
  routeLengths,
  wallCells,
  type Cell,
} from "@/lib/floorplan";

const S = 14; // px per cell
const PAD = 8;

const cx = (c: number) => PAD + c * S + S / 2;
const cy = (r: number) => PAD + r * S + S / 2;

const MARKER = {
  entrance: { fill: "#0e7a54", label: "Entrance" },
  machine: { fill: "#6b4fd1", label: "Machine" },
  blocked: { fill: "#c4461a", label: "Blocked" },
} as const;

function Pin({
  cell,
  kind,
  shown,
}: {
  cell: Cell;
  kind: keyof typeof MARKER;
  shown: boolean;
}) {
  if (!shown) return null;
  const m = MARKER[kind];
  return (
    <g>
      <circle cx={cx(cell.c)} cy={cy(cell.r)} r={7} fill={m.fill} opacity={0.18} />
      <circle cx={cx(cell.c)} cy={cy(cell.r)} r={4} fill={m.fill} />
      <text
        x={cx(cell.c)}
        y={cy(cell.r) - 10}
        fontSize={9}
        fontWeight={600}
        textAnchor="middle"
        fill="var(--text-primary)"
      >
        {m.label}
      </text>
    </g>
  );
}

/**
 * The route is run through the layout rather than written down, so when the
 * resident reports something in the way the drawn path moves by itself.
 */
export default function FloorPlan({
  showEntrance = true,
  showMachine = true,
  showBlocked = true,
  showPath = true,
}: {
  showEntrance?: boolean;
  showMachine?: boolean;
  showBlocked?: boolean;
  showPath?: boolean;
}) {
  const path = corners(planPath(showBlocked ? [BLOCKED] : []));
  const { planned, ifUnblocked } = routeLengths();
  const detour = planned - ifUnblocked;

  const w = COLS * S + PAD * 2;
  const h = ROWS * S + PAD * 2;

  return (
    <div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="block w-full rounded-xl border"
        style={{ background: "var(--surface-0)", borderColor: "var(--border)" }}
        role="img"
        aria-label={`Third floor layout. The recommended path runs from the entrance to the machine in ${planned} steps${detour > 0 ? `, ${detour} more than if the hallway were clear` : ""}.`}
      >
        {wallCells().map((c, i) => (
          <rect
            key={i}
            x={PAD + c.c * S}
            y={PAD + c.r * S}
            width={S}
            height={S}
            fill="#e3ddcf"
          />
        ))}

        {showPath && path.length > 1 && (
          <polyline
            points={path.map((c) => `${cx(c.c)},${cy(c.r)}`).join(" ")}
            fill="none"
            stroke="var(--accent, #a8441a)"
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray="1 6"
          />
        )}

        <Pin cell={ENTRANCE} kind="entrance" shown={showEntrance} />
        <Pin cell={MACHINE} kind="machine" shown={showMachine} />
        <Pin cell={BLOCKED} kind="blocked" shown={showBlocked} />
      </svg>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs">
        {showPath && (
          <span className="flex items-center gap-1.5 font-semibold">
            <svg width="20" height="6" aria-hidden="true">
              <line
                x1="0"
                y1="3"
                x2="20"
                y2="3"
                stroke="var(--accent, #a8441a)"
                strokeWidth="2.5"
                strokeDasharray="1 5"
                strokeLinecap="round"
              />
            </svg>
            Recommended path
          </span>
        )}
        {(Object.keys(MARKER) as (keyof typeof MARKER)[]).map((k) => {
          const on =
            k === "entrance" ? showEntrance : k === "machine" ? showMachine : showBlocked;
          if (!on) return null;
          return (
            <span key={k} className="flex items-center gap-1.5" style={{ color: "var(--text-secondary)" }}>
              <svg width="10" height="10" viewBox="-5 -5 10 10" aria-hidden="true">
                <circle r={3.5} fill={MARKER[k].fill} />
              </svg>
              {MARKER[k].label}
            </span>
          );
        })}
      </div>

      {showPath && showBlocked && detour > 0 && (
        <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
          {detour} steps longer than the direct run, because the resident reported the hallway
          blocked. The route is planned over the layout, so it moved on its own.
        </p>
      )}
    </div>
  );
}
