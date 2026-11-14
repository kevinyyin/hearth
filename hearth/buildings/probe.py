"""python -m hearth.buildings.probe <building_id> : what each data layer returns for one building."""
import sys

from hearth.buildings import tools


def probe(building_id: str) -> None:
    rec = tools.costar_record(building_id)
    print(f"costar: {'none' if rec is None else sorted(rec)}")
    if rec is None:
        return
    lat, lon = rec["lat"], rec["lon"]
    attrs = tools.vexcel_attributes(lat, lon)
    print(f"vexcel attributes: {'none' if attrs is None else sorted(attrs)}")
    print(f"vexcel image: {tools.vexcel_image(building_id, lat, lon)}")
    panos = tools.matterport_panoramas(building_id)
    print(f"matterport: {len(panos)} panoramas {[p['label'] for p in panos]}; embed={tools.matterport_embed_url(building_id) is not None}")


if __name__ == "__main__":
    for bid in sys.argv[1:]:
        print(f"== {bid}")
        probe(bid)
