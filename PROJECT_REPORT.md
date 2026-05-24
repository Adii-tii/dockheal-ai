# DOCKHEAL: Autonomous Healing and AI-Assisted Incident Investigation Platform

---

## 1. Introduction

In modern production environments, software services are packaged and deployed using containerization technologies, with Docker serving as the primary standard. Containerization offers unmatched flexibility, portability, and velocity. However, it also introduces operational challenges. Containers running at scale frequently encounter critical errors, including:
*   **Out-of-Memory (OOM) Kills**: The Linux kernel terminates a process when it exceeds its cgroup resource constraints.
*   **Crash Loops**: Application processes exit repeatedly due to startup failures, misconfigurations, or database connectivity losses.
*   **Silent Degradation**: The container remains in a "running" state but fails internal healthchecks, returning HTTP 500 status codes.
*   **Resource Starvation**: Runaway processes consume CPU cores or memory pages, starving peer containers on the same host.

Traditional operational approaches to diagnosing and resolving these incidents are manual, time-consuming, and error-prone. **DockHeal** is an academic and enterprise-ready **Autonomous Healing and AI-Assisted Incident Investigation Platform** designed specifically for Docker hosts. It blends deterministic recovery rules (pre-flight checks, retry limits, cooldown periods) with an agentic AI loop (powered by the Mistral large language model) to continuously monitor, analyze, explain, and safely remediate container incidents.

The technology stack for DockHeal is structured into a distributed microservice architecture:
1.  **Core Backend**: FastAPI (Python 3.10+), utilizing asynchronous concurrency (`anyio`/`asyncio`) to ensure non-blocking task execution.
2.  **Database & ORM**: PostgreSQL, mapped using SQLAlchemy 2.0 (with asyncpg driver) and migrated via Alembic.
3.  **AI Engine**: Mistral LLM API integrated via a custom streaming execution engine, executing iterative investigation routines.
4.  **Telemetry & Daemon**: Docker SDK (Python) interacting directly with the host `/var/run/docker.sock` to extract real-time system metrics, container statuses, and Docker event streams.
5.  **Frontend Client**: React.js built on Vite, styled using Tailwind CSS, and managed globally with Zustand state-stores and real-time WebSockets.

---

## 2. Profile of the Problem & Scope of the Study

### Problem Statement
In conventional Docker deployments, container monitoring and incident remediation are separated. Current infrastructure monitoring platforms (e.g., Prometheus, Grafana, Datadog) excel at metrics ingestion and alert dispatching but offer no remediation capabilities. When a service goes down:
1.  An alert triggers on a metric threshold breach.
2.  Alertmanager routes the notification to PagerDuty, waking up an on-call engineer.
3.  The engineer manually logs into the target host via SSH.
4.  They run command-line diagnostics (`docker logs`, `docker inspect`, `docker stats`) to find error messages.
5.  They determine a remedy (e.g., restarting, adjusting memory limits) and execute it.
6.  They monitor the service to verify recovery.

