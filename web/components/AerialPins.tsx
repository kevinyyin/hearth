"use client";

import { PIN_COLOR, pinLabels, tapToFraction } from "@/lib/home";
import type { OutsideKind, OutsidePin } from "@/lib/types";
import { useAuthedImage } from "@/lib/useAuthedImage";

const MAX_PINS = 50; // the API's cap

/** The building's aerial image with the resident's outside pins. With `onChange` a tap on the image places a pin of
 *  `kind` and a tap on a pin removes it; without it the pins are only shown. */
export default function AerialPins({ imagePath, pins, kind, onChange }: {
  imagePath: string;
  pins: OutsidePin[];
  kind?: OutsideKind;
  onChange?: (pins: OutsidePin[]) => void;
}) {
  const image = useAuthedImage(imagePath);
  const labels = pinLabels(pins);
  const route = pins.filter((p) => p.kind === "route");

  if (image === undefined) return <p className="text-xs" style={{ color: "var(--text-muted)" }}>Loading the aerial image…</p>;
  if (image === null) return <p className="text-xs" style={{ color: "var(--text-muted)" }}>No aerial image for this building.</p>;

  return (
    <div
      className="relative overflow-hidden rounded"
      style={{ cursor: onChange && kind ? "crosshair" : "default" }}
      onClick={(e) => {
        if (!onChange || !kind || pins.length >= MAX_PINS) return;
        onChange([...pins, { kind, ...tapToFraction(e, e.currentTarget.getBoundingClientRect()) }]);
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- an object URL from an authenticated fetch */}
      <img src={image} alt="Top-down aerial image of the building (Vexcel)" className="block w-full select-none" draggable={false} />
      {route.length > 1 && (
        <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
          <polyline points={route.map((p) => `${p.x * 100},${p.y * 100}`).join(" ")} fill="none" stroke={PIN_COLOR.route}
            strokeWidth={3} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        </svg>
      )}
      {pins.map((p, i) => {
        const body = (
          <>
            <span className="block h-3.5 w-3.5 rounded-full border-2 border-white shadow" style={{ background: PIN_COLOR[p.kind] }} />
            <span className="mt-0.5 rounded px-1 text-[10px] font-semibold leading-4 text-white" style={{ background: PIN_COLOR[p.kind] }}>
              {labels[i]}
            </span>
          </>
        );
        const at = { left: `${p.x * 100}%`, top: `${p.y * 100}%`, transform: "translate(-50%, -7px)" };
        return onChange ? (
          <button
            key={i}
            type="button"
            aria-label={`Remove ${labels[i]} pin`}
            className="absolute flex flex-col items-center"
            style={at}
            onClick={(e) => {
              e.stopPropagation();
              onChange(pins.filter((_, j) => j !== i));
            }}
          >
            {body}
          </button>
        ) : (
          <span key={i} className="absolute flex flex-col items-center" style={at}>{body}</span>
        );
      })}
    </div>
  );
}
