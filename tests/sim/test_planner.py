from hearth.planner import Crew, Flags, Need, assign, travel_h


def need(pid, w=3.0, hours=10.0, supplier="s1", kind="delivery"):
    return Need(patient_id=pid, kind=kind, supplier_id=supplier, weight=w, hours_until_empty=hours, lat=29.76, lon=-95.37,
                service_h=0.2, since_h=0.0)


def crew(cid, org="s1"):
    return Crew(crew_id=cid, org_id=org, lat=29.80, lon=-95.40)


def stock(n):
    return {"s1": n, "s2": n, "s3": n}


def test_most_urgent_patient_is_served_first():
    jobs = assign([need("slow", w=3, hours=20), need("fast", w=3, hours=2)], [crew("c1")], stock(10), Flags(), 0)
    assert jobs[0].patient_id == "fast"


def test_no_cross_supplier_delivery_without_mutual_aid():
    assert assign([need("a", supplier="s1")], [crew("c2", org="s2")], stock(10), Flags(), 0) == []
    assert len(assign([need("a", supplier="s1")], [crew("c2", org="s2")], stock(10), Flags(mutual_aid=True), 0)) == 1


def test_out_of_stock_patient_is_not_dropped():
    needs, s = [need("a")], stock(0)
    assert assign(needs, [crew("c1")], s, Flags(), 0) == [] and [n.patient_id for n in needs] == ["a"] and s["s1"] == 0


def test_delivery_takes_stock_and_busies_the_crew():
    s, c = stock(1), crew("c1")
    jobs = assign([need("a"), need("b")], [c], s, Flags(), 0)
    assert len(jobs) == 1 and s["s1"] == 0 and c.free_at_h == jobs[0].data["done_h"] > 0


def test_travel_is_haversine_times_detour_over_speed():
    assert abs(travel_h((29.76, -95.37), (29.76 + 0.36, -95.37)) - 40.0 * 1.4 / 40) < 0.01  # 0.36 deg lat ~ 40 km


def test_assign_skips_crews_that_do_not_fit():
    near, far = crew("near"), Crew(crew_id="far", org_id="s1", lat=29.95, lon=-95.60)
    ride = lambda: [need("a", kind="ride")]
    assert assign(ride(), [near, far], {}, Flags(), 0)[0].data["crew_id"] == "near"
    near.free_at_h = 0.0
    assert assign(ride(), [near, far], {}, Flags(), 0, fits=lambda n, c: c.crew_id != "near")[0].data["crew_id"] == "far"
    assert assign(ride(), [crew("x")], {}, Flags(), 0, fits=lambda n, c: False) == []
