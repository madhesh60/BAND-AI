
## HACKATHON 2: Band of Agents (Lablab.ai)

### The Quick Summary

Build practical enterprise workflows where AI agents communicate, coordinate, exchange context, and complete work together. Prize pool: $9,500. Dates: June 12–19, 2026. [LabLab](https://lablab.ai/ai-hackathons/band-of-agents-hackathon)

---

### Your Big Question: "June 12th start date — but everything is already there. What does that mean?"

Great question. Here's exactly what's happening:

The **problem statement and rules are already public** — you can read them right now. This is totally normal for hackathons. They put everything out early so you can **plan and prepare** beforehand.

**June 12 is not when they reveal the problem. It's when the official build clock starts.**

Think of it like a school exam. The teacher might tell you the topic a week early. But the exam itself starts at 9am on exam day. You can study and plan before — but you cannot submit your answer sheet until exam day begins.

June 12: Kick-off Stream (a live intro call). June 12–19: Online Build Phase. June 19: Project Submissions End. [LabLab](https://lablab.ai/ai-hackathons/band-of-agents-hackathon)

So right now, before June 12, you can:

- Read all the details
- Plan your idea
- Learn how Band works
- Write some code to experiment

But your **official submission** only counts if you build it during June 12–19. You don't need to build anything "new" on June 12 — you just officially start your clock and ideally watch the kick-off stream for last-minute tips.

---

### What is "Band"?

Band's platform is designed to sit above existing frameworks and tools, enabling agents to communicate and collaborate regardless of how or where they are built. Whether agents are developed using frameworks like LangChain or CrewAI, Band gives them a shared layer for interaction — so agents can discover one another, exchange context, and delegate tasks dynamically. [Unite.AI](https://www.unite.ai/band-raises-17m-seed-round-to-build-the-coordination-layer-for-ai-agents/)

**In plain words:** Imagine you have 3 workers — one who researches, one who writes, one who reviews. Normally, you (the developer) have to manually pass files and notes between them. Band is like a **shared WhatsApp group** for your AI agents — they can all talk to each other, share updates, and hand off tasks without you doing it manually.

---

### What Exactly Do You Need to Build?

Your challenge is to build a multi-agent system where at least 3 agents collaborate through Band across planning, execution, review, decision-making, or task handoff. [LabLab](https://lablab.ai/ai-hackathons/band-of-agents-hackathon)

So the rules are clear: **minimum 3 agents, and they must talk to each other through Band.**

Agents should communicate, share structured context, delegate work, hand off tasks, or coordinate state as part of the core workflow. Band should be part of the actual collaboration layer, not only a thin wrapper, final notification system, or simple output channel. [LabLab](https://lablab.ai/ai-hackathons/band-of-agents-hackathon)

This means you **cannot** just slap Band on at the end as decoration. It must be the main communication highway between your agents.

---

### What Kind of System Should You Build?

Build enterprise-ready multi-agent systems for real business workflows — systems where agents do not just respond to prompts, but collaborate across planning, execution, review, and decision-making. [LabLab](https://lablab.ai/ai-hackathons/band-of-agents-hackathon)

Real examples you could build:

- **HR system**: Agent 1 screens resumes → hands to Agent 2 who schedules interviews → Agent 3 sends offer letters
- **Finance system**: Agent 1 tracks incoming invoices → Agent 2 checks if payment policy is followed → Agent 3 logs the audit record
- **Coding team**: Agent 1 writes code → Agent 2 reviews it → Agent 3 runs tests and reports results

The topic is open. As long as it's a **real business problem** and 3+ agents work together through Band, you're good.

**You already live in this world.** You're a developer. You already know what "write code → review it → test it → fix bugs" looks like. You don't need to research how HR approvals work or what a legal compliance process looks like. You already understand the problem from day 1.

**They even gave you a free starting point.** Track 2 mentions a thing called **CodeBand** — it's a ready-made example on GitHub showing how multi-agent coding workflows work. That's basically a free head start. The other two tracks have no such reference.

**The agents practically design themselves.** In Track 2, your 3 agents are obvious:

- Agent 1: Planner (reads the task, breaks it into steps)
- Agent 2: Coder (writes the actual code)
- Agent 3: Reviewer/Tester (checks the code, finds bugs)

Done. You don't need to think hard about what each agent does — it maps directly to how software is already built.

---
## Hackathon 2: Band of Agents (Lablab.ai)

### ✅ MUST DO (No choice, mandatory)

- Build **minimum 3 agents** — not 2, not 1, exactly 3 or more
- All agents must **communicate through Band** as the main connection layer — Band cannot be decoration, it must be the actual communication highway
- Your agents must show clear **task handoffs** — Agent 1 passes work to Agent 2, Agent 2 passes to Agent 3, etc.
- Agents must share **context with each other** — not just run separately
- Solve a **real business workflow problem** — toy demos will score low
- Submit before **June 19, 2026**
- Make code **open source with MIT license**
- Submit during the **June 12–19 build window** officially

---

### 🤔 YOUR CHOICE (Optional but smart)

- Which track you pick — Track 2 (coding agents) is easiest for developers
- Which LLM powers your agents — Claude recommended
- Whether you watch the **June 12 kick-off stream** — not mandatory but gives useful tips
- What specific business problem you solve — fully open within your track
- Whether you use **CodeBand** (the free reference code they provided) — saves you hours of setup time, highly recommended