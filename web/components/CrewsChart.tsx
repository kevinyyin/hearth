"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatHours, toChartRows, toSeries } from "@/lib/results";
import {
  DEFAULT_POLICIES,
  OPTIONAL_POLICIES,
  POLICY_ORDER,
  policyLabel,
  type PolicyId,
  type SweepRow,
} from "@/lib/types";

/**
 * Kept out of the main screen. The ablation is still in the sweep and still in the
 * repo's own write-ups; it is one line too many for a two-minute demo.
 */
const HIDDEN: PolicyId[] = ["p3__nomove", "p3__paired"];

/** Colour follows the policy, never its rank, so a toggle never repaints the survivors. */
function seriesColor(policy: string): string {
  const slot = POLICY_ORDER.indexOf(policy as PolicyId);
  return `var(--series-${slot === -1 ? 1 : slot + 1})`;
}



type TooltipPayload = { dataKey?: string | number; value?: number; color?: string };

function ChartTooltip({
  active,
  payload,
  label,
  weighted,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: number | string;
  weighted: boolean;
}) {
  if (!active || !payload?.length) return null;

  // Only the median lines carry a plain policy id as their dataKey; band keys are suffixed.
  const lines = payload.filter(
    (p) => typeof p.dataKey === "string" && !p.dataKey.includes("__lo") && !p.dataKey.includes("__span"),
  );
  if (!lines.length) return null;

  return (
    <div
      className="rounded-md border px-3 py-2 text-xs shadow-lg"
      style={{
        background: "var(--surface-1)",
        borderColor: "var(--border)",
        color: "var(--text-primary)",
      }}
    >
      <div className="mb-1.5 font-medium" style={{ color: "var(--text-secondary)" }}>
        {label} crews · {weighted ? "risk-weighted" : "unweighted"}
      </div>
      <table className="border-separate border-spacing-x-2 border-spacing-y-0.5">
        <tbody>
          {lines
            .slice()
            .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
            .map((p) => (
              <tr key={String(p.dataKey)}>
                <td>
                  <span
                    aria-hidden
                    className="inline-block size-2.5 rounded-sm"
                    style={{ background: p.color }}
                  />
                </td>
                <td style={{ color: "var(--text-secondary)" }}>{policyLabel(String(p.dataKey))}</td>
                <td className="tnum text-right font-medium">
                  {p.value == null ? "—" : formatHours(p.value)}
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CrewsChart({
  rows,
  selectedCrews,
  comparison,
}: {
  rows: SweepRow[];
  /** Marked with a rule on the x axis, so the card's crew count is visible here too. */
  selectedCrews?: number | null;
  /** When set, the chart opens on Hearth against this one policy; the legend still toggles the rest. */
  comparison?: PolicyId;
}) {
  // Always risk-weighted: the unweighted view was a toggle nobody used in a demo.
  const weighted = true;
  const [shown, setShown] = useState<string[]>(
    comparison ? ["p3", comparison] : [...DEFAULT_POLICIES],
  );
  const [showTable, setShowTable] = useState(false);

  // The card drives which comparison is drawn. A legend click after that still wins,
  // until the card changes again.
  useEffect(() => {
    if (comparison) setShown(["p3", comparison]);
  }, [comparison]);

  const allSeries = useMemo(
    () => toSeries(rows, weighted).filter((s) => !HIDDEN.includes(s.policy as PolicyId)),
    [rows, weighted],
  );
  // the crew counts come from the sweep file (sweep.crews in assumptions.yaml), not from the page
  const crewTicks = useMemo(() => [...new Set(rows.map((r) => r.crews))].sort((a, b) => a - b), [rows]);
  const visible = useMemo(
    () => allSeries.filter((s) => shown.includes(s.policy)),
    [allSeries, shown],
  );
  const chartRows = useMemo(() => toChartRows(visible), [visible]);

  const toggle = (policy: string) =>
    setShown((prev) =>
      prev.includes(policy) ? prev.filter((p) => p !== policy) : [...prev, policy],
    );

  return (
    <section
      className="rounded-xl border p-5"
      style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
    >
      {/* Filters in one row above the chart. */}
      <div className="mb-5 flex flex-wrap items-center gap-x-6 gap-y-3">
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          className="rounded-lg border px-3 py-1.5 text-sm font-medium"
          style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
          aria-expanded={showTable}
        >
          {showTable ? "Hide table" : "Show table"}
        </button>
      </div>

      <div className="h-[420px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          {/* top leaves room for the selected-crews label the reference line hangs above the plot */}
          <ComposedChart data={chartRows} margin={{ top: 26, right: 16, bottom: 28, left: 8 }}>
            <CartesianGrid stroke="var(--grid)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="crews"
              type="number"
              scale="log"
              domain={[crewTicks[0] / 1.15, crewTicks[crewTicks.length - 1] * 1.15]}
              ticks={crewTicks}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tick={{ fill: "var(--text-muted)", fontSize: 12 }}
              label={{
                value: "Delivery crews",
                position: "insideBottom",
                offset: -16,
                fill: "var(--text-secondary)",
                fontSize: 12,
              }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={96}
              tick={{ fill: "var(--text-muted)", fontSize: 12 }}
              tickFormatter={(v: number) => formatHours(v)}
              label={{
                value: weighted
                  ? "Median patient-hours at risk"
                  : "Unweighted median patient-hours at risk",
                angle: -90,
                position: "insideLeft",
                offset: 6,
                style: { textAnchor: "middle", fill: "var(--text-secondary)", fontSize: 12 },
              }}
            />
            <Tooltip
              content={<ChartTooltip weighted={weighted} />}
              cursor={{ stroke: "var(--text-muted)", strokeDasharray: "3 3" }}
            />

            {selectedCrews != null && (
              <ReferenceLine
                x={selectedCrews}
                stroke="var(--accent, var(--text-muted))"
                strokeDasharray="4 4"
                label={{
                  value: `${selectedCrews} crews`,
                  position: "top",
                  fill: "var(--accent, var(--text-secondary))",
                  fontSize: 11,
                }}
              />
            )}

            {/* p5..p95 band: an invisible floor plus a tinted span, stacked per policy. */}
            {weighted &&
              visible.map((s) => [
                <Area
                  key={`${s.policy}__lo`}
                  dataKey={`${s.policy}__lo`}
                  stackId={s.policy}
                  stroke="none"
                  fill="none"
                  isAnimationActive={false}
                  activeDot={false}
                  legendType="none"
                />,
                <Area
                  key={`${s.policy}__span`}
                  dataKey={`${s.policy}__span`}
                  stackId={s.policy}
                  stroke="none"
                  fill={seriesColor(s.policy)}
                  fillOpacity={0.14}
                  isAnimationActive={false}
                  activeDot={false}
                  legendType="none"
                />,
              ])}

            {visible.map((s) => (
              <Line
                key={s.policy}
                dataKey={s.policy}
                name={s.label}
                type="monotone"
                stroke={seriesColor(s.policy)}
                strokeWidth={2}
                dot={{ r: 4, strokeWidth: 0, fill: seriesColor(s.policy) }}
                activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--surface-1)" }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Legend doubles as the policy filter: the first three are on, the last two are toggles. */}
      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm">
        {allSeries.map((s) => {
          const on = shown.includes(s.policy);
          const optional = OPTIONAL_POLICIES.includes(s.policy as PolicyId);
          return (
            <li key={s.policy}>
              <button
                type="button"
                onClick={() => toggle(s.policy)}
                aria-pressed={on}
                className="flex items-center gap-2 transition-opacity"
                style={{ opacity: on ? 1 : 0.45, color: "var(--text-secondary)" }}
              >
                <span
                  aria-hidden
                  className="inline-block h-0.5 w-4 rounded-full"
                  style={{ background: on ? seriesColor(s.policy) : "var(--text-muted)" }}
                />
                <span className={on ? "font-medium" : undefined}>{s.label}</span>
                {optional && (
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {on ? "on" : "off"}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>

      {showTable && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Median patient-hours at risk by policy and crew count
            </caption>
            <thead>
              <tr style={{ color: "var(--text-muted)" }}>
                <th scope="col" className="py-2 pr-4 text-left font-medium">
                  Policy
                </th>
                {crewTicks.map((c) => (
                  <th scope="col" key={c} className="py-2 pr-4 text-right font-medium">
                    {c} crews
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {allSeries.map((s) => (
                <tr key={s.policy} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <th scope="row" className="py-2 pr-4 text-left font-normal">
                    <span className="flex items-center gap-2">
                      <span
                        aria-hidden
                        className="inline-block h-0.5 w-4 rounded-full"
                        style={{ background: seriesColor(s.policy) }}
                      />
                      {s.label}
                    </span>
                  </th>
                  {crewTicks.map((c) => {
                    const point = s.points.find((p) => p.crews === c);
                    return (
                      <td key={c} className="tnum py-2 pr-4 text-right">
                        {point == null ? (
                          "—"
                        ) : (
                          <>
                            {formatHours(point.y)}
                            {point.lo !== undefined && point.hi !== undefined && (
                              <span className="ml-1 text-xs" style={{ color: "var(--text-muted)" }}>
                                ({formatHours(point.lo)}–{formatHours(point.hi)})
                              </span>
                            )}
                          </>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
            {weighted
              ? "Median patient-hours at risk, with the 5th–95th percentile across seeds in parentheses."
              : "Unweighted median patient-hours at risk."}
          </p>
        </div>
      )}
    </section>
  );
}
