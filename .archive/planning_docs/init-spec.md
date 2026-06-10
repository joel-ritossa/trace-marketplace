# Trace Marketplace

## Goal

Millions of people use AI agents (such as Claude Code) to assist them in real work. Their agents are already logging rich trace data during their sessions, but this data is going to waste — there is no market for it yet.

**Trace Marketplace** provides a frictionless way for users to sell this information.

Labs and businesses (e.g. Fleet) want visibility into what's happening and would pay for data that assists in model training and understanding:

- **Rare data / rare experiences**
- **Failure modes** — where is the AI screwing up?

### Architecture

We are intentionally not prescribing the architecture. You should make the core decisions yourself:

- How will users upload their data?
- How will we search the data?
- How are traces stored and analyzed?
- How will we support marketplace dynamics?

We care about whether you have strong, defensible opinions about how to build and design a large system from core principles. Coding agents are heavily encouraged as part of the workflow, but the key design decisions should still be clearly yours and legible in the final system.

## Scope

The scope of this project is very large. We are much more interested in getting a **solid foundation for data processing** than in rich marketplace functionality. Marketplace features on top would be nice to have.

## Deliverables

- A running website to view traces
- A contributor must be able to onboard to the website and upload trace data
- A consumer must be able to discover and download allowed trace data
- The full runnable system in a single repo, documenting any third-party or cloud services used
