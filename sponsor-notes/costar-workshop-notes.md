# CoStar Group workshop notes

HackPrinceton Fall 2026 · Attendee notes for the Hearth team

## What the sponsor wants to see

- **Use at least two of the three sponsor data layers.** CoStar provides property data, Vexcel provides aerial imagery, and Matterport provides 3D scans. The use case can be outside real estate.
- **Combine sources to uncover something a single source could miss.** The strongest demo shows what the combination lets someone know or do.
- **Put AI at the center of the workflow.** Show how the intended user works with it. The presenters discouraged standalone chat boxes and AI added as a side feature.
- **Use modalities that serve the task.** Voice, cameras, and phones can capture context. Pictures and graphs can communicate findings. Design for people to change direction as they interact.
- **Build the demo first and have a backup.** Plan for unreliable venue Wi-Fi.

For questions, ask in the event Discord or visit the CoStar sponsor table. The workshop also mentioned an overall prize of a Mac Studio with 128 GB RAM and a Studio Display. Confirm which award that refers to before repeating it.

## How Hearth could apply this

Hearth could show how a dispatcher's decision changes when an agent combines property records, aerial observations, and interior scans. For example, CoStar can describe building age, construction, and elevator access. Vexcel can show shade, roof characteristics, and where a crew could stop. Matterport can show features of a scanned unit type that matter for getting equipment inside. The demo can make the combined insight visible in the triage view or crew brief.

The conversation left us unsure about the fit of disaster triage. Ask the sponsor team which data combinations would make the strongest EMS or emergency-dispatch demo, and whether post-disaster imagery is available for any relevant area. Treat predictions about disaster impacts and building conditions as project ideas to test.

## Vexcel · aerial imagery

- Vexcel described building its own camera sensors, operating an aircraft fleet, and producing aerial datasets. The workshop mentioned multispectral imagery, elevation, and repeat imagery at roughly six-month or annual intervals. Hackathon coverage includes Houston and Los Angeles.
- **Orthographic imagery** is a corrected top-down view. **Oblique imagery** shows buildings from an angle.
- The workshop described REST queries with geometry in Well-Known Text (WKT) and JSON responses that can include building footprint polygons. The Discord bot reportedly has a Python example.
- The presenters highlighted vector embeddings for semantic search and said vectors can be returned through the API. Check the toolkit for available endpoints, fields, and coverage.
- Vexcel sometimes flies after disasters to document affected areas. The workshop also mentioned unsupervised training, monocular depth, and Google Maps and Tesla as examples. Confirm those details with the sponsor before using them in the pitch.

## Matterport · 3D building scans

- The workshop cited **14,944 models** across Los Angeles and Houston, including 13,104 commercial and 1,930 residential models. Check the toolkit for the subset that matches CoStar records.
- Captures include panoramic views. Scan data can support workflows involving colored XYZ point clouds, meshes, and materials. Some models can also show exterior areas.
- Room boundaries were mentioned as an available input. The workshop floated furniture removal as a research example. Check which geometry and export features the hackathon toolkit exposes.
- The workshop's problem examples were in a photo taken at the session. Add those examples when the photo is available.

## CoStar · property data

- CoStar Group includes Homes.com and Apartments.com. The data platform discussion covered bringing property data together and working with it in relational databases and SQL.
- The workshop described a ZIP data extract with eight datasets covering topics such as listings, transactions, and property buyers. Check the extract for its schema and join keys before planning cross-source analysis.
