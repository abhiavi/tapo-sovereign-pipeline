# Tapo KLAP Sovereign Pipeline

## Project Overview
This project completely automates the extraction, synchronization, and cloud-archival of 7 Tapo cameras running the encrypted KLAP firmware protocol (v1.5.0+). 

By reverse-engineering the Tapo Dual-Credential API, this system natively bypasses the `HTTP 401 Unauthorized` lockout on Port 8800 without relying on TP-Link's cloud subscriptions.

## 🏗️ Architecture Flow

```mermaid
graph TD
    %% Nodes
    cron[Systemd Timer \n 2:00 AM Daily]
    master[tapo_sync_manager.py \n on adraca-mini]
    
    subgraph Cameras [Tapo Hardware Nodes]
        cam1[Bedroom]
        cam2[Kitchen]
        cam3[Hall]
        cam4[Office]
        cam5[Outside Front]
        cam6[Outside Top]
        cam7[Backyard]
    end
    
    local_buffer[(/mnt/warehouse/tapo_buffer \n 7-Day Local Retention)]
    csv[metadata_index.csv \n Auto-Generated]
    obsidian[(ObsidianVault \n Daily_Sync_Logs.md)]
    
    gdrive[(Google Drive rclone \n 4.5TB Cold Storage)]

    %% Edges
    cron -->|Triggers| master
    master -->|Port 443: Local Auth \n Port 8800: Cloud Hash| Cameras
    Cameras -->|Raw .ts Video Chunks| master
    master -->|FFmpeg Transcode .mp4| local_buffer
    master -->|Generate Metrics| csv
    csv --> local_buffer
    
    master -->|rsync push| gdrive
    master -->|Daily Telemetry Report| obsidian
    master -->|Delete > 7 Days| local_buffer
    
    %% Styling
    style master fill:#f9f,stroke:#333,stroke-width:2px
    style local_buffer fill:#bbf,stroke:#333,stroke-width:2px
    style gdrive fill:#bfb,stroke:#333,stroke-width:2px
```

## Features
- **Dual-Credential Handshake:** Uses the Local Account (`admin`) for Port 443 control requests, and automatically injects the Master Cloud Password hash into the media request payload for Port 8800.
- **Sequential Execution:** Prevents hardware starvation on weak camera SoCs by iterating through the camera array synchronously.
- **Smart Retries:** 5-minute exponential backoff for offline nodes (max 3 retries).
- **Automated CSV Indexing:** Generates rich indexing metadata for future AI analysis (timestamps, file sizes, duration).
- **Hybrid Storage:** Maintains a 7-day fast local buffer while immediately pushing completed downloads to a massive Google Drive data lake.

## XDA Developers / Publishing Draft
For the full writeup, see the draft located at:
`/home/abhishek/.gemini/antigravity-cli/brain/5eb63b3c-b642-47f7-9c07-516dc5796e5b/Tapo_KLAP_XDA_Article.md`
