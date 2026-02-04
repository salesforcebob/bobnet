# BobNet Architecture Diagrams

## System Overview

```mermaid
flowchart TB
    subgraph External ["External Email Providers"]
        CF[("Cloudflare\nEmail Workers")]
        MG[("Mailgun\nInbound Routes")]
    end

    subgraph BobNet ["BobNet System"]
        subgraph Web ["Web Server (bobnet-web)"]
            W1["/webhooks/cloudflare"]
            W2["/webhooks/mailgun"]
            AUTH["Auth Verification"]
        end

        subgraph Queues ["RabbitMQ (CloudAMQP)"]
            Q1[("inbound_webhooks\n(raw payloads)")]
            Q2[("email_simulator\n(parsed jobs)")]
        end

        subgraph Processor ["Processor (bobnet-processor)"]
            P1["RFC 5322 Parser"]
            P2["Message-Id Extractor"]
            P3["HTML Extractor"]
        end

        subgraph Worker ["Worker (bobnet-worker)"]
            S1["Open Simulator"]
            S2["Click Simulator"]
        end
    end

    subgraph Targets ["Marketing Cloud Tracking"]
        PIXEL[("Open Pixels\ncl.s4.exct.net")]
        LINKS[("Click Tracking\nLinks")]
    end

    CF -->|JSON + X-Custom-Auth| W1
    MG -->|Form + HMAC Signature| W2
    W1 --> AUTH
    W2 --> AUTH
    AUTH -->|Raw Payload| Q1
    Q1 --> Processor
    P1 --> P2
    P2 --> P3
    P3 -->|SimulatorJob| Q2
    Q2 --> Worker
    S1 -->|Fetch Pixels| PIXEL
    S2 -->|Click Links| LINKS
```

## Request Flow

```mermaid
sequenceDiagram
    participant Email as Inbound Email
    participant CF as Cloudflare Worker
    participant Web as bobnet-web
    participant Q1 as inbound_webhooks
    participant Proc as bobnet-processor
    participant Q2 as email_simulator
    participant Work as bobnet-worker
    participant MC as Marketing Cloud

    Email->>CF: Receive Email
    CF->>Web: POST /webhooks/cloudflare
    Note over Web: Verify X-Custom-Auth
    Web->>Q1: Enqueue Raw Payload
    Web-->>CF: 200 OK (microseconds)
    
    Q1->>Proc: Consume Message
    Note over Proc: Parse RFC 5322<br/>Extract Message-Id<br/>Extract HTML
    Proc->>Q2: Publish SimulatorJob
    
    Q2->>Work: Consume Job
    Note over Work: Random Delay
    
    alt Open Simulation (probability check)
        Work->>MC: Fetch Open Pixel
        MC-->>Work: 200 OK
    end
    
    alt Click Simulation (probability check)
        Work->>MC: Click Tracking Link
        MC-->>Work: 302 Redirect
    end
```

## Queue Message Types

```mermaid
classDiagram
    class InboundWebhook {
        <<enum>>
        +Mailgun(MailgunRawPayload)
        +Cloudflare(CloudflareRawPayload)
    }
    
    class MailgunRawPayload {
        +String recipient
        +String sender
        +String subject
        +Option~String~ body_html
        +Option~String~ message_headers
        +String timestamp
        +String token
    }
    
    class CloudflareRawPayload {
        +String from_field
        +String to
        +String subject
        +String timestamp
        +String raw_content
    }
    
    class SimulatorJob {
        +String message_id
        +String to
        +Option~String~ html
    }
    
    InboundWebhook --> MailgunRawPayload
    InboundWebhook --> CloudflareRawPayload
    InboundWebhook ..> SimulatorJob : "processed into"
```

## Simulation Decision Flow

```mermaid
flowchart TD
    START([Receive SimulatorJob]) --> DELAY["Random Delay\n(500-5000ms)"]
    
    DELAY --> CHECK_OPEN{"Check Open Rate\n(global or per-email)"}
    CHECK_OPEN -->|"roll < probability"| FIND_PIXEL["Find Open Pixel"]
    CHECK_OPEN -->|"roll >= probability"| CHECK_CLICK
    
    FIND_PIXEL --> EXCT{"ExactTarget Pixel\nFound?"}
    EXCT -->|Yes| FETCH_EXCT["Fetch cl.s4.exct.net\nopen.aspx"]
    EXCT -->|No| FETCH_IMG["Fetch Other Images"]
    FETCH_EXCT --> CHECK_CLICK
    FETCH_IMG --> CHECK_CLICK
    
    CHECK_CLICK{"Check Click Rate\n(global or per-email)"}
    CHECK_CLICK -->|"roll < probability"| EXTRACT_LINKS["Extract Links\nwith Rates"]
    CHECK_CLICK -->|"roll >= probability"| DONE
    
    EXTRACT_LINKS --> FILTER["Filter Links\n- Domain allow/deny\n- Remove unsub links*"]
    FILTER --> WEIGHT["Weighted Selection\n(by data-click-rate)"]
    WEIGHT --> CLICK["Click Links\nwith Random Delays"]
    CLICK --> DONE([Complete])
    
    style FILTER fill:#f9f,stroke:#333
```

