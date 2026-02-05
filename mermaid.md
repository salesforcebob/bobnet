# BobNet Architecture Diagrams

This document contains comprehensive Mermaid diagrams illustrating the BobNet email simulation system.

## Table of Contents

1. [System Overview](#system-overview)
2. [Request Flow](#request-flow)
3. [Queue Message Types](#queue-message-types)
4. [Simulation Decision Flow](#simulation-decision-flow)
5. [HTML Override System](#html-override-system)
6. [Component Architecture](#component-architecture)
7. [Deployment Architecture](#deployment-architecture)

---

## System Overview

High-level view of the BobNet system architecture showing the three-binary design with two RabbitMQ queues.

```mermaid
flowchart LR
    subgraph External["External Sources"]
        CF[("Cloudflare\nEmail Workers")]
        MG[("Mailgun\nWebhooks")]
    end

    subgraph Rust["Rust Application"]
        WEB["bobnet-web\n(Axum Server)"]
        PROC["bobnet-processor\n(Message Parser)"]
        WORK["bobnet-worker\n(Simulator)"]
    end

    subgraph Queues["RabbitMQ (CloudAMQP)"]
        Q1[("inbound_webhooks")]
        Q2[("email_simulator")]
    end

    subgraph Targets["External Targets"]
        PIXELS["Open Pixels\n(SFMC, etc.)"]
        LINKS["Email Links\n(Marketing URLs)"]
    end

    CF -->|JSON + X-Custom-Auth| WEB
    MG -->|Form + HMAC| WEB
    WEB -->|Raw Payload| Q1
    Q1 --> PROC
    PROC -->|Parsed Job| Q2
    Q2 --> WORK
    WORK -->|HTTP GET| PIXELS
    WORK -->|HTTP GET| LINKS
```

---

## Request Flow

Detailed sequence diagram showing how an inbound email webhook flows through the system.

```mermaid
sequenceDiagram
    autonumber
    participant CF as Cloudflare Worker
    participant WEB as bobnet-web
    participant Q1 as inbound_webhooks
    participant PROC as bobnet-processor
    participant Q2 as email_simulator
    participant WORK as bobnet-worker
    participant EXT as External URLs

    CF->>WEB: POST /webhooks/cloudflare
    Note over WEB: Verify X-Custom-Auth header
    WEB->>Q1: Publish InboundWebhook
    WEB-->>CF: 200 OK {"status": "enqueued"}
    
    Q1->>PROC: Consume message
    Note over PROC: Parse RFC 5322 email<br/>Extract HTML body<br/>Extract Message-Id
    PROC->>Q2: Publish SimulatorJob
    Note over PROC: ACK message
    
    Q2->>WORK: Consume job
    Note over WORK: Check open probability<br/>Find SFMC open pixel
    
    alt Will Open
        WORK->>EXT: GET open pixel URL
        EXT-->>WORK: 200 OK (1x1 gif)
    end
    
    Note over WORK: Check click probability<br/>Filter links<br/>Select weighted links
    
    alt Will Click
        loop For each selected link
            WORK->>EXT: GET link URL
            EXT-->>WORK: 200/302 response
        end
    end
    
    Note over WORK: ACK job
```

---

## Queue Message Types

Entity relationship diagram showing the structure of messages in each queue.

```mermaid
erDiagram
    InboundWebhook {
        string source "cloudflare | mailgun"
        datetime received_at "ISO 8601 timestamp"
        CloudflarePayload cloudflare "Optional"
        MailgunPayload mailgun "Optional"
    }
    
    CloudflarePayload {
        string from "Sender email"
        string to "Recipient email"
        string subject "Email subject"
        string timestamp "Cloudflare timestamp"
        string raw_content "Full RFC 5322 email"
    }
    
    MailgunPayload {
        string recipient "Recipient email"
        string sender "Sender email"
        string subject "Email subject"
        string body_html "HTML content (optional)"
        string body_plain "Plain text (optional)"
        string stripped_html "Stripped HTML (optional)"
        string message_headers "JSON headers"
        int timestamp "Unix timestamp"
        string token "Verification token"
        string signature "HMAC signature"
    }
    
    SimulatorJob {
        string message_id "Unique identifier"
        string recipient "Target email"
        string sender "From email"
        string subject "Email subject"
        string html "HTML content"
        string source "cloudflare | mailgun"
    }
    
    InboundWebhook ||--o| CloudflarePayload : "contains"
    InboundWebhook ||--o| MailgunPayload : "contains"
```

---

## Simulation Decision Flow

Flowchart showing the decision logic for open and click simulation.

```mermaid
flowchart TD
    START([SimulatorJob Received])
    
    subgraph OpenSimulation["Open Simulation"]
        CHK_OPEN{Check open probability<br/>vs global rate}
        FIND_PIXEL["Find SFMC open pixel"]
        CHK_PIXEL{SFMC pixel found?}
        FETCH_PIXEL["Fetch SFMC pixel"]
        FETCH_RANDOM["Fetch random image"]
        LOG_OPEN["Log open success"]
        SKIP_OPEN["Skip open simulation"]
    end
    
    subgraph ClickSimulation["Click Simulation"]
        CHK_CLICK{Check click probability<br/>vs global rate}
        EXTRACT_LINKS["Extract links with rates"]
        FILTER_LINKS["Filter links:<br/>- Domain allow/deny<br/>- SFMC unsubscribe"]
        CHK_LINKS{Links available?}
        SELECT_LINKS["Weighted link selection"]
        FETCH_LINKS["Fetch selected links<br/>(with delays)"]
        LOG_CLICK["Log click success"]
        SKIP_CLICK["Skip click simulation"]
    end
    
    DONE([Job Complete - ACK])
    
    START --> CHK_OPEN
    CHK_OPEN -->|random < rate| FIND_PIXEL
    CHK_OPEN -->|random >= rate| SKIP_OPEN
    FIND_PIXEL --> CHK_PIXEL
    CHK_PIXEL -->|Yes| FETCH_PIXEL
    CHK_PIXEL -->|No| FETCH_RANDOM
    FETCH_PIXEL --> LOG_OPEN
    FETCH_RANDOM --> LOG_OPEN
    LOG_OPEN --> CHK_CLICK
    SKIP_OPEN --> CHK_CLICK
    
    CHK_CLICK -->|random < rate| EXTRACT_LINKS
    CHK_CLICK -->|random >= rate| SKIP_CLICK
    EXTRACT_LINKS --> FILTER_LINKS
    FILTER_LINKS --> CHK_LINKS
    CHK_LINKS -->|Yes| SELECT_LINKS
    CHK_LINKS -->|No| SKIP_CLICK
    SELECT_LINKS --> FETCH_LINKS
    FETCH_LINKS --> LOG_CLICK
    LOG_CLICK --> DONE
    SKIP_CLICK --> DONE
```

---

## HTML Override System

Diagram showing how HTML-based rate overrides work.

```mermaid
flowchart TD
    subgraph EmailHTML["Email HTML Content"]
        GLOBAL["&lt;div data-scope='global'<br/>data-open-rate='0.9'<br/>data-click-rate='0.5'&gt;"]
        LINK1["&lt;a href='...'<br/>data-click-rate='0.8'&gt;"]
        LINK2["&lt;a href='...'&gt;<br/>(no override)"]
    end
    
    subgraph Parser["HTML Parser"]
        PARSE_GLOBAL["find_global_open_rate()<br/>find_global_click_rate()"]
        PARSE_LINKS["extract_links_with_rates()"]
    end
    
    subgraph RateResolution["Rate Resolution"]
        OPEN_RATE["Open Rate"]
        CLICK_RATE["Click Rate"]
        LINK_RATES["Per-Link Rates"]
    end
    
    subgraph Defaults["Environment Defaults"]
        ENV_OPEN["SIMULATE_OPEN_PROBABILITY<br/>(default: 0.7)"]
        ENV_CLICK["SIMULATE_CLICK_PROBABILITY<br/>(default: 0.3)"]
    end
    
    GLOBAL --> PARSE_GLOBAL
    LINK1 --> PARSE_LINKS
    LINK2 --> PARSE_LINKS
    
    PARSE_GLOBAL --> OPEN_RATE
    PARSE_GLOBAL --> CLICK_RATE
    ENV_OPEN -.->|fallback| OPEN_RATE
    ENV_CLICK -.->|fallback| CLICK_RATE
    
    PARSE_LINKS --> LINK_RATES
    CLICK_RATE -.->|fallback for links<br/>without override| LINK_RATES
```

### SFMC Open Pixel Detection

```mermaid
flowchart TD
    START([HTML Content])
    SCAN["Scan all &lt;img src='...'&gt; tags"]
    
    CHK1{URL contains<br/>'cl.s4.exct.net/open.aspx'?}
    CHK2{URL contains<br/>'tracking.e360.salesforce.com/open'?}
    
    FOUND["Return SFMC Pixel URL"]
    FALLBACK["Return None<br/>(use random image)"]
    
    START --> SCAN
    SCAN --> CHK1
    CHK1 -->|Yes| FOUND
    CHK1 -->|No| CHK2
    CHK2 -->|Yes| FOUND
    CHK2 -->|No| FALLBACK
```

### SFMC Unsubscribe Link Filtering

```mermaid
flowchart TD
    LINK([Link URL])
    
    CHK_CLASSIC{Contains<br/>'cl.s4.exct.net/unsub_center.aspx'?}
    CHK_ADVANCED{Contains<br/>'tracking.e360.salesforce.com/unsubscribe'?}
    CHK_OVERRIDE{Has data-click-rate<br/>override?}
    
    INCLUDE["Include in click candidates"]
    EXCLUDE["Exclude from click candidates"]
    
    LINK --> CHK_CLASSIC
    CHK_CLASSIC -->|Yes| CHK_OVERRIDE
    CHK_CLASSIC -->|No| CHK_ADVANCED
    CHK_ADVANCED -->|Yes| CHK_OVERRIDE
    CHK_ADVANCED -->|No| INCLUDE
    CHK_OVERRIDE -->|Yes| INCLUDE
    CHK_OVERRIDE -->|No| EXCLUDE
```

---

## Component Architecture

Class diagram showing the internal structure of each Rust binary.

```mermaid
classDiagram
    direction TB
    
    class BobnetWeb {
        +main()
        +health_check()
        +cloudflare_webhook()
        +mailgun_webhook()
    }
    
    class BobnetProcessor {
        +main()
        +process_inbound_webhook()
        -parse_cloudflare()
        -parse_mailgun()
    }
    
    class BobnetWorker {
        +main()
        +process_simulator_job()
        -simulate_open()
        -simulate_clicks()
    }
    
    class Config {
        +cloudamqp_url: String
        +port: u16
        +cloudflare_auth_token: Option~String~
        +mailgun_signing_key: Option~String~
        +simulate_open_probability: f64
        +simulate_click_probability: f64
        +from_env() Config
    }
    
    class QueuePublisher {
        +channel: Channel
        +new() QueuePublisher
        +publish_inbound_webhook()
        +publish_simulator_job()
    }
    
    class HtmlParser {
        +extract_image_sources()
        +extract_links_with_rates()
        +find_sfmc_open_pixel()
        +find_global_open_rate()
        +find_global_click_rate()
    }
    
    class Clicker {
        +filter_links_with_rates()
        +choose_links_weighted()
        +perform_clicks()
        -is_unsubscribe_link()
    }
    
    class EmailParser {
        +parse_email()
        -extract_html_from_multipart()
        -extract_message_id()
    }
    
    class SignatureVerifier {
        +verify_mailgun_signature()
        +verify_cloudflare_auth()
    }
    
    BobnetWeb --> Config
    BobnetWeb --> QueuePublisher
    BobnetWeb --> SignatureVerifier
    
    BobnetProcessor --> Config
    BobnetProcessor --> QueuePublisher
    BobnetProcessor --> EmailParser
    BobnetProcessor --> HtmlParser
    
    BobnetWorker --> Config
    BobnetWorker --> HtmlParser
    BobnetWorker --> Clicker
```

---

## Deployment Architecture

Deployment diagram showing the Heroku infrastructure.

```mermaid
flowchart TB
    subgraph Internet["Internet"]
        CF["Cloudflare\nEmail Workers"]
        MG["Mailgun\nWebhooks"]
        TARGETS["External URLs\n(Open Pixels, Links)"]
    end
    
    subgraph Heroku["Heroku Platform"]
        subgraph WebDyno["Web Dyno"]
            WEB["bobnet-web\n:$PORT"]
        end
        
        subgraph ProcDyno["Processor Dyno"]
            PROC["bobnet-processor"]
        end
        
        subgraph WorkDyno["Worker Dyno"]
            WORK["bobnet-worker"]
        end
    end
    
    subgraph CloudAMQP["CloudAMQP Add-on"]
        Q1[("inbound_webhooks\nqueue")]
        Q2[("email_simulator\nqueue")]
    end
    
    CF -->|HTTPS| WEB
    MG -->|HTTPS| WEB
    WEB -->|AMQPS| Q1
    Q1 -->|AMQPS| PROC
    PROC -->|AMQPS| Q2
    Q2 -->|AMQPS| WORK
    WORK -->|HTTPS| TARGETS
```

### Procfile Configuration

```
web: ./rust-worker/target/release/bobnet-web
processor: ./rust-worker/target/release/bobnet-processor
rust-worker: ./rust-worker/target/release/bobnet-worker
```

### Environment Variables

```mermaid
flowchart LR
    subgraph Required["Required"]
        AMQP["CLOUDAMQP_URL"]
    end
    
    subgraph WebServer["Web Server"]
        PORT["PORT (8080)"]
        CF_TOKEN["CLOUDFLARE_AUTH_TOKEN"]
        MG_KEY["MAILGUN_SIGNING_KEY"]
        MG_DOMAIN["MAILGUN_DOMAIN"]
    end
    
    subgraph Worker["Worker"]
        OPEN_PROB["SIMULATE_OPEN_PROBABILITY (0.7)"]
        CLICK_PROB["SIMULATE_CLICK_PROBABILITY (0.3)"]
        MAX_CLICKS["MAX_CLICKS (2)"]
        OPEN_DELAY["OPEN_DELAY_RANGE_MS (500,5000)"]
        CLICK_DELAY["CLICK_DELAY_RANGE_MS (300,4000)"]
    end
```

---

## Performance Characteristics

```mermaid
xychart-beta
    title "Component Throughput (requests/second)"
    x-axis ["Web Server", "Processor", "Worker"]
    y-axis "Throughput" 0 --> 12000
    bar [10000, 5000, 100]
```

| Component | Throughput | Latency | Bottleneck |
|-----------|------------|---------|------------|
| Web Server | 10,000+ req/sec | Sub-millisecond | None (async I/O) |
| Processor | 5,000+ msg/sec | ~1ms per message | Email parsing |
| Worker | 100+ items/sec | Variable | External network I/O |
