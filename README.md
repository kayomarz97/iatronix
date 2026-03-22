# Iatronix — AI-Powered Medical Reference

Iatronix is a medical information website that uses artificial intelligence to answer questions about drugs, diseases, and treatment comparisons. It provides structured, evidence-based answers with citations from trusted medical sources like the FDA, WHO, and major clinical guidelines.

**Live at:** https://med.debkay.com

---

## What Does Iatronix Do?

Imagine you want to quickly look up how a medication works, what a disease involves, or how two treatments compare. Instead of reading through dozens of medical textbooks or websites, you type your question into Iatronix and get a well-organized answer — complete with references to real medical guidelines.

### Types of Questions You Can Ask

1. **Drug Queries** — Ask about any medication (e.g., "metformin dosing and interactions")
   - How it works in the body
   - What it's used for
   - Dosing instructions
   - Side effects and warnings
   - Drug interactions
   - Special considerations (pregnancy, kidney disease, etc.)

2. **Disease Queries** — Ask about any medical condition (e.g., "heart failure management guidelines")
   - What causes it
   - How common it is
   - Symptoms and diagnosis
   - Treatment options (first-line, second-line, non-drug options)
   - Complications and prognosis

3. **Comparisons** — Compare two treatments (e.g., "lisinopril vs losartan for hypertension")
   - Side-by-side comparison across multiple dimensions
   - Efficacy, safety, cost, convenience
   - Which one guidelines recommend and why

4. **General Medical Questions** — Anything else medical that doesn't fit the above categories

### Evidence Grading

Every fact in a response is tagged with:
- **Level of Evidence** — How strong the research behind it is (Level I = strongest, like large clinical trials; Level III = weakest, like expert opinion)
- **Class of Recommendation** — How strongly guidelines recommend it (Class I = "definitely do this"; Class III = "don't do this")
- **Source** — Which guideline or database it comes from (e.g., AHA, FDA, WHO)
- **Confidence** — How confident the system is in the answer (high, moderate, or low)

You see this information by hovering over the small colored dot next to each fact. Low-confidence claims are highlighted in amber so you can spot them easily.

### Safety Features

The system automatically flags:
- Life-threatening situations (overdose, anaphylaxis, etc.)
- High-risk medications that need careful dosing (blood thinners, chemotherapy, etc.)
- Dangerous drug combinations

Every response includes a disclaimer reminding users that this is a reference tool, not a substitute for professional medical judgment.

---

## How It Works (Behind the Scenes)

When you type a question and hit search, here's what happens step by step:

```
You type a question
        ↓
Your browser sends it to the website
        ↓
The website forwards it to the backend server
        ↓
The server checks: "Have I answered this exact question before?"
   YES → Send the saved answer instantly
   NO  → Continue below
        ↓
The server figures out what kind of question it is (drug? disease? comparison?)
        ↓
It builds a carefully crafted prompt with medical rules and sends it to an AI model (Claude)
        ↓
The AI responds with a structured answer including citations
        ↓
The server checks the answer:
   • Are the citations from approved sources?
   • Are there any safety concerns?
   • Is the data structured correctly?
        ↓
The server saves the answer for future use (so the same question is instant next time)
        ↓
The answer is sent back to your browser and displayed with nice formatting
```

The whole process typically takes 15–30 seconds for a new question, or less than 1 second if the answer was previously cached.

---

## The Building Blocks

Iatronix is made up of several pieces of software that work together, like departments in a hospital. Here's what each one does:

### 1. The Website You See (Frontend)

**What it is:** The visual interface you interact with — the search bar, the results, the buttons.

**Built with:**
- **Next.js** — A framework for building modern websites. It makes the site fast and responsive.
- **React** — The library that makes the interface interactive (typing, clicking, results appearing without page reloads).
- **Tailwind CSS** — A styling system that makes everything look clean and professional with a dark/light medical theme.
- **TypeScript** — A programming language that helps prevent bugs by catching errors before the code runs.

**What it does:**
- Shows the search bar and example query cards
- Sends your question to the backend server
- Displays results with proper medical formatting (headings, sections, evidence badges)
- Works on phones, tablets, and desktops
- Remembers which AI model you prefer (stored in your browser)

