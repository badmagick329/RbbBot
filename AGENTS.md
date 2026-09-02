## Coding

- Do not consider backward compatibility. Ignore legacy code/libraries
- Do not introduce guarding, excessive testing, except where input cannot be trusted. For example, user input or another software's input

## Architecture

- Follow Clean Architecture. Dependencies point inward; inner layers must not depend on outer layers.
- `Domain`: entities, value objects, domain rules. `Application`: use cases. `Infrastructure`: persistence and external systems. `Presentation`: transport/API entry points. `Views`: UI components, pages, and presentation-specific rendering.
- Organize application code as vertical slices by feature/use case, not by technical type.
- Each slice owns its request/command/query, handler/use case, validation, DTOs, and mapping where needed.
- Avoid generic `Services`, `Helpers`, or other dumping-ground abstractions. Extract shared code only when genuinely reused.

## Documentation

- Document non-trivial classes/functions by explaining **why they exist**, not what they do.
- Capture intent, design rationale, constraints, and invariants; do not narrate implementation or obvious inputs/outputs.

## Git

- Use Conventional Commits with an appropriate type and optional scope.
- Keep commit messages focused on the intent of the change.

## Response Discipline

Keep answers tightly scoped to the user's actual question.

- Do not add extra framing, justification, or side commentary unless it directly answers the request.
- Do not introduce cautions, alternatives, or edge-case advice unless the user asked for them or they are necessary to avoid a meaningful mistake.
- Prefer short prose over bullets when the question is simple.
- Do not pad responses with reasons why something is good, bad, or sensible unless the user explicitly asks for evaluation.
- Optimize for directness: answer first, stop when the user's question has been satisfied.
- Sacrifice grammar for concision.
- No motivational fluff.
