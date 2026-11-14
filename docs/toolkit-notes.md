# Sponsor toolkit notes

Field names and coverage only. No sponsor records are copied here; raw data stays in git-ignored
`data/raw/` and `data/buildings/<id>/`.

## CoStar (data extract, not an API)

- Source: `data/raw/costar/costar-hackathon-kit/data/commercial-property.jsonl` (3,339 records; Houston research
  market `primaryAddress.researchMarketId == 14`: 1,758). Null fields are omitted from records, so every read uses `.get`.
- Our reader: `hearth/buildings/tools.py` `normalize_costar`; the Houston subset is normalized once into
  `data/buildings/_costar/houston.json` (git-ignored).
- Field map:
  - id: `id` (PropertyId). Lat/lon: `primaryAddress.latitude/longitude` (all records).
  - floors: `numStoriesAboveGrade` (not `floors[]`, which does not match the story count).
  - units: `propertyApartment.totalNumUnits`; hotels `propertyHospitality.numUnits` (rooms).
  - year built: `constructionEvents[]` with `eventType == 2`, `.year`.
  - construction: `buildingConstructionMaterial` (1 masonry, 2 metal, 3 reinforced concrete, 4 steel, 5 wood frame,
    6 brownstone, 7 limestone, 0 unknown).
  - property type: `propertyType` (1 hospitality, 11 multifamily, 13 healthcare); senior housing is mostly multifamily
    with `propertyApartment.apartmentLifestyleType == 2`, or healthcare subtypes 26, 27, 28, 31, 142.
  - elevators: `propertyApartment.elevators[]` or `property{Office,Retail,Industrial,Flex}.structural.elevators[]`;
    passenger = `elevatorType 1`, `elevatorState` 1 yes / 2 no, `numElevators` sometimes. `propertyApartment.isWalkup`
    is a proxy for none. Hospitality has no elevator block.
  - Matterport model ids: any `attachments[]` entry (also under `propertyApartment.models[]` and `.units[]`) with
    `videoExternalReferenceType` 36 or 234; `videoKey` is the model id.
- Houston coverage (Nov 13 probe): multifamily 1,314 (elevator known for 1,179), office 191, industrial 98,
  hotel 54 (elevator known for 0), retail 41, senior housing 35 (elevator known for 29), flex 21.
  Buildings with at least one Matterport model id: 1,732 of 1,758. The kit covers only properties on CoStar's
  Matterport list; it is not a census of Houston.
- No per-field confidence in the data. Enum 0 and missing keys mean unknown, not "no".

## Vexcel (REST API)

- Base `https://api.vexcelgroup.com/v2`, header `X-API-KEY`. Back off on 429 (1, 2, 4 s).
- Attributes: `GET /property/extract?wkt=POINT(lon lat)&srid=4326&layer=urban,urban-r,wide-area,urban-g&latest=true&include=precomputed&unit-system=metric`.
  Returns a FeatureCollection with one feature per capture (several years); we take the latest
  `metadata.ortho-date-estimate` inside the parcel. Flat dotted keys: `parcel-tree-cover.percent`, `structure.count`,
  `metadata.collection`; per structure in `structures[]`: `primary-structure`, `building-type.class`,
  `roof-characteristics.material.class`, `.condition` (1-5), `.shape.value`, `.tree-cover.percent`, `footprint.area`,
  `roof-objects.solar-panel-photovoltaic.count`. Stories and roof height came back null on the probed buildings.
- No roof tone or color field: roof tone comes from a vision read of the ortho tile.
- Image: `POST /ortho/extract` with `{wkt, srid, layer, buffer-meter: 40, crop: bounding_box, image-format: png,
  destination-dimensions: "800,800"}` returns PNG bytes (about 1 MB). Cached at `data/buildings/<id>/vexcel.png`.
- Houston collections seen: 2023 to 2026 captures (`us-tx-houston-*`). Both calls took under half a second.

## Matterport

- Model ids come from CoStar (above). API access and panorama reads: pending the developer docs.
