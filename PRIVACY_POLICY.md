# Privacy and Data Handling Policy

**Application:** Agent Helper
**Environment:** Internal Corporate Use Only
**Effective Date:** 4/28/2026

## 1. Introduction
The Agent Helper application is an internal productivity tool designed to assist call center agents in classifying customer issues, extracting vetting details, and generating resolution workflows. This Privacy Policy outlines how the App interacts with, processes, and stores data on corporate-managed machines.

## 2. Data Processing & Locality (Offline-First Architecture)
Agent Helper operates on a strictly offline-first architecture.
* **Zero External Transmission:** The App does not transmit, upload, or sync customer data, vetting details, or interaction logs to any external servers, cloud databases, or third-party analytics services.
* **Local Storage:** All configuration data, user-saved guidance notes, and temporary session data are stored locally in human-readable JSON files within the App's installation directory on the host machine.

## 3. Handling of Customer Data (PII & Financial Data)
The App is designed to process Personally Identifiable Information (PII) and sensitive financial data (e.g., ID numbers, transaction codes, M-PESA balances, Skiza/PRS codes) strictly for the duration of an active support call.
* **Temporary Extraction:** Data extracted from customer notes via the clipboard is held in the machine's active memory (RAM) and local temporary state to generate interaction outputs.
* **Data Clearing:** The App is designed to clear active session data (vetting inputs and interaction text) immediately when the agent switches to a new issue category or resets the view.

## 4. System Access & Permissions
To function as an automated productivity tool, the App requires specific system-level permissions:
* **Clipboard Access:** The App reads the system clipboard to automatically extract vetting details and writes to the clipboard to provide agents with prepared resolution snippets.
* **Keyboard Monitoring (Hotkeys):** The App temporarily monitors keyboard inputs (e.g., typing specific SLA numbers) solely to trigger localized auto-fill workflows (e.g., Reversal automation). Keyboard monitoring is strictly contextual and does not log keystrokes to any persistent file.

## 5. Network Activity & Updates
The App operates entirely offline and does not generate independent network traffic or connect to external APIs. Updates and version control are managed exclusively through the secure, native infrastructure of the Microsoft Store. The App itself does not initiate any external download requests, and no user, machine, or customer data is transmitted to facilitate updates. All application updates are governed by the host machine's Microsoft Store deployment policies.

## 6. Corporate Compliance & User Responsibility
Agent Helper is a localized processor meant to work alongside the company's authorized CRM systems.
* Agents using this App remain bound by the company's overarching Data Protection Policies, IT Security Guidelines, and any applicable regional data protection laws.
* Agents must not manually export, backup, or share the App's internal `history.json` or `favorites.json` files outside of the corporate-controlled environment.

## 7. Modifications to the App
Any user-generated modifications, including adding custom issues, snippets, or guidance notes via the App's editing interface, remain on the local machine and are subject to the same local-only storage protocols defined above.
