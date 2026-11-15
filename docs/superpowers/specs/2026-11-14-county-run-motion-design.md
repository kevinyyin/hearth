# County run: motion and a live counter

**Why.** The county run on `/results` is the screen on the projector for the
2-minute demo. It should show "same fleet, different information" in a few
seconds without anyone reading the paragraph. The user pointed at another
project (Standard Response) for ideas, not for its look: Hearth keeps its own
light paper style.

**Goals.** A big live counter that pulls apart; crew trails that show chaining
vs out-and-back; a pulse when a home is reached.
**Non-goals.** A dark panel or dark basemap (tried, rejected by the user),
full-bleed layout, drawing all 23,273 registry points (the web app only has the
395 simulated ones).
**Anti-goals.** Copying the reference's look; a number that can be mistaken for
the 5,134 patient-hours on the same page.

## Approaches

1. **Motion and a counter on the existing paper map** (picked). Positron
   basemap, the existing state colours and shapes; add layers, not a theme.
2. Dark night panel with glowing homes. Built first, rejected: "background
   should not be black", and it copied the reference.
3. Full-screen map with floating panels. Dropped: too large a change this late.

## Design

- **Counter.** "Patients whose device ran out of power at home", Hearth with
  the central planner (p3__alns, the planner that routes the map's Hearth side)
  vs Today (p0), as a share of the sample with "N of 647" beside it, plus the
  ratio of the counts shown. The footnote says the sample is one in 36. From the engine's sweep
  (`ran_out_median`, brought over from the `people-count` branch) at the crew
  count picked at the top of the page, not from the browser replay: the replay
  only sends help once a device has already run out, so every household would
  count on both sides. A first version showed the replay's live wait-hours; the
  user rejected it as unreliable.
- **Trails.** Each crew's legs driven in the last 2 simulated hours, as ink
  lines that fade with age, under the dots.
- **Pulse.** A ring in the home's new colour that grows and fades over 0.4
  simulated hours when a job is served. Off under `prefers-reduced-motion`.
- The legend and per-side figures read the map's exported `FILL`.

Files: `web/lib/simulation.ts` (`trailsAt`, `arrivalsAt` on `CountySim`, with
tests), `web/app/results/page.tsx` (passes the sweep rows and crews), the
`people-count` sweep data, metric and type, `web/components/sim/HouseholdMap.tsx`,
`web/components/sim/FullRun.tsx`.
