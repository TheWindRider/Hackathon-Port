# Zero Downtime Hackathon - Architecture & Tool Summary

## Core Challenge

Build an **Agentic Software Factory** - not just an app, but the executable, repeatable, observable system that builds apps. The app is the test run; the factory is the submission.

## Three-Layer Architecture

### 1. Factory Layer (Port.io)

**Purpose:** Plan architecture, coordinate agents, govern development

**Key Components:**

- **Context Lake** - Model factory context and shared state
- **Workflow Orchestration** - Multi-step work coordination
- **AI Agents** - Agent management and execution
- **Governance** - Standards, approvals, validation points
- **Interface Layer** - Human-in-control dashboards and views

**Integration Points:**

- Port AI Builder for rapid setup (Plan vs Build modes)
- MCP connectors for external coding agents
- Workflow triggers and scorecards
- Real-time audit trails

**Target Loop:** brief → plan → build → test → approval → release → audit

### 2. Data Layer (Bright Data Scraper Studio)

**Purpose:** Fetch and maintain live web data resiliently

**Key Features:**

- Terminal-based scraping (no browser switching)
- Project rules file integration (CLAUDE.md, .cursor/rules, CODEX.md)
- Automatic scraper repair on HTML structure changes
- Version-controlled scraper configuration
- Clean JSON output for agent consumption

**Requirements:**

- Data pipeline embedded in agentic workflow
- Reusable, version-controlled scraper configs
- Automatic detection and recovery from site changes
- Fresh, structured data feeding the factory

### 3. Observability Layer (SigNoz)

**Purpose:** Monitor performance, trace execution, surface failures

**Key Capabilities:**

- Distributed tracing across pipeline steps
- Metrics collection (latency, throughput, error rates)
- Log aggregation and search
- Dashboard building for operators
- Alert and escalation workflows

**Coverage Areas:**

- Data pipeline execution
- API endpoint performance
- Scraper failure and auto-repair events
- Agent coordination steps
- Factory loop timing

## Judging Criteria

### Port Integration

- Clear workspace setup (goals, choices, risks, services)
- Faithful brief understanding and constraint handling
- Agent/tool coordination effectiveness
- Testing and verification automation
- Failure handling and retry logic
- Operator visibility into what happened and why
- Repeatability (not one-off rehearsed results)

### Bright Data Integration

- Pure terminal workflow (no browser dashboard dependency)
- Proper scraper rules configuration in project files
- Clean JSON output structure
- Working auto-repair execution
- Data freshness and actual app usage

### SigNoz Integration

- Active tracing across meaningful system parts
- Log collection and correlation
- Metric tracking (latency, throughput, errors)
- First-class failure and auto-repair event signals
- Observability feeding back into factory (alerts, retries, escalation)

## Technical Approach Guidelines

**Do:**

- Build the factory system around the model (model is one worker)
- Make decisions based on context observation
- Verify results and adjust accordingly
- Integrate all three tools into one pipeline
- Focus on system design over clever model selection

**Don't:**

- Single giant prompt (not a factory)
- Fixed CI pipeline with LLM bolted on (not adaptive)
- Hardcoded HTML parsers (not resilient data pipeline)
- Console printing as observability (not production-ready)
- One-time scraping without repair (not sustainable)

## Project Idea Patterns

- Brief-to-App Factory: End-to-end automated development
- Self-Healing Data Product: Auto-repairing scrapers with monitoring
- Competitor-Watch Feature Factory: Change-driven development
- Docs-to-RAG Factory: Self-rebuilding knowledge bases
- Incident-to-Fix Factory: Alert-driven remediation workflows

## Success Metrics

- Can the factory run repeatedly with consistent results?
- Can operators diagnose failures from dashboards alone?
- Does the data pipeline survive web structure changes?
- Are all three tools integrated into one cohesive system?