### 2. The Brain (Backend Server)

**What it is:** The server that processes your questions, talks to the AI, and validates everything.

**Built with:**
- **FastAPI** — A high-performance web framework for Python. It handles incoming requests very efficiently.
- **Python** — The programming language the backend is written in.
- **LangChain** — A toolkit that makes it easier to work with AI models.

**What it does:**
- Receives questions from the website
- Classifies what type of question it is
- Builds specialized medical prompts for the AI
- Calls the AI model and processes the response
- Validates citations against approved medical sources
- Checks for safety concerns
- Caches answers so repeat questions are instant
- Logs all queries for monitoring

### 3. The AI Models

**What they are:** Large language models (like ChatGPT or Claude) that generate the medical answers.

**Services used:**
- **Anthropic Claude** — The primary AI model. Made by Anthropic, it's one of the most capable AI models available.
- **OpenRouter** — A backup service that provides access to multiple AI models. If Claude goes down, the system automatically switches to OpenRouter.

**How they're used:**
- The backend sends a carefully structured prompt that includes medical rules, approved citation sources, and the user's question
- The AI returns a structured answer in JSON format with evidence grading on every claim
- The system never just blindly trusts the AI — it validates every response

### 4. The Database

**What it is:** Where permanent data is stored — user accounts, API keys, and query logs.

**Built with:**
- **PostgreSQL** — A powerful, reliable database used by companies like Instagram and Spotify.
- **pgvector** — An add-on that enables storing and searching mathematical representations of text (for future advanced search features).

**What it stores:**
- User accounts and API keys
- Logs of all queries (for monitoring and improvement)
- Vector embeddings (for future retrieval-augmented generation)

### 5. The Cache (Redis)

**What it is:** A super-fast temporary storage system that remembers recent answers.

**Built with:**
- **Redis** — An in-memory data store. Think of it as a very fast notepad that the server checks before doing expensive AI calls.

