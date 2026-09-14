# ShopSense — Project Scope & Understanding

> **Project ID:** 14 (Project-1-DAT, "Building AI agent" track)
> **Mentor:** Animesh
> **Track:** 1-month → Weeks 1–5 (7 Sep – 9 Oct)
> **Mandate:** *Develop a multi-agent AI assistant for customer support, order management, refunds, and policy-based decision making.*
> **Expected outcome:** Implementation + Experiments — ticket triage, order/refund tools, customer memory, policy RAG, LangGraph orchestration, MCP integration, observability/reliability, end-to-end evaluation with **refund and prompt-injection guardrails**.

---

## 0. Reading the assignment sheet

Projects 11–15 are the same architectural skeleton applied to five domains:

| ID | Project | Domain | Guardrail focus |
|----|---------|--------|-----------------|
| 11 | CareFlow | Care coordination | Safety |
| 12 | LexOps | Contracts & compliance | Legal review |
| 13 | WealthPilot | SME loan underwriting | Bias/compliance + human approval |
| **14** | **ShopSense** | **Customer care & orders** | **Refund + prompt injection** |
| 15 | PlantGuard | Predictive maintenance | Safety + human approval |

Every row demands the same pipeline: structured intake → tool integration → persistent memory → production RAG → LangGraph orchestration → MCP → observability/reliability → end-to-end evaluation.

**Two consequences.**

1. The pipeline is table stakes. It will not differentiate the work — everyone builds it.
2. The differentiator is the guardrail clause. ShopSense is the only one of the five where the agent **moves real money** and where the **user is a plausible adversary**. A refund is an irreversible financial transfer initiated by a language model on the basis of a policy it retrieved from a document, while an untrusted party controls the input.

That is the thesis of this project. Everything else supports it.

The **Papers column is empty** for all five projects. The related-work survey is ours to source — it is a deliverable, not a handout.

---

## 1. What the system does

A customer writes in:

> *"My order arrived cracked, I want my money back."*

ShopSense must:

1. Classify the request and its urgency
2. Resolve which order they mean, and retrieve its real state
3. Retrieve the policy clause governing damaged goods in that product category
4. Decide: refund, replace, deny, or escalate — and for how much
5. Execute that decision against the payments system
6. Reply, citing the policy it applied

The chatbot is the easy part. The project is steps 3–5: **grounded, authorized, auditable action**.

---

## 2. Key challenges

| Challenge | Why the naive approach fails |
|---|---|
| **Policy grounding** | Asked "can they return this?", an LLM will invent a return window with total confidence. Every decision must trace to a retrieved clause. |
| **Irreversible side effects** | `issue_refund` spends money. A retry storm, a duplicated tool call, or one hallucinated argument is real loss. Needs idempotency keys and authorization tiers. |
| **Adversarial input** | *Direct* injection (typed into chat) and *indirect* injection (poisoned text inside an order note, product review, or email signature the agent reads as data). |
| **History-dependent decisions** | One refund is service. The fifth this month is fraud. Requires durable customer memory, not chat context. |
| **Non-determinism** | Same ticket, two runs, two different actions. Without evaluation you cannot tell whether a change helped. |
| **Stateful coordination** | Triage → context → policy → decision → execute → verify is a branching workflow with human handoffs, not a single prompt. |

---

## 3. Assumptions & scope boundaries

**In scope**
- Text tickets (chat/email style), English
- A synthetic but realistic commerce backend (orders, shipments, payments, returns)
- A hand-authored policy corpus of ~15–30 documents
- Offline evaluation on a golden dataset

**Out of scope**
- Voice, images, real payment processors, real PII
- Production deployment, multi-tenancy, i18n
- Live A/B testing with human customers

**Assumptions**
- The mock backend faithfully represents the *shape* of a commerce API (typed, failable, idempotent), which is what matters for agent design
- Synthetic tickets generated against a labeled schema are adequate for measuring relative performance across baselines

---

## 4. The eight components, decoded

### 4.1 Ticket triage
Classifier over incoming messages. Intent (`WISMO` / return / refund / cancel / damaged / address-change / product-question / complaint / fraud-suspicion), priority, sentiment, routing decision.
*Measured by macro-F1 against a labeled set. Earliest win in the project.*

### 4.2 Order / refund tools
Mock commerce backend — SQLite + FastAPI. Entities: orders, line items, shipments, payments, returns, refunds.

Tools: `get_order`, `search_orders`, `track_shipment`, `cancel_order`, `initiate_return`, `issue_refund`, `create_replacement`, `update_address`.

Every mutating tool requires: a typed schema (Pydantic), an **idempotency key**, and a permission tier. Tools must be able to *fail* — that is what makes the reliability work meaningful.

### 4.3 Customer memory
Two layers.
- **Short-term** — conversation state carried inside the graph
- **Long-term** — customer profile: prior tickets, refund history (90-day window), lifetime value, abuse flags

The long-term layer is what makes *"5th refund this month → escalate"* expressible.

### 4.4 Policy RAG
Corpus: return windows by category, refund eligibility, shipping SLAs, warranty terms, fraud rules, exception handling. Chunked, embedded, retrieved — with hybrid retrieval and reranking if recall demands it.

**Hard requirement: every policy-based decision cites the clause it used. An uncited decision is a failed decision.** This is the grounding metric, and it is enforceable in evaluation.

