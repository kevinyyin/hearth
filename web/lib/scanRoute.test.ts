import { describe, expect, it } from "vitest";
import { nearestSpot, scanRoute, type Spot } from "./scanRoute";

const at = (x: number, z: number, neighbors: string[], enabled = true): Spot => ({ position: { x, y: 0, z }, neighbors, enabled });

// door - hall - bedroom, with a kitchen off the hall and a shortcut from the door that is switched off
const home: Record<string, Spot> = {
  door: at(0, 0, ["hall", "closed"]),
  hall: at(2, 0, ["door", "kitchen", "bedroom"]),
  kitchen: at(2, 1, ["hall"]),
  bedroom: at(6, 0, ["hall", "closed"]),
  closed: at(3, 0, ["door", "bedroom"], false),
  porch: at(-9, 0, []),
};

describe("scanRoute", () => {
  it("walks the shortest way between two spots, around a spot that is switched off", () => {
    expect(scanRoute(home, "door", "bedroom")).toEqual(["door", "hall", "bedroom"]);
  });

  it("goes to the farthest spot that can be walked to when no end is given", () => {
    expect(scanRoute(home, "door")).toEqual(["door", "hall", "bedroom"]);
  });

  it("passes over a room scanned from one spot, such as a bathroom, for a bigger room nearer the door", () => {
    const room = (s: Spot, id: string): Spot => ({ ...s, roomInfo: { id } });
    const flat: Record<string, Spot> = {
      door: room(at(0, 0, ["bed1"]), "hall"),
      bed1: room(at(3, 0, ["door", "bed2"]), "bedroom"),
      bed2: room(at(5, 0, ["bed1", "bath"]), "bedroom"),
      bath: room(at(8, 0, ["bed2"]), "bathroom"),
    };
    expect(scanRoute(flat, "door")).toEqual(["door", "bed1", "bed2"]);
    expect(scanRoute(flat, "door", "bath")).toEqual(["door", "bed1", "bed2", "bath"]);
  });

  it("is empty when there is no way through", () => {
    expect(scanRoute(home, "door", "porch")).toEqual([]);
    expect(scanRoute(home, "nowhere", "door")).toEqual([]);
  });
});

describe("nearestSpot", () => {
  it("is the open spot closest to a point", () => {
    expect(nearestSpot(home, { x: 3.1, y: 0, z: 0 })).toBe("hall");
    expect(nearestSpot({}, { x: 0, y: 0, z: 0 })).toBeNull();
  });
});
