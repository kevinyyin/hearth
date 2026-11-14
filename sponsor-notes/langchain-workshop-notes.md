# LangChain workshop notes

HackPrinceton Fall 2026 · Attendee notes for the Hearth team

## What the sponsor wants to see

- **A complex, realistic use case.** Show how the agent handles a real workflow with multiple steps, tools, and decisions.
- **Human review at consequential steps.** The workshop emphasized human-in-the-loop middleware for difficult or sensitive cases. Show when the workflow pauses, what the reviewer sees, and what happens after approval or rejection.
- **Why you chose each component.** Explain what planning, subagents, filesystem access, or middleware each contributes to your specific workflow.
- **Visible use of the filesystem.** The presenter returned to this repeatedly. Show what the agent writes, what it reads back, and how that helps it manage context across steps.

An uncertainty score came up as a possible way to decide when to ask for review. Our workshop takeaway was to calculate the score in code using explicit inputs and thresholds. Claude could help compare candidate formulas against example cases during development.

## How Hearth can show this

- **Plan and delegate.** Show the surveyor planning a building assessment and assigning CoStar records, Vexcel imagery, and Matterport scans to separate subagents. Explain why each source gets its own task and how the surveyor reconciles disagreements.
- **Write findings to files.** Show a subagent's saved findings and where the surveyor reads them back. Explain how saving the findings supports a long-running workflow and lets subsequent surveys reuse cached evidence.
- **Show a real review decision.** Pause on a refuge proposal. Give the dispatcher the supporting evidence and any missing or conflicting information. Show what happens when they reject it and how the reason informs the next proposal.
- **Consider a deterministic review trigger.** For example, missing or conflicting evidence about step-free access could trigger review. If we add a score, show the inputs and threshold that led to the decision.
- **Use middleware where it serves a purpose.** The workshop covered conditional checks before tool calls and redacting sensitive information. If we show redaction, explain which fields are removed and why the tool does not need them.

## Technical notes

- LangChain covers building, testing, and deploying agents. The workshop focused on building them for the hackathon.
- **Agent = model + harness.** Deep Agents is the harness. You supply the model, including a vision-language model where appropriate. The harness supplies planning, filesystem tools, and subagents.
- Define custom Python tools with a tool decorator when the agent needs a web lookup or a project-specific operation. Skills can give the agent reusable instructions for specialized tasks.
- Deep Agents supports both temporary and persistent memory. Store durable state or preferences in a backend such as SQLite when they need to survive across sessions or be shared across workflows.
- The presenter compared the LangGraph server to a Flask app. It exposes endpoints for running agent workflows and streaming their progress. The workshop materials have example snippets.

## Resources and contact

- **Discord:** The LangChain channel has the workshop Jupyter notebook. Eugene is the sponsor contact for questions via Discord DM.
- **Setup ideas from the workshop:** Connect the LangChain docs MCP server and install the LangChain skills if useful for development.