This manual troubleshooting sequence leads to a high Mean Time to Resolution (MTTR), causing expensive application downtime and team fatigue. Simple automated restart solutions (like Docker's native `restart: always` policy) can worsen issues—such as repeatedly restarting an Out-Of-Memory container, which wastes CPU cycles and hides the root cause.

```text
Traditional MTTR Breakdown:
┌──────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ Alert Ingest │ ───> │ Operator Paged│ ───> │ Manual SSH   │ ───> │ Container    │
│ (2 - 5 mins) │      │ (5 - 15 mins)│      │ & Diagnostic │      │ Remediation  │
└──────────────┘      └──────────────┘      │ (10-30 mins) │      │ (1 - 5 mins) │
                                            └──────────────┘      └──────────────┘
                                            Total MTTR: 18 - 55 minutes of downtime
```

### Rationale and Scope
DockHeal bridges the gap between monitoring and resolution by running an autonomous agent beside the Docker daemon. The scope of this project includes:
*   **Real-time Event and Metric Listening**: Collecting sub-second cgroup resource stats (CPU, Memory, Uptime) and system event streams (`die`, `oom`, `kill`).
*   **Telemetry Aggregation Layer**: Compiling container states, log snippets, dependency mappings, and resource usage into a structured JSON "Investigation Packet".
*   **AI Agent Loop**: An iterative loop using Mistral AI that proposes diagnostic pathways and executes custom Model Context Protocol (MCP) tools in a restricted command sandbox.
*   **Multi-layered Safety Guardrails**: Enforcing strict, deterministic check gates (e.g., cooldowns, manual stops, peer dependency health) that prevent catastrophic cascading failure restarts and LLM hallucinations.
*   **Live Policy Administration**: Providing a dashboard to dynamically alter system policies (retry counts, severity gates, blocked tools) at runtime.

---

## 3. Existing System

### Introduction
The existing system relies on disconnected monitoring, manual troubleshooting, and deterministic, static automation scripts. System status is exposed through metrics exporters, and humans act as the control loop.

### Existing Software
1.  **Watchtower**: Automatically updates running containers when a new image is pushed. It lacks diagnostics, does not evaluate logs, and has no capacity to heal internal application failures.
2.  **Portainer / Docker Desktop**: GUI tools for viewing container lists and stats. They require active manual operation to troubleshoot and restart services.
3.  **Prometheus + Alertmanager + PagerDuty**: Collects metrics and triggers alerts when thresholds (e.g., memory > 90%) are breached. It cannot automatically investigate or run corrective actions.

### DFD for Present (Traditional) System

```mermaid
flowchart TD
    Docker[Docker Engine Container Crash] -->|Exposes Logs & Events| Exporter[Metrics Exporter]
    Exporter -->|Scrapes Metrics| Prometheus[Prometheus Server]
    Prometheus -->|Triggers Alert Rule| Alertmanager[Alertmanager]
    Alertmanager -->|Pushes Alert Notification| PagerDuty["PagerDuty / SMS Alert"]
    PagerDuty -->|Wakes Up / Pages| Dev["SRE / Developer"]
    Dev -->|1. Runs SSH Connection| Server[Production Server]
    Server -->|2. Runs docker logs / docker stats| Inspect[Analyze Failure]
    Inspect -->|3. Runs docker restart| Action[Manual Container Remediation]
    Action -->|4. Verify Health| Success{Health Reached?}
    Success -->|Yes| End[Resolve Alert]
    Success -->|No| Inspect
```

### What's New in DockHeal
DockHeal replaces the manual troubleshooting sequence with an autonomous AI Agent bounded by safety rules. Instead of alerting a developer immediately:
1.  DockHeal detects the failure.
2.  It aggregates logs, dependencies, and metrics into an **Operational Context Packet**.
3.  An AI Investigator streams thoughts, executes diagnostic tools (like checking log errors, inspect configurations), and determines the root cause.
4.  It checks the proposed fix against **Guardrails** and a **Command Sandbox**.
5.  If safe, it executes the remediation and verifies recovery. If unsafe or high-risk, it escalates to the engineer with a pre-analyzed Root Cause Analysis (RCA) report.

---

## 4. Problem Analysis

### Product Definition
DockHeal is a self-contained monitoring and healing daemon. It operates as a web application with a FastAPI backend communicating with the Docker host socket, and a React UI showing container lifecycles, streaming AI thoughts, audit trails, and policy controls.

### Feasibility Analysis

#### 1. Technical Feasibility
*   **Docker Socket API**: The Docker Engine exposes a local UNIX socket (`/var/run/docker.sock` on Linux or named pipes on Windows). The Python SDK provides full bindings for inspection, logs, and container state control.
*   **FastAPI & Async Integration**: FastAPI's async loops allow continuous, non-blocking polling of container stats alongside API requests. SQLAlchemy's asyncpg engine permits concurrent read/writes to PostgreSQL.
*   **LLM Integrations**: Mistral's API supports fast response streaming, enabling the UI to render real-time agent thoughts.

#### 2. Economic Feasibility
*   **Reduced MTTR**: The cost of downtime in production environments can range from thousands to millions of dollars. Automating recovery reduces recovery times from hours to seconds.
*   **Operational Cost**: DockHeal is a lightweight service running on the host. It reduces the need for constant on-call support rotations.

#### 3. Operational Feasibility
*   **User Acceptability**: Developers and operators can interact with the system via a modern dashboard.
*   **Co-Pilot Control**: A hybrid mode ("Co-Pilot") ensures that high-risk actions (e.g. modifying container limits) require human approval, providing a transition path to full automation.

### Project Plan

```mermaid
gantt
    title DockHeal Development Project Plan
    dateFormat  YYYY-MM-DD
    section Phase 1: Core Telemetry Daemon
    Docker API Client Integration           :active, p1, 2026-05-01, 7d
    Metrics and Event Listener Loop         :p2, after p1, 7d
    section Phase 2: DB & Aggregation
    Database Schema Configuration           :p3, 2026-05-10, 5d
    Operational Context Aggregator          :p4, after p3, 6d
    section Phase 3: AI Loop & Safety
    Mistral Agent Execution Wrapper         :p5, 2026-05-18, 7d
    Guardrails & Sandbox Validation         :p6, after p5, 6d
    section Phase 4: UI & WebSocket
    Zustand Store & WebSocket Server        :p7, 2026-05-20, 5d
    React Pages (Dashboard, Sandbox, Timeline):p8, after p7, 8d
```

---

## 5. Software Requirement Analysis

### Introduction
The software requirement specification outlines the core functional capabilities and non-functional bounds of the DockHeal platform.

### General Description
The application runs as a Docker container or host process. It requires access to the host's Docker socket and database. It interacts with the operator via HTTP/WebSockets and with Mistral via HTTPS.

### Specific Requirements

#### 1. Functional Requirements

##### 1.1 Container Discovery and State Synchronization
*   **Input**: Host `/var/run/docker.sock` API.
*   **Process**: Poll the Docker socket every 30 seconds to fetch all containers. Map each to the database schema.
*   **Output**: Upsert rows into the `containers` table with matching statuses and configuration labels.
*   **Validation**: Exclude system containers or DockHeal's own service components to avoid self-monitoring recursion loops.

##### 1.2 Telemetry Aggregator (Context Engine)
*   **Input**: Container name and raw event triggers.
*   **Process**:
    1. Query container attributes (started_at, exit_code, status, healthcheck status).
    2. Extract last 200 lines of standard output/error logs.
    3. Run regex classification for crash signals (e.g., SIGSEGV, SIGTERM, NullPointerException, SyntaxError).
    4. Read host cgroup utilization to calculate CPU and memory usage.
    5. Search labels for Compose dependency relationships (`depends_on`).
    6. Mask credentials matching sensitive key substrings (e.g., `password`, `key`, `token`, `secret`) with `<REDACTED>`.
*   **Output**: A structured JSON `OperationalContext` packet.
*   **Validation**: Verify the telemetry packet generation age does not exceed the `packet_max_age_secs` policy threshold.

##### 1.3 AI Agent Loop & Tool Invocation
*   **Input**: JSON context packet, system instructions, and user policies.
*   **Process**:
    1. Send context packet to the Mistral model API.
    2. Read streaming thoughts response chunk-by-chunk.
    3. If the model invokes a tool call, pause streaming and route the request to the Sandbox.
*   **Output**: Streamed text response showing reasoning steps, tool invocation requests, and final RCA reports.
*   **Validation**: Ensure the tool execution does not exceed the `max_deep_iterations` limit (default 5).

##### 1.4 Sandbox & Guardrails Engine
*   **Input**: Proposed tool call (name and arguments), context packet, and active policies.
*   **Process**:
    1. **Sandbox Phase**: Verify if the target container exists, validation metrics are within ranges, and the tool is not explicitly blacklisted in the policies registry.
    2. **Guardrails Phase**: Verify safety logic:
        *   Confirm the target container has not been manually stopped by an operator.
        *   Confirm the target container is not locked (`operator_lock`).
        *   Check that the time since the last action exceeds the cooldown setting (e.g., 300 seconds).
        *   Confirm the current retry count is less than the max retries policy limit.
        *   Block auto-restarts if an OOM event is detected and `oom_block_restart` is active.
        *   Confirm the incident severity score is less than the severity gate policy setting.
*   **Output**: A signed `GuardrailDecision` JSON payload (`allowed: true/false`, `action: execute/warn/block/escalate`, `reason: string`).
*   **Validation**: All write actions must go through this double-layer validation. No developer or AI override can bypass a guardrail block.

##### 1.5 Real-Time Client Visualizer
*   **Input**: FastAPI backend WebSocket client connections.
*   **Process**: Broadcast real-time container metrics, active investigations, and streaming AI thoughts to all connected dashboard instances.
*   **Output**: Real-time dashboard updates with no manual browser refreshes needed.

##### 1.6 Simulation Engine
*   **Input**: User click in the Simulator panel.
*   **Process**: Docker socket API call to trigger container errors (OOM crash, healthcheck timeout, crash loops) in mock containers.
*   **Output**: Simulated failures to test and verify the DockHeal pipeline.

#### 2. Non-Functional Requirements
*   **Performance**: The telemetry gather loop must execute within 30 seconds without putting more than 1% CPU overhead on the host.
*   **Scalability**: The backend must handle up to 100 containers on a single host.
*   **Security**: Sensitive environment variables in context packets (such as tokens, keys, and passwords) must be automatically redacted.
*   **Robustness**: If the LLM API is unavailable, the system must fall back to deterministic recovery (e.g. attempting a standard restart) or escalate immediately.

---

## 6. Design

### System Design Architecture

```mermaid
flowchart LR
    subgraph client_app ["Client Application (React/Vite)"]
        Dashboard[Dashboard View]
        Timeline["Timeline & Audit Logs"]
        Settings[Policies Panel]
        Zustand[Zustand State Store]
    end

    subgraph backend_app ["FastAPI Application (Python Backend)"]
        API[REST API Endpoints]
        WS[WebSocket Manager]
        Monitor[Monitor Loop Daemon]
        Aggregator[Context Aggregator]
        Guardrails[Guardrail Safety Gate]
        Sandbox[Sandbox Precondition Engine]
        AI[AI Investigator Engine]
    end

    subgraph External Infrastructure
        DockerSock[("/var/run/docker.sock")]
        PostgreSQL[("PostgreSQL Database")]
        Mistral[Mistral AI API]
    end

    Dashboard & Timeline & Settings <--> Zustand
    Zustand <-->|HTTP & WebSockets| API & WS
    Monitor -->|Discover & Write| DockerSock
    Monitor -->|Sync Status| PostgreSQL
    Monitor -->|Trigger Incident| Aggregator
    Aggregator -->|Read Telemetry| DockerSock
    Aggregator -->|Generate Context Packet| AI
    AI <-->|Analyze / Stream Thoughts| Mistral
    AI -->|Request Action| Sandbox
    Sandbox -->|Verify State| DockerSock
    Sandbox -->|Approve Action| Guardrails
    Guardrails -->|Enforce Safety Rules| PostgreSQL
    Guardrails -->|Write Action| DockerSock
    API <--> PostgreSQL
```

### Database Schema Attribute Mappings

#### 1. `containers` Table
Tracks monitored Docker containers.
| Attribute | Data Type | Constraint | Description |
| :--- | :--- | :--- | :--- |
| `id` | UUID | Primary Key, Not Null | Unique identifier |
| `container_name` | VARCHAR(255) | Not Null, Index | Container name |
| `runtime_id` | VARCHAR(255) | Not Null, Unique, Index | Docker 64-char container ID |
| `image_name` | VARCHAR(512) | Nullable | Image tag |
| `status` | VARCHAR(100) | Not Null, Index | e.g. running, exited, restarting, dead, unknown |
| `health_status` | VARCHAR(100) | Not Null | e.g. healthy, unhealthy, starting, none |
| `auto_restart` | BOOLEAN | Not Null | True if self-healing is active |
| `is_manually_stopped` | BOOLEAN | Not Null, default: false | True if user manually stopped the container |
| `environment` | VARCHAR(100) | Nullable | Environment classification |
| `last_seen` | TIMESTAMPTZ | Nullable | Last sync timestamp |
| `labels` | JSONB | Nullable | Raw Docker labels dictionary |
| `ports` | JSONB | Nullable | Exposed port bindings mappings |
| `runtime_metadata` | JSONB | Nullable | Engine-specific configuration |
| `created_at` | TIMESTAMPTZ | Not Null | Record creation timestamp |
| `updated_at` | TIMESTAMPTZ | Not Null | Record update timestamp |

#### 2. `investigations` Table
The central registry for all incident investigations.
| Attribute | Data Type | Constraint | Description |
| :--- | :--- | :--- | :--- |
| `id` | UUID | Primary Key, Not Null | Unique identifier |
| `container_id` | UUID | FK (containers.id), Not Null, Index | Affected container |
| `title` | VARCHAR(512) | Not Null | Title description of the incident |
| `incident_summary` | TEXT | Nullable | Short summary of the failure |
| `severity_level` | VARCHAR(50) | Not Null, Index | e.g. P0, P1, P2, P3 |
| `lifecycle_state` | VARCHAR(100) | Not Null, Index | e.g. DETECTED, ANALYZING, RESOLVED, ESCALATED |
| `status` | VARCHAR(100) | Nullable | Human-readable status |
| `root_cause` | TEXT | Nullable | Final root cause analysis |
| `proposed_action` | TEXT | Nullable | Proposed remediation steps |
| `thoughts` | TEXT | Nullable | Raw streaming thoughts from the LLM |
| `confidence` | FLOAT | Nullable | AI confidence rating (0.0 to 1.0) |
| `auto_restart_allowed` | BOOLEAN | Not Null | True if auto remediation is allowed |
| `approval_required` | BOOLEAN | Not Null | True if manual operator approval is required |
| `approved_by` | VARCHAR(255) | Nullable | Username of reviewer |
| `approved_at` | TIMESTAMPTZ | Nullable | Approval timestamp |
| `started_at` | TIMESTAMPTZ | Nullable | Investigation start timestamp |
| `resolved_at` | TIMESTAMPTZ | Nullable | Resolution timestamp |
| `created_at` | TIMESTAMPTZ | Not Null, Index | Creation timestamp |

#### 3. `rca_reports` Table
Stores root cause analysis reports.
| Attribute | Data Type | Constraint | Description |
| :--- | :--- | :--- | :--- |
| `id` | UUID | Primary Key, Not Null | Unique identifier |
| `investigation_id` | UUID | FK (investigations.id), Not Null, Index | Investigation record |
| `rca_version` | INTEGER | Not Null | Version index for changes |
| `is_final` | BOOLEAN | Not Null | True if finalized |
| `incident_summary` | TEXT | Nullable | Overview of the crash |
| `impact_assessment` | TEXT | Nullable | Analysis of downstream impact |
| `what_failed` | TEXT | Nullable | Description of the core failure |
| `why_it_happened` | TEXT | Nullable | Explanation of the failure mechanism |
| `action_proposed` | TEXT | Nullable | Proposed remediation details |
| `recovery_status` | VARCHAR(100) | Nullable | Status of recovery checks |
| `long_term_prevention`| TEXT | Nullable | Prevention recommendations |
| `confidence_score` | FLOAT | Nullable | AI confidence rating (0.0 to 1.0) |
| `evidence_found` | JSONB | Nullable | Supporting evidence list |
| `created_at` | TIMESTAMPTZ | Not Null | Record creation timestamp |

#### 4. `recovery_actions` Table
Audits remediation execution runs.
| Attribute | Data Type | Constraint | Description |
| :--- | :--- | :--- | :--- |
| `id` | UUID | Primary Key, Not Null | Unique identifier |
| `investigation_id` | UUID | FK (investigations.id), Not Null, Index | Investigation record |
| `action_name` | VARCHAR(255) | Not Null | Target tool (e.g. `restart_container`) |
| `action_type` | VARCHAR(100) | Not Null | e.g. RESTART, CONFIG_PATCH, ROLLBACK |
| `execution_status` | VARCHAR(100) | Not Null, Index | e.g. PENDING, RUNNING, SUCCESS, FAILED |
| `execution_logs` | TEXT | Nullable | Output logs from the execution |
| `rollback_available` | BOOLEAN | Not Null | True if rollback logic is configured |
| `rollback_executed` | BOOLEAN | Not Null | True if rollback occurred |
| `parameters` | JSONB | Nullable | Parameters passed to the execution tool |
| `validation_results` | JSONB | Nullable | Post-execution validation metrics |
| `created_at` | TIMESTAMPTZ | Not Null, Index | Creation timestamp |

---

### Detailed Design & Flowcharts

#### AI Investigation Agent & Sandbox Validation Loop

```mermaid
flowchart TD
    Start[Incident Detected] --> Agg[Context Aggregator Assembles Packet]
    Agg --> AI[AI Prompt Constructed]
    AI --> LLM[Consult Mistral AI Engine]
    LLM -->|Streams Thoughts| WS[Broadcast to UI WebSockets]
    LLM -->|Proposes Action: tool_call| Sandbox{Sandbox Validation}
    
    subgraph Sandbox Precondition Verification
        Sandbox -->|Check 1: Tool Blocked?| SB1{Blocked in Policies?}
        SB1 -->|Yes| RejectSB[Return Approved=False]
        SB1 -->|No| SB2{"Container Exists & State Correct?"}
        SB2 -->|No| RejectSB
        SB2 -->|Yes| SB3{"OOM / Headroom Checks Pass?"}
        SB3 -->|No| RejectSB
        SB3 -->|Yes| ApproveSB[Return Approved=True]
    end
    
    RejectSB --> Block[Update State to BLOCKED & Stop]
    ApproveSB --> Guardrails{Guardrails Evaluation}
    
    subgraph Guardrails Safety Policies
        Guardrails --> G1{Is Cooldown Active?}
        G1 -->|Yes| GBlock["Block / Stop"]
        G1 -->|No| G2{Is Retry Limit Exceeded?}
        G2 -->|Yes| GEscalate[Escalate to Human]
        G2 -->|No| G3{Severity Score >= Gate?}
        G3 -->|Yes| GEscalate
        G3 -->|No| G4{Is Peer Cascade Present?}
        G4 -->|Yes| GEscalate
        G4 -->|No| GExecute[Execute Action]
    end
    
    GBlock --> Block
    GEscalate --> Await["Update State to AWAITING_APPROVAL & Alert Operator"]
    GExecute --> RunTool[Run Tool on Docker Socket]
    
    RunTool --> Poll{Poll Container Health}
    Poll -->|Recovered| Resolved[Mark RESOLVED]
    Poll -->|Failed / Timeout| GEscalate
```

---

### Pseudocode Listings

#### 1. Context Aggregator: `build_investigation_packet`
This logic creates the context packet when an incident is detected.

```python
def build_investigation_packet(container_name, incident_event):
    # Initialize packet structure
    packet = {
        "schema_version": "1.0",
        "generated_at": get_current_iso_time(),
        "investigation_id": generate_uuid4()
    }
    
    # 1. Fetch container attributes from Docker
    docker_container = docker_client.get_container_by_name(container_name)
    packet["container_state"] = {
        "id": docker_container.id,
        "name": docker_container.name,
        "image": docker_container.image,
        "status": docker_container.status,
        "health": docker_container.health,
        "restart_count": docker_container.restart_count,
        "exit_code": docker_container.exit_code,
        "oom_killed": docker_container.oom_killed,
        "env_vars": sanitize_and_redact_env(docker_container.env)
    }
    
    # 2. Collect container logs (last 200 lines) and run basic diagnostics
    raw_logs = docker_container.read_logs(tail=200)
    packet["logs"] = {
        "raw_tail": raw_logs,
        "signals": parse_logs_for_errors(raw_logs)  # Matches regex for SEGFAULT, NullPointer, etc.
    }
    
    # 3. Retrieve system cgroup metrics
    stats = docker_container.get_stats()
    packet["metrics_snapshot"] = {
        "cpu_percent": calculate_cpu_percentage(stats),
        "mem_usage_mb": stats.memory_usage_mb,
        "mem_limit_mb": stats.memory_limit_mb,
        "mem_percent": (stats.memory_usage_mb / stats.memory_limit_mb) * 100,
        "uptime_seconds": calculate_uptime(docker_container.started_at)
    }
    
    # 4. Map compose dependencies
    packet["dependency_context"] = map_compose_peers(container_name)
    
    # 5. Deterministic Severity Assessment
    packet["assessment"] = evaluate_heuristic_severity(packet)
    
    return packet
```

#### 2. Sandbox Precondition Validator
Determines if an action is valid for execution on the host.

```python
def validate_sandbox_preconditions(tool_name, parameters, context_packet):
    active_policies = load_policies()
    
    # 1. Verify sandbox blocked tools configurations
    if tool_name in active_policies.blocked_tools:
        return SandboxResult(approved=False, reason="Tool is blacklisted in policies")
        
    container_name = parameters.get("container_name")
    
    # 2. Verify packet freshness
    packet_age = get_current_time() - context_packet.generated_at
    if packet_age > active_policies.packet_max_age_secs:
        return SandboxResult(approved=False, reason="Context packet is stale")
        
    # 3. Verify target container exists on the host
    if not docker_client.container_exists(container_name):
        return SandboxResult(approved=False, reason="Container does not exist on host")
        
    # 4. Run per-tool validation checks
    if tool_name == "restart_container":
        container = docker_client.get_container(container_name)
        if container.status not in ["running", "exited", "restarting"]:
            return SandboxResult(approved=False, reason="Container is in a non-restartable state")
        if context_packet.logs.signals.oom_killed:
            return SandboxResult(approved=False, reason="OOM detected; restart will likely fail again immediately")
        return SandboxResult(approved=True, risk="low", effects=["Temporary service offline downtime (~10s)"])
        
    elif tool_name == "update_memory_limit":
        new_limit = parameters.get("memory_mb")
        current_usage = context_packet.metrics_snapshot.mem_usage_mb
        # New limit must provide at least 20% headroom
        if new_limit < (current_usage * 1.2):
            return SandboxResult(approved=False, reason="New limit provides insufficient memory headroom")
        return SandboxResult(approved=True, risk="medium", effects=["Modifies container limits runtime parameters"])
        
    return SandboxResult(approved=False, reason="No sandbox validation rule defined for this tool")
```

---

## 7. Testing

### Testing Strategy
DockHeal is verified using functional, structural, integration, and system-level tests. Additionally, incident simulations are run to verify end-to-end healing flows.

### End-to-End Incident Test-Case Matrix

| Test ID | Scenario | Preconditions | Inputs / Trigger | Expected Output / Process | Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-01** | **OOM Failure Detection & Escalation** | Container has auto-restart active. Cooldown is inactive. | Simulate OOM event (exit code 137). | 1. Monitor loop identifies the OOM.<br>2. Severity is floored to 85.<br>3. Restart is blocked by OOM guard.<br>4. State updates to `AWAITING_APPROVAL`. | **PASSED** |
| **TC-02** | **Remediation Cooldown Enforcement** | Remediation was executed 45 seconds ago. Cooldown policy is 300s. | Trigger healthcheck failure on container. | 1. Monitor loop identifies the failure.<br>2. System blocks restart execution.<br>3. Incident logs show: `cooldown active (255s remaining)`. | **PASSED** |
| **TC-03** | **Manual Operator Lock Override** | Container is locked (`operator_lock`). | Trigger crash simulation on the locked container. | 1. Telemetry is gathered.<br>2. Guardrails identify the active operator lock.<br>3. State updates to `BLOCKED`. | **PASSED** |
| **TC-04** | **Cascading Peer Failure Prevention** | 3 peer containers in the same compose project are unhealthy. | Trigger crash simulation on target container. | 1. Context mapper flags 3 unhealthy peer services.<br>2. Incident is escalated immediately (severity level set to P0).<br>3. State updates to `ESCALATED`. | **PASSED** |
| **TC-05** | **Policy Mutation and Persistence** | Default severity gate is set to 80. | Mutate severity gate value to 50 via `PUT /policies`. | 1. Settings update in memory.<br>2. Configuration is saved to `.policies.json`. | **PASSED** |
| **TC-06** | **Credential Redaction in Packets** | Container has environment keys: `DB_PASS=secret123`, `APP_PORT=80`. | Query context aggregation payload. | 1. `APP_PORT` value is visible.<br>2. `DB_PASS` value is replaced with `<REDACTED>`. | **PASSED** |

---

## 8. Implementation

### Deployment stack
DockHeal is structured to run as a multi-container Docker application or alongside existing services on a production server.

```mermaid
flowchart TD
    ServerHost[Host Production Server]
    subgraph DockHeal Service Stack
        ReactClient[Vite React Client Container: Port 5173]
        FastAPIBackend[FastAPI Backend Container: Port 8000]
        PostgreSQLDB[("PostgreSQL Database Container: Port 5432")]
    end
    DockerDaemon["Host Docker Daemon Engine: /var/run/docker.sock"]
    
    ReactClient <-->|HTTP / WS| FastAPIBackend
    FastAPIBackend <-->|SQL / Asyncpg| PostgreSQLDB
    FastAPIBackend <-->|UNIX Socket Mount| DockerDaemon
```

### Installation Steps
1.  **Mount the Docker Socket**: The backend container must mount the host's `/var/run/docker.sock` UNIX socket:
    ```bash
    -v /var/run/docker.sock:/var/run/docker.sock
    ```
2.  **Environment Configuration**: Configure the `.env` file in the backend folder:
    ```env
    DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/dockheal
    API_KEY=your_mistral_api_key
    ```
3.  **Run Migrations**: Build the database schema using Alembic:
    ```bash
    alembic upgrade head
    ```
4.  **Launch Backend**: Start the FastAPI server using Uvicorn:
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ```
5.  **Launch Client**: Start the Vite React client:
    ```bash
    npm install
    npm run dev
    ```

### Conversion Plan
To deploy DockHeal without risking production downtime:
1.  **Phase 1: Monitor-Only (Co-Pilot Mode)**: Deploy DockHeal with `agent_mode = Co-Pilot` and `severity_gate = 0`. The system gathers telemetry, builds RCA reports, and requests operator approval before running any remediation.
2.  **Phase 2: Hybrid Automation**: Set the severity gate to `80`. Moderate incidents (like simple application crashes) are resolved automatically. Severe incidents (like OOM events) require approval.
3.  **Phase 3: Full Autopilot**: Set the system to full autopilot mode for trusted containers.

### Post-Implementation Maintenance
*   **Archiving Old Metrics**: A background task runs hourly to aggregate raw system metrics and purge data older than 24 hours, keeping PostgreSQL database storage stable.
*   **API Key Rotation**: The Mistral API key should be rotated periodically using environment variables without requiring code changes.

---

## 9. Project Legacy

### Current Status
DockHeal is a functional prototype. It discovers host containers, tracks CPU/Memory usage, and identifies incidents. Its AI engine uses Mistral to stream reasoning logs to React, and safety guardrails work as designed.

### Remaining Areas of Concern & Future Scope
*   **Multi-Host Swarm and Kubernetes Orchestration**: Currently, DockHeal operates on a single host. Future scope includes extending it to monitor Kubernetes clusters via the Kubernetes API.
*   **Fine-Grained Sandbox Environments**: While the sandbox validates preconditions, running commands inside temporary, isolated Docker scratch containers would improve security for untrusted configurations.

### Lessons Learnt
1.  **LLM Latency Mitigation**: Streaming LLM output using Server-Sent Events (SSE) ensures a responsive user experience.
2.  **Safety Guardrails are Mandatory**: AI agents are prone to hallucinating parameters. Using a separate, hardcoded safety validation gate is critical before running commands.

---

## 10. User Manual

### 1. Dashboard View
Shows a real-time list of all containers on the host, including their status (running/exited), CPU/memory usage, and current healthcheck state.

```text
+------------------------------------------------------------------------------------+
| ⚓ DOCKHEAL                                               [ Dashboard ] [Timeline] |
+------------------------------------------------------------------------------------+
| MONITORED CONTAINERS                                                               |
| +-----------------+-----------+-------------+------------+-----------------------+ |
| | Container Name  | Status    | CPU Usage   | Memory     | Actions               | |
| +-----------------+-----------+-------------+------------+-----------------------+ |
| | production-db   | [RUNNING] | [|||   12%] | 256/2048MB | [Restart] [Lock]      | |
| | api-gateway     | [RUNNING] | [||||| 24%] | 120/1024MB | [Restart] [Lock]      | |
| | web-frontend    | [UNHEALTHY] [||||||56%] | 980/1024MB | [Restart] [Lock]      | |
| +-----------------+-----------+-------------+------------+-----------------------+ |
|                                                                                    |
| ACTIVE INCIDENTS (Awaiting Review)                                                 |
| [!] web-frontend: CRASH_LOOP detected (Severity Score: 78)                         |
|     Root Cause Analysis Draft: Crash loop due to database connection timeout.      |
|     Proposed Remedy: Restart container after database health check completes.      |
|     [ Approve Remediation ]   [ Reject / Escalate ]                                |
+------------------------------------------------------------------------------------+
```

*   **Locking a Container**: Select a container and click "Lock". This blocks all automated remediation actions for that container.
*   **Manual Restart**: Click "Restart" on a container to trigger a manual restart via the API.

### 2. Investigations Panel
Shows active incident investigations.
*   **Streaming Terminal**: Displays real-time thoughts and tool calls from the AI Agent.
*   **Root Cause Analysis (RCA)**: Summarizes what caused the failure.
*   **Approval Dialog**: If an action requires approval, a dialog asks the operator to approve or reject the proposed remediation.

### 3. Policy Controls
Adjust policies at runtime:
*   **Cooldown Slider**: Set the minimum delay between remediation attempts.
*   **Max Retries Input**: Set the maximum retries before escalation.
*   **Severity Gate Slider**: Adjust the score threshold where autonomous actions require approval.

### 4. Sandbox Simulator
*   Inject memory leaks, healthcheck failures, or crash loops to test how DockHeal responds and recovers.

---

## 11. Source Code & Snapshot Map

### Directory Layout

```text
DockHeal/
├── backend/                       # FastAPI Server Application
│   ├── app/
│   │   ├── ai/                    # Mistral Agent and Safety Components
│   │   │   ├── tools/             # MCP Docker Control Tools
│   │   │   ├── deep_investigator.py  # Iterative AI loop
│   │   │   ├── guardrails.py      # Hard & Soft policy checker
│   │   │   └── sandbox.py         # Command validator
│   │   ├── context/               # Telemetry Context Aggregator
│   │   │   ├── aggregator.py      # Main context assembler
│   │   │   └── dependency_mapper.py  # Docker-Compose mapper
│   │   ├── db/                    # SQL Database Configuration & Models
│   │   │   ├── config/            # Async Engine configuration
│   │   │   └── models/            # SQLAlchemy DB tables mapping
│   │   ├── docker_monitor/        # Background tracking loops
│   │   └── main.py                # FastAPI endpoints & ws entry point
│   └── requirements.txt           # Python backend dependencies
└── client/                        # React Frontend Application
    ├── src/
    │   ├── pages/                 # React views (Dashboard, Timeline, etc.)
    │   ├── store.js               # Zustand Web Socket state store
    │   └── main.jsx               # React entry point
    └── package.json               # Node packages and scripts
```

---

## 12. Bibliography

1.  **FastAPI Documentation**: *FastAPI Web Framework, ASGI standards, and concurrency utilities.* [https://fastapi.tiangolo.com](https://fastapi.tiangolo.com)
2.  **Docker Engine SDK**: *Docker SDK for Python, Socket connections, and Event listeners.* [https://docker-py.readthedocs.io](https://docker-py.readthedocs.io)
3.  **SQLAlchemy 2.0**: *Object-Relational Mapping (ORM) and asynchronous connection architecture.* [https://www.sqlalchemy.org](https://www.sqlalchemy.org)
4.  **Mistral AI Developer Platform**: *LLM API prompt guidelines and function calling specifications.* [https://docs.mistral.ai](https://docs.mistral.ai)
5.  **Zustand Documentation**: *State management patterns in React application stores.* [https://zustand-demo.pmnd.rs](https://zustand-demo.pmnd.rs)
