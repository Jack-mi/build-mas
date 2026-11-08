# Architecture decisions

The executable ArchitectureSpec and service are authoritative; this reference supplies model decision criteria.

- Establish source_runtime by real entrypoints, imports, dependencies, state, tools and handoffs. Installing a package alone does not prove it is used.
- none → new Codex SDK project; codex_sdk → reuse and local edit; other → behavior capture and rebuild; unknown → inspect and ask only a blocking question.
- Start with one role/thread. Multiple roles require independently divisible work, distinct trust/permission contexts, or useful independent verification. Store the reason and baseline comparison.
- Host Python controls the flow, permissions, validation, state, integration, budgets and stopping. The model analyzes, generates code and diagnoses semantics.
- Skill is reusable procedural knowledge; deterministic repeated operations become scripts; tools provide narrow current data/actions. Do not generate Skills for one-off task prose.
- The target is a standalone package using public openai_codex exports. Default service forms are library, CLI and stdio MCP. HTTP, plugins and resident workers are optional deliverables when requested.
- Build/edit/migrate/refactor prepare exact file proposals in isolation. User authorization binds proposal hash, spec revision and workspace snapshot. Only apply writes the target.
- Preserve failure and incomplete coverage. Deterministic command receipts and artifacts establish runnable behavior; model verdicts are supplementary.
- Migration parity requires golden inputs/outputs plus errors, permissions, side effects and recovery criteria. Old runtime imports/entrypoints/unused dependencies must be retired only within approved scope. An unexecutable old system is a rebuild with limited evidence, not proven parity.

Architecture sources checked 2026-11-08: agents-best-practices 1.18.0 at da245f8cbfc4c358e8c3cde61dbb703bd40292bc; official Codex SDK source 748ab55ca7de0b647d9a7a9d9a8e70e00f28666d; published SDK/runtime 0.167.0.
