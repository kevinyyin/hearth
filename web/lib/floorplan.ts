// A schematic of the resident's floor, and a route across it that is actually
// planned rather than written down.
//
// The layout is a placeholder standing in for the room geometry the building
// lane pulls from CoStar and the Matterport scan: swap GRID for the real
// footprint and everything below keeps working. The point of doing it this way
// is that the crew's route is computed from the layout and the blockages, so
// when the resident says a hallway is blocked the path moves on its own instead
// of a sentence being rewritten.

export type Cell = { r: number; c: number };

/**
 * `#` wall, `.` open floor, `E` the way in from the stairwell, `M` the machine,
 * `X` something the resident told us is in the way.
 */
const GRID = [
  "########################",
  "#......................#",
  "#..M...................#",
  "#......................#",
  "#####........####......#",
  "#......X.......#.......#",
  "#..............#.......#",
  "#####.......####.......#",
  "#......................#",
  "#......................#",
  "#...................E..#",
  "########################",
];

export const ROWS = GRID.length;
export const COLS = GRID[0].length;

function findCell(ch: string): Cell {
  for (let r = 0; r < ROWS; r++) {
    const c = GRID[r].indexOf(ch);
    if (c !== -1) return { r, c };
  }
  throw new Error(`floor plan has no "${ch}"`);
}

export const ENTRANCE = findCell("E");
export const MACHINE = findCell("M");
export const BLOCKED = findCell("X");

export const isWall = (r: number, c: number): boolean => GRID[r][c] === "#";

/** Every wall cell, for drawing. */
export function wallCells(): Cell[] {
  const out: Cell[] = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) if (isWall(r, c)) out.push({ r, c });
  }
  return out;
}

const key = (r: number, c: number) => r * COLS + c;

/**
 * Breadth-first, four-way: on an unweighted grid that is the shortest route, and
 * it is short enough to run on every render. `avoid` is what the resident told us
 * about, so passing it empty shows the route the imagery alone would have given.
 */
export function planPath(avoid: Cell[] = [BLOCKED]): Cell[] {
  const blocked = new Set(avoid.map((c) => key(c.r, c.c)));
  const start = ENTRANCE;
  const goal = MACHINE;

  const prev = new Map<number, number>();
  const seen = new Set<number>([key(start.r, start.c)]);
  const queue: Cell[] = [start];

  while (queue.length) {
    const cur = queue.shift() as Cell;
    if (cur.r === goal.r && cur.c === goal.c) break;

    const steps: Cell[] = [
      { r: cur.r - 1, c: cur.c },
      { r: cur.r + 1, c: cur.c },
      { r: cur.r, c: cur.c - 1 },
      { r: cur.r, c: cur.c + 1 },
    ];

    for (const n of steps) {
      if (n.r < 0 || n.c < 0 || n.r >= ROWS || n.c >= COLS) continue;
      const k = key(n.r, n.c);
      if (seen.has(k) || blocked.has(k) || isWall(n.r, n.c)) continue;
      seen.add(k);
      prev.set(k, key(cur.r, cur.c));
      queue.push(n);
    }
  }

  const goalKey = key(goal.r, goal.c);
  if (!seen.has(goalKey)) return [];

  const path: Cell[] = [];
  let at: number | undefined = goalKey;
  while (at !== undefined) {
    path.push({ r: Math.floor(at / COLS), c: at % COLS });
    at = prev.get(at);
  }
  return path.reverse();
}

/** Drops the cells in the middle of a straight run, so the drawn route has corners, not dots. */
export function corners(path: Cell[]): Cell[] {
  if (path.length < 3) return path;
  const out: Cell[] = [path[0]];
  for (let i = 1; i < path.length - 1; i++) {
    const a = path[i - 1];
    const b = path[i];
    const c = path[i + 1];
    const straight = (a.r === b.r && b.r === c.r) || (a.c === b.c && b.c === c.c);
    if (!straight) out.push(b);
  }
  out.push(path[path.length - 1]);
  return out;
}

/** How far the crew walks, in cells, for the two routes worth comparing. */
export function routeLengths(): { planned: number; ifUnblocked: number } {
  return {
    planned: Math.max(planPath().length - 1, 0),
    ifUnblocked: Math.max(planPath([]).length - 1, 0),
  };
}