**What it does:**
- Stores answers to questions that have been asked before
- Drug/disease/comparison answers are saved for 30 days (medical facts don't change quickly)
- General answers are saved for 24 hours
- Makes repeat queries return in under 1 second instead of 15–30 seconds
- Also handles rate limiting (preventing abuse by limiting how many questions someone can ask per minute)

**What happens if Redis goes down:**
- The system keeps working — it just can't use cached answers and processes every question fresh
- Rate limiting falls back to a simpler in-memory system

### 6. The Reverse Proxy (Nginx)

**What it is:** The "front door" of the server that directs incoming traffic to the right place.

**Built with:**
- **Nginx** — The world's most popular web server, used by over 30% of all websites.

**What it does:**
- Handles the secure connection (HTTPS/SSL) so your data is encrypted
- Routes requests to the right service:
  - Medical questions (`/api/v1/...`) → Backend server
  - Everything else (`/`) → Website frontend
- Manages SSL certificates from Let's Encrypt (free, auto-renewing security certificates)

### 7. Docker (The Container System)

**What it is:** A system that packages each piece of software into its own isolated "container" — like separate rooms in a building.

**Built with:**
- **Docker** — The industry standard for containerization.
- **Docker Compose** — A tool that defines and runs all containers together.

**What it does:**
- Each service (database, cache, backend, frontend) runs in its own container
- Containers can talk to each other over a private network but are isolated from the outside
- If one container crashes, it automatically restarts
- Makes deployment reproducible — the same setup works identically on any server

**The containers:**

| Container | What's Inside | Purpose |
|-----------|--------------|---------|
| iatronix-db | PostgreSQL 16 + pgvector | Permanent data storage |
| iatronix-redis | Redis 7 | Fast caching and rate limiting |
| iatronix-backend | Python + FastAPI | Processes questions and talks to AI |
| iatronix-frontend | Node.js + Next.js | The website you see |

### 8. Cloudflare

**What it is:** A global network service that sits between users and the server.

**What it does:**
- Protects the server from attacks (DDoS protection)
- Makes the site load faster by serving content from servers closer to the user
- Manages the domain name (med.debkay.com)
- Provides an additional layer of SSL encryption

---

## Security Layers

The system has multiple layers of security, like checkpoints:

1. **Cloudflare** — Filters out malicious traffic before it reaches the server
2. **Nginx SSL** — Encrypts all communication between your browser and the server
3. **Payload Limit** — Rejects oversized requests (max 64KB) to prevent abuse
4. **IP Rate Limiting** — Limits each IP address to 30 requests per minute
5. **API Key Authentication** — Every request must include a valid API key
6. **Per-Key Rate Limiting** — Each API key is limited to 10 requests per minute
7. **Input Validation** — Questions are limited to 2,000 characters

---

## Resilience (What Happens When Things Break)

The system is designed to keep working even when parts of it fail:

| What Breaks | What Happens |
|-------------|-------------|
| Redis (cache) goes down | System keeps working, just slower (no caching). Rate limiting uses backup method. |
| Primary AI (Claude) goes down | Automatically switches to backup AI provider (OpenRouter). |
| Both AI providers go down | Returns a friendly "temporarily unavailable" message with cached results if any exist. |
| Database goes down | New queries still work (AI doesn't need the database). Logging is saved to a backup file. |
| Too many AI failures | Circuit breaker activates — stops making AI calls for 30 seconds to let the service recover, serves cached results instead. |

---

## Approved Medical Sources

The system only accepts citations from these trusted sources:

- **Clinical Guidelines:** NICE, AHA/ACC, ESC, WHO, IDSA, NCCN, ACOG, GOLD, KDIGO, ADA
- **Regulatory Bodies:** FDA, EMA, MHRA
- **Medical Databases:** UpToDate, BMJ Best Practice, Cochrane Library, PubMed (systematic reviews only)
- **Pharmacology References:** FDA drug labels, BNF, Micromedex

If the AI cites a source not on this list, the system flags it with a warning. If more than half the facts in a response have low confidence or missing citations, a prominent warning is displayed.

---

## Technology Summary

| Technology | Version | Role |
|------------|---------|------|
| Python | 3.12 | Backend programming language |
| FastAPI | 0.115+ | Backend web framework |
| Next.js | 15.1 | Frontend web framework |
| React | 19 | Frontend UI library |
| TypeScript | 5.7 | Frontend programming language |
| Tailwind CSS | 4.0 | Styling and design |
| PostgreSQL | 16 | Database |
| pgvector | latest | Vector search extension |
| Redis | 7 | Caching and rate limiting |
| Docker | latest | Containerization |
| Nginx | latest | Reverse proxy and SSL |
| Claude (Anthropic) | Sonnet 4 | Primary AI model |
| OpenRouter | — | Backup AI provider |
| Let's Encrypt | — | Free SSL certificates |
| Cloudflare | — | CDN, DNS, and DDoS protection |
| SQLAlchemy | 2.0+ | Database ORM |
| Alembic | latest | Database migrations |
| LangChain | 0.3+ | AI model integration |
| PyBreaker | latest | Circuit breaker pattern |

---

## Project Structure (Simplified)

```
med-ai-project/
├── docker-compose.yml          ← Defines all 4 containers
├── .env                        ← Secret keys and configuration
│
├── frontend/                   ← The website
│   ├── Dockerfile              ← How to build the frontend container
│   └── src/
│       ├── app/                ← Pages and API proxy
│       ├── components/         ← Reusable UI pieces (search bar, result cards, etc.)
│       └── lib/                ← Helper code (types, formatting, API calls)
│
├── backend/                    ← The brain
│   ├── Dockerfile              ← How to build the backend container
│   └── app/
│       ├── main.py             ← Application startup
│       ├── config.py           ← All settings in one place
│       ├── api/v1/             ← API endpoints (query, health, models, auth)
│       ├── middleware/         ← Security layers (rate limit, auth, payload limit)
│       ├── services/           ← Core logic (AI pipeline, caching, safety checks)
│       ├── schemas/            ← Data structure definitions
│       └── models/             ← Database table definitions
│
├── data/
│   └── drug_dictionary.json    ← List of ~500 known drugs for linking
│
└── db/
    └── init.sql                ← Database initialization
```

---

## Disclaimer

Iatronix is a medical reference tool designed to assist healthcare professionals. It is **not** a substitute for professional medical judgment, clinical decision-making, or direct patient care. Always verify critical information with primary sources and use clinical judgment when making treatment decisions.
