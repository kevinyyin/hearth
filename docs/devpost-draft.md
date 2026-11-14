# Devpost draft (building-agent tracks)

Draft for the team to edit. Every number here was measured on Nov 13; patients are simulated.

## CoStar: Inside and Out

During a multi-day outage, the danger to someone on a home oxygen concentrator or feeding pump is set by their
building: how fast it heats up, whether a crew can get a delivery up eight floors with the elevator dead, and
whether there is anywhere step-free to move them. Hearth's building agent reads all three of the toolkit's layers
for one building and writes an outage profile in which every field names its source and confidence. CoStar gives
floors, units, year built, construction and elevators. Vexcel gives roof material, condition and tree cover, plus
a vision read of the ortho tile for roof tone and where a van can stop. Matterport scan panoramas give entrances,
steps, door and stair widths, and visible elevators. When the layers disagree (CoStar lists an elevator the scan
never shows), the agent says so and asks a follow-up. Code, not the model, turns the profile into a published
heuristic: hours until the home is unsafe at 35 °C, shown with and without each layer so judges can see what each
dataset changed, plus delivery minutes with the elevator out. Inside, the scan becomes a one-screen crew access
brief; outside, CoStar search finds hotels and senior housing beyond the dark area, and the same survey checks
whether a wheelchair user can actually get in. Of the kit's 1,758 Houston buildings, 1,732 have a Matterport
model; a live survey of a Houston hotel took 61 seconds end to end.

## LangChain: deepagents

The building agent is a `deepagents` deep agent on Claude. It writes a to-do plan, dispatches three layer
subagents (CoStar, aerial, interior) in parallel, saves each layer's findings to files that double as the cache,
reconciles conflicts with a follow-up question to the right subagent, and calls one validated `write_profile`
tool that rejects any field without a real source. A second deep agent, the refuge finder, searches, surveys
candidates (cache first), filters them with code-checked access rules, and stops at the library's human-approval
interrupt: a dispatcher approves or rejects. A rejection reason is written to the agent's memory file, and the
next proposal reads it: in our test the agent skipped the rejected hotel on the next run. The dispatcher's map
streams the agent's plan, subagent progress, files and conflicts live. Subagents run on Claude Haiku 5.5 at low
effort and the coordinator on Claude Sonnet 5.5, which cut a fixture survey from 61 to 38 seconds.