## HTML Override System

```mermaid
flowchart LR
    subgraph HTML ["Email HTML Content"]
        DIV["&lt;div data-scope='global'\ndata-open-rate='0.9'\ndata-click-rate='0.5'&gt;"]
        LINK1["&lt;a href='...' data-click-rate='0.8'&gt;"]
        LINK2["&lt;a href='...'&gt;"]
        UNSUB["&lt;a href='unsub_center.aspx'&gt;"]
    end
    
    subgraph Rates ["Effective Rates"]
        OPEN_RATE["Open: 0.9\n(from div)"]
        CLICK_RATE["Global Click: 0.5\n(from div)"]
        L1_RATE["Link1: 0.8\n(override)"]
        L2_RATE["Link2: 0.5\n(global)"]
        UNSUB_RATE["Unsub: FILTERED\n(no override)"]
    end
    
    DIV --> OPEN_RATE
    DIV --> CLICK_RATE
    LINK1 --> L1_RATE
    LINK2 --> L2_RATE
    UNSUB --> UNSUB_RATE
    
    style UNSUB_RATE fill:#f66,stroke:#333
```

## Component Architecture

```mermaid
graph TB
    subgraph "bobnet-web (Axum)"
        WEB_MAIN["main()"] --> ROUTER["Router"]
        ROUTER --> HEALTH["/health"]
        ROUTER --> MG_HANDLER["/webhooks/mailgun"]
        ROUTER --> CF_HANDLER["/webhooks/cloudflare"]
        MG_HANDLER --> SIG_VERIFY["HMAC-SHA256\nVerification"]
        CF_HANDLER --> AUTH_VERIFY["X-Custom-Auth\nVerification"]
        SIG_VERIFY --> PUBLISHER["Publisher"]
        AUTH_VERIFY --> PUBLISHER
    end
    
    subgraph "bobnet-processor (Tokio)"
        PROC_MAIN["main()"] --> CONSUMER["RabbitMQ Consumer"]
        CONSUMER --> PARSE["process_webhook()"]
        PARSE --> MG_PROC["process_mailgun()"]
        PARSE --> CF_PROC["process_cloudflare()"]
        CF_PROC --> EMAIL_PARSE["mailparse\nRFC 5322"]
        MG_PROC --> PUB2["Publisher"]
        EMAIL_PARSE --> PUB2
    end
    
    subgraph "bobnet-worker (Tokio)"
        WORK_MAIN["main()"] --> WORK_CONSUMER["RabbitMQ Consumer"]
        WORK_CONSUMER --> PROCESS["process_job()"]
        PROCESS --> OPENER["simulate_open()"]
        PROCESS --> CLICKER["perform_clicks()"]
        OPENER --> HTTP["reqwest\nHTTP Client"]
        CLICKER --> HTTP
    end
    
    PUBLISHER -.->|"inbound_webhooks"| CONSUMER
    PUB2 -.->|"email_simulator"| WORK_CONSUMER
```

## Deployment Architecture (Heroku)

```mermaid
flowchart TB
    subgraph Heroku ["Heroku Platform"]
        subgraph Dynos ["Dyno Formation"]
            WEB_DYNO["web dyno\nbobnet-web"]
            PROC_DYNO["processor dyno\nbobnet-processor"]
            WORK_DYNO["rust-worker dyno\nbobnet-worker"]
        end
    end
    
    subgraph CloudAMQP ["CloudAMQP"]
        RABBIT[("RabbitMQ\nCluster")]
    end
    
    subgraph Internet ["Internet"]
        CF_WORKER["Cloudflare\nEmail Worker"]
        MG_ROUTE["Mailgun\nInbound Route"]
    end
    
    CF_WORKER -->|HTTPS| WEB_DYNO
    MG_ROUTE -->|HTTPS| WEB_DYNO
    WEB_DYNO <-->|AMQPS| RABBIT
    PROC_DYNO <-->|AMQPS| RABBIT
    WORK_DYNO <-->|AMQPS| RABBIT
```

---

*Generated for BobNet Email Simulator - High-performance email simulation system*
