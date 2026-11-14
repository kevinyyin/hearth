"""Normalizers for real sponsor records. Inputs are hand-made in the sponsors' shapes, not sponsor data."""
from hearth.buildings.tools import normalize_costar, normalize_vexcel


def costar(**over):
    rec = {"id": 1, "propertyType": 11, "propertySubtype": 58, "numStoriesAboveGrade": 9, "buildingConstructionMaterial": 1,
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
