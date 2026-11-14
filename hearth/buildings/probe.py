"""python -m hearth.buildings.probe [building_id ...] : what each data layer returns; no ids = Houston scan coverage."""
import sys
from collections import Counter

from hearth.buildings import tools


def _show(name, fn):
    try:
        v = fn()
        print(f"  {name}: {sorted(v) if isinstance(v, dict) else v}")
        return v
    except Exception as e:  # a probe reports every layer, even when one fails
        print(f"  {name}: ERROR {type(e).__name__}: {e}")


def probe(building_id: str) -> None:
    rec = _show("costar", lambda: tools.costar_record(building_id))
    if not rec:
        return
    lat, lon = rec["lat"], rec["lon"]
    _show("vexcel attributes", lambda: tools.vexcel_attributes(lat, lon))
    _show("vexcel image", lambda: tools.vexcel_image(building_id, lat, lon))
    _show("matterport panoramas", lambda: len(tools.matterport_panoramas(building_id)))
    _show("matterport embed", lambda: tools.matterport_embed_url(building_id))


def coverage() -> None:
    rows = tools._costar_index().values()
    print("Houston buildings by type (with a Matterport model id / total):")
    total, scanned = Counter(r["property_type"] for r in rows), Counter(r["property_type"] for r in rows if r["matterport_model_ids"])
    for t, n in total.most_common():
        print(f"  {t}: {scanned[t]} / {n}")


if __name__ == "__main__":
    for bid in sys.argv[1:]:
        print(f"== {bid}")
        probe(bid)
    if len(sys.argv) == 1:
        coverage()
