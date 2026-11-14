"""Normalizers for real sponsor records. Inputs are hand-made in the sponsors' shapes, not sponsor data."""
from hearth.buildings.tools import normalize_costar, normalize_vexcel


def costar(**over):
    rec = {"id": 1, "buildingName": "Main Tower", "propertyType": 11, "propertySubtype": 58, "numStoriesAboveGrade": 9, "buildingConstructionMaterial": 1,
           "constructionStatus": 1,
           "primaryAddress": {"streetNumber": "100", "streetName": "Main", "streetType": "St", "city": "Houston", "state": "TX",
                              "postcode": "770021234", "latitude": 29.7, "longitude": -95.3},
           "constructionEvents": [{"eventType": 4, "year": 2004}, {"eventType": 2, "year": 1965}],
           "propertyApartment": {"totalNumUnits": 592, "apartmentLifestyleType": 1,
                                 "elevators": [{"elevatorType": 1, "numElevators": 5, "elevatorState": 1}, {"elevatorType": 2, "elevatorState": 2}],
                                 "models": [{"attachments": [{"videoExternalReferenceType": 234, "videoKey": "unitTour"}]}]},
           "attachments": [{"videoExternalReferenceType": 36, "videoKey": "lobbyTour"}, {"videoExternalReferenceType": 1, "videoKey": "x"}]}
    return rec | over


def test_costar_multifamily_fields():
    r = normalize_costar(costar())
    assert (r["building_id"], r["floors"], r["units"], r["year_built"], r["construction"]) == ("1", 9, 592, 1965, "masonry")
    assert r["property_type"] == "multifamily" and r["elevator_count"] == 5 and r["existing"]
    assert r["matterport_model_ids"] == ["lobbyTour", "unitTour"]
    assert r["address"] == "100 Main St, Houston, TX 77002" and (r["lat"], r["lon"]) == (29.7, -95.3)
    assert r["name"] == "Main Tower" and r["zip"] == "77002"


def test_costar_senior_flag_and_walkup():
    apt = {"totalNumUnits": 40, "apartmentLifestyleType": 2, "isWalkup": True, "elevators": []}
    r = normalize_costar(costar(propertyApartment=apt, buildingConstructionMaterial=0))
    assert r["property_type"] == "senior_housing" and r["elevator_count"] == 0 and r["construction"] is None


def test_costar_elevator_yes_without_count_is_at_least_one():
    apt = {"elevators": [{"elevatorType": 1, "elevatorState": 1}]}
    r = normalize_costar(costar(propertyApartment=apt))
    assert r["elevator_count"] == 1 and "at least" in r["elevator_note"]


def test_costar_hotel_has_rooms_and_unknown_elevators():
    r = normalize_costar(costar(propertyType=1, propertySubtype=32, propertyApartment=None, propertyHospitality={"numUnits": 210}))
    assert r["property_type"] == "hotel" and r["units"] == 210 and r["elevator_count"] is None


def test_vexcel_picks_latest_capture():
    feat = lambda date, tree, mat: {"properties": {"metadata.ortho-date-estimate": date, "metadata.collection": "c" + date[:4],
                                                    "parcel-tree-cover.percent": 19.0, "request-information.inside-parcel": True,
                                                    "structures": [{"primary-structure": True, "roof-characteristics.material.class": mat,
                                                                    "roof-characteristics.tree-cover.percent": tree,
                                                                    "roof-characteristics.condition": 3.0, "roof-characteristics.shape.value": "flat"}]}}
    v = normalize_vexcel({"features": [feat("2023-01-19T00:00:00", 0.0, "shingle"), feat("2025-09-03T00:00:00", 2.0, "membrane")]})
    assert v["roof_material"] == "membrane" and v["tree_cover_fraction"] == 0.02 and v["capture_date"].startswith("2025")
    assert v["parcel_tree_cover_fraction"] == 0.19 and normalize_vexcel({"features": []}) is None


def test_matterport_locations_become_panoramas_with_horizontal_faces():
    from hearth.buildings.tools import normalize_matterport
    sky = lambda: {"children": [f"https://cdn/x_skybox{i}.jpg?t=1" for i in range(6)]}
    model = {"name": "Lobby", "locations": [
        {"id": "loc2", "label": "2", "floor": {"label": "Floor 1"}, "room": {"label": "", "tags": ["hallway"]}, "panos": [{"skybox": sky()}]},
        {"id": "loc0", "label": "0", "floor": {"label": "Floor 1"}, "room": {"label": "Entry", "tags": []}, "panos": [{"skybox": sky()}]},
        {"id": "loc9", "label": "9", "floor": None, "room": None, "panos": []},
    ]}
    panos = normalize_matterport("M1", model)
    assert [p["pano_id"] for p in panos] == ["M1-loc0", "M1-loc2"]          # sweep order, no-image location dropped
    assert panos[0]["label"] == "Lobby: Entry, Floor 1, sweep 0" and "hallway" in panos[1]["label"]
    assert [f.split("?")[0][-5] for f in panos[0]["faces"]] == ["1", "2", "3", "4"]   # faces 0 and 5 are ceiling and floor


def test_detections_become_labels_with_a_side_of_the_building():
    from hearth.buildings.tools import summarize_detections
    box = lambda lon, lat, d=0.00005: f"POLYGON (({lon-d} {lat-d}, {lon+d} {lat-d}, {lon+d} {lat+d}, {lon-d} {lat+d}, {lon-d} {lat-d}))"
    j = {"features": [
        {"properties": {"label": "driveway", "detections": [{"confidence": 0.68, "bbox": box(-95.0, 29.7004)}]}},   # ~45 m north
        {"properties": {"label": "driveway", "detections": [{"confidence": 0.44, "bbox": box(-94.9996, 29.7)}]}},  # ~39 m east
        {"properties": {"label": "parking space", "detections": [{"confidence": 0.5, "bbox": box(-95.0, 29.6997)}]}},
    ]}
    rows = summarize_detections(j, 29.7, -95.0)
    assert rows[0] == {"label": "driveway", "confidence": 0.68, "side": "north", "distance_m": 45}
    assert [r["side"] for r in rows] == ["north", "south", "east"] or [r["side"] for r in rows] == ["north", "east", "south"]
    assert summarize_detections({"features": []}, 29.7, -95.0) == []


def test_rooms_keep_unit_type_and_sizes_and_drop_blank_rooms():
    from hearth.buildings.tools import normalize_rooms
    model = {"name": "2BR, 2BA - 1,000SF", "rooms": [
        {"label": "", "tags": ["hallway"], "dimensions": {"areaFloor": 4.4, "width": 1.1, "depth": 4.0}},
        {"label": "Bedroom 1", "tags": [], "dimensions": {"areaFloor": 10.2, "width": 3.4, "depth": 3.0}},
        {"label": "", "tags": []},
    ]}
    u = normalize_rooms(model)
    assert u["unit_type"] == "2BR, 2BA - 1,000SF"
    assert u["rooms"] == [{"room": "hallway", "width_m": 1.1, "length_m": 4.0, "area_m2": 4.4},
                          {"room": "Bedroom 1", "width_m": 3.0, "length_m": 3.4, "area_m2": 10.2}]