### 4.5 LangGraph orchestration
The state machine tying it together. Nodes per agent, conditional edges, **checkpointing** (a ticket survives a crash), and `interrupt` for human-in-the-loop when a refund exceeds threshold.

```
intake → triage → resolve_context → retrieve_policy → decide
                                                        │
                              ┌─────────────────────────┼──────────────────┐
                              ▼                         ▼                  ▼
                        auto_approve              human_review           deny
                              │                         │                  │
                              └──────────► execute ◄────┘                  │
                                              │                            │
                                           verify ──────► respond ◄────────┘
```

### 4.6 MCP integration
Expose the commerce backend as an **MCP server**; the agent consumes tools over the protocol rather than importing Python functions. Demonstrates interoperability instead of a monolith, and gives a clean boundary at which to enforce tool-call validation. Strong demo material.

### 4.7 Observability & reliability
Per-node tracing (latency, tokens, cost), structured logs, retries with backoff, timeouts, fallback models, a dead-letter path for failed tickets, and trace replay. Langfuse or LangSmith.

### 4.8 Guardrails & evaluation

**Refund guardrail** — a *deterministic* validator between the LLM's proposal and execution:
- amount ≤ order total, minus prior refunds
- within the policy window that was actually retrieved
- not already refunded (idempotency)
- under the auto-approve threshold, else route to human

> **The LLM proposes; code disposes.** No language model unilaterally decides that money moves.

**Prompt-injection guardrail** — delimiting/spotlighting of untrusted content, an injection detector on both user input and retrieved data, tool-call validation against retrieved policy, and a red-team suite run as a standing benchmark.

**End-to-end evaluation** — a golden set of ~100–200 tickets with expected actions, plus an adversarial split.

---

## 5. Metrics

| Metric | What it tells us |
|---|---|
| Triage macro-F1 | Classification quality |
| **Action accuracy** | Did it take the correct action? |
| **Policy citation correctness** | Right clause, not merely right answer |
| **False-refund rate** | Refunds issued that policy forbids — *headline safety number* |
| **Injection attack success rate (ASR)** | % of red-team prompts causing an unauthorized tool call |
| Escalation precision / recall | Hands off when it should — and only then |
| p50 / p95 latency, cost per ticket | The price of safety |

### Baselines

| | System |
|---|---|
| **B0** | Single LLM, all tools, no retrieval, no guardrails |
| **B1** | Single ReAct agent + policy RAG |
| **B2** | Full multi-agent graph + guardrails *(proposed)* |

Evaluated on an identical set. Expected narrative: **B0 is fast, cheap, and unsafe; B2 costs more and drives false-refund rate and injection ASR toward zero.** That trade-off curve is the experimental result — not a demo video.

Ablations worth running: guardrail off, RAG off, memory off, single-agent vs. multi-agent.

---

## 6. Related work to survey

**Commercial landscape** — Intercom Fin, Sierra, Decagon, Zendesk AI, Salesforce Agentforce, Forethought, Gorgias. All closed. *That opacity is itself part of the gap argument.*

**Academic / technical**, in reading order:

1. **τ-bench (tau-bench)** — Sierra's benchmark for retail customer-service agents with explicit **policy adherence**. Closest existing framing to this project. Read first.
2. **AgentDojo** — prompt injection against tool-using agents; a methodology to borrow for the red-team suite.
3. **Greshake et al., indirect prompt injection** — the foundational attack paper.
4. **ReAct**, **Reflexion** — agent reasoning loops.
5. **Self-RAG / CRAG** — retrieval with self-correction.
6. **BFCL**, **ToolBench** — tool-calling evaluation.
7. **OWASP LLM Top 10** — framing for the guardrail section.
8. **MCP specification**, **LangGraph documentation** — the stack itself.

### The gap
Existing work measures **capability** (τ-bench) *or* **safety** (AgentDojo), separately. Commercial systems measure both but publish nothing. There is no open, end-to-end customer-care agent that combines policy-grounded decisions, deterministic financial guardrails, injection resistance, and production observability — **evaluated together, with the safety/cost trade-off quantified.**

That is the contribution.

---

## 7. Five-week plan

| Week | Dates | Deliverable |
|---|---|---|
| **1** | Sep 7–11 | Background, problem statement, landscape, related work, justification. **Plus:** repo skeleton, mock order schema, policy corpus drafted. |
| **2** | Sep 14–18 | Architecture & design document — graph topology, agent roles, tool contracts, guardrail placement, memory schema, evaluation plan. |
| **3** | Sep 21–25 | Prototype end-to-end. Working demo + evaluation numbers + baseline comparison. |
| **4** | Sep 28–Oct 3 | Hardening — MCP, observability, red-team suite, ablations. |
| **5** | Oct 5–9 | Mentor presentation and demonstration. |

**Week 1 is graded on documentation, but start the mock data and policy corpus now.** They are unglamorous, take longer than anyone expects, and block everything in Week 3.

---

## 8. Immediate next actions

- [ ] Make `shopsense` a standalone git repository *(it currently sits inside the `Global` repo alongside unrelated work)*
- [ ] Repo skeleton + dependency management
- [ ] Design the commerce schema (orders → shipments → payments → returns → refunds)
- [ ] Draft 15–30 policy documents — deliberately including **conflicting and edge-case clauses**, since those are what expose ungrounded reasoning
- [ ] Define the ticket taxonomy and label schema
- [ ] Read τ-bench and AgentDojo; begin the related-work table

---

*Working document — supersedes nothing, subject to revision through Week 2.*
