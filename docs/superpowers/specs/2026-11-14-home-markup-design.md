# Home markup: the resident marks up their home, the responder sees it

Short design · slice 1 of 3 (accounts, resident side, responder side) · November 14, 2026

## Why

Hearth today has one view, for a dispatcher. Records and scans cannot say where the machine is inside a home,
which door to use, or what is in the way. The resident can. This slice lets the resident say it once, ahead of
time, and puts it in front of the responder at the door. It is also the CoStar "Inside and Out" story told from
the two people who would use it.

## Goals

- A resident persona sets up their device and marks up their home, outside and inside.
- A responder persona opens one job and sees that markup on the same aerial image and 3D scan, above the
  existing crew brief.
- It demos on its own: no dispatch, no model call.

## Not in this slice

- The help loop (ask for help, "I'm safe", Claude assigning responders, the tracker, next job) is slice 2.
- Contacts and live-in helpers are slice 3.
- Responder setup (base, vehicle, equipment) is slice 2, where the model needs it.
- Real logins. Any address outside the CoStar extract. Messaging anyone.

## Must not happen

- No real person's data. Every resident is a synthetic patient and every screen keeps the "Simulated patients"
  badge.
- The scan is never presented as the resident's own rooms unless the resident said their home is laid out like it.

## Approaches

| | What | Verdict |
|---|---|---|
| Accounts | Demo personas: pick a role, then a synthetic patient or a crew name; kept in the browser; the shared password still guards the hosted site | Picked by the user |
| | Real logins through Supabase | Rejected: real health data, half a day, a login form is all a judge sees |
| Inside pins | Pins in the live 3D scan through the Matterport embed SDK; positions saved in our store | Picked. Tested Nov 14 on a real apartment scan: a pin dropped at the pointer, and showed again after a reload, including on the scan's floor-plan inset |
| | Pins on flat room photos from the scan | Fallback only if the SDK key is refused on the hosted domain |
| Outside pins | Taps on the Vexcel aerial image, saved as a fraction of its width and height | Only sensible way |

## What gets built

**Start page (`/start`).** Three links: Resident, Responder, Dispatcher (the current map). The resident then picks
one of the demo patients; the responder types a crew name. The choice lives in the browser's local storage.

**Resident page (`/resident`)**, one phone-width column:

1. Your device: device type (from the patient record), "without it I'm OK for N hours", backup plan (free text),
   and size: one of shoebox, microwave, carry-on suitcase, mini fridge, or typed width, depth and height.
2. Your building: an address search over the CoStar properties. It starts on the patient's own building.
3. Outside: the aerial image. Pick a pin kind, tap to place: park here, entrance, blocked, route (numbered taps
   joined by a line). Tap a pin to remove it.
4. Inside: "Which of these is laid out like your home?" shows the building's scans (most apartment buildings
   have two or more) and "none of these". On a chosen scan: machine, blocked, route from the door. To place a
   pin, hold the pointer still on the spot and press the "Drop pin here" button that appears. With "none of
   these" there are no inside pins, only a typed note.
5. Save.

**Responder page (`/responder`).** A list of residents who have saved a home markup; opening one is the job card:
device, size, hours OK without it, backup plan, note; the aerial image with the outside pins; the chosen scan
with the inside pins, opened facing the machine pin; then the existing crew access brief.

**Data.** One new document kind, `home`, keyed by patient id, in the existing store: building id, the device
answers, the chosen scan id or none, the note, outside pins (kind, x, y, order) and inside pins (kind, 3D
position, surface normal, order). The patient record itself is not changed.

**API.** `GET` and `PUT /api/patients/{id}/home`, and `GET /api/homes` for the responder's list. The PUT checks
pin kinds, that outside pins fall inside the image, that the scan id belongs to the building, and caps the pin
count. Building detail also returns the list of scan ids. The embed SDK key reaches the page through the API,
which is already behind the password.

## Known limits

- Dropping an inside pin needs a mouse pointer. It has not been tried on a touch screen; the demo runs on a
  laptop showing a phone-width column.
- The SDK key was tested on localhost only. Matterport keys can be limited to named domains, so the hosted site
  needs its own check before it is shown.
- A scan can take 10 to 20 seconds to open.

## Left to the builder

- Component split, styling within the existing design tokens, the exact pin colors and icons.
- Whether the scan viewer is one component with an edit flag or two.
- Tests: one API round trip with the validation cases; one web test for the tap-to-fraction arithmetic.
