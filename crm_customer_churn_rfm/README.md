# CRM Customer Churn RFM

**Version:** 18.0.1.0.0 · **Author:** TwenTIC · **License:** LGPL-3

## Overview

This module extends Odoo's standard contact/customer management with an **RFM (Recency, Frequency, Monetary)** health-score engine designed to detect and prevent customer churn before it happens.

It adds three computed fields to `res.partner`, a daily scheduled action that keeps them up to date, and enriched list/kanban/form views that let the sales team identify at-risk customers at a glance.

---

## How it fits into the Odoo circuit

```
account.move (posted invoices)
        │
        ▼
res.partner ──► x_rfm_score (0–100 %)
                x_last_purchase_date
                x_purchase_frequency
        │
        │  score < 40 %?
        ▼
mail.activity ──► assigned to partner's salesperson
                  (deadline: T + 3 days)
```

The module **reads** invoice data from `account.move` and **writes** health metrics back onto the partner record. It creates `mail.activity` tasks automatically so no manual monitoring is needed.

---

## Fields added to res.partner

| Field | Type | Description |
|---|---|---|
| `x_rfm_score` | Float (%) | Combined health score 0–100. Coloured red/orange/green. |
| `x_last_purchase_date` | Date | Date of the most recent posted invoice. |
| `x_purchase_frequency` | Float (days) | Average days between consecutive posted invoices. |

---

## Scoring algorithm

Only partners with **≥ 3 posted invoices** are scored (fewer data points are statistically unreliable).

### Recency score (weight 60 %)

| Condition | Score |
|---|---|
| `days_since_last_purchase ≤ frequency` | 100 % |
| `frequency < days_since ≤ 2 × frequency` | Linear decay 100 → 50 % |
| `days_since > 2 × frequency` | Continues to 0 % |

### Monetary score (weight 40 %)

Compares the average of the **last 2 invoices** against the **overall average**:

```
monetary_score = (last_two_avg / overall_avg) × 100
```

An informational log warning is emitted when the last-2 average drops **≥ 40 %** below the historical average.

### Combined score

```
rfm_score = (0.60 × recency_score) + (0.40 × monetary_score)
```

---

## Automated action: daily cron

A **daily scheduled action** (`ir.cron`) queries all partners with `customer_rank > 0` and recomputes their scores.

**When a score drops below 40 %**, the cron automatically:

1. Checks whether an open RFM activity already exists for that partner.
2. If not, creates a `mail.activity` of type *To-Do* assigned to the partner's salesperson (or the current user if none is set).
3. Sets a deadline of **3 days from today**.

The activity summary is `RFM Alert: At-Risk Customer` and the note contains the current score, last purchase date, and average frequency.

---

## Views and UI

### List view (Contacts)

Inherits `base.view_partner_list` and adds:

- **RFM Score (%)** column — `optional="show"` (visible by default, can be hidden).
- **Last Purchase** column — `optional="show"`.
- Row-level colour coding via `decoration-*` attributes:
  - 🔴 **Red** — score < 40 % (at risk)
  - 🟠 **Orange** — score 40–70 % (needs attention)
  - 🟢 **Green** — score ≥ 70 % (healthy)

### Kanban view (Contacts)

Inherits `base.res_partner_kanban_view` and adds a **coloured pill badge** in the card footer showing the RFM score with the same traffic-light colour scheme (Bootstrap `text-bg-danger / warning / success`). The badge is only shown for partners with `customer_rank > 0` and a score > 0.

### Form view (Partner)

Inherits `base.view_partner_form` and adds:

- A **smart button** in the button box (visible only for customers) that shows the current RFM score and triggers a manual recomputation when clicked.
- An **RFM Analysis** tab on the Sales & Purchases page with the three metric fields.

### Search view (Contacts)

Inherits `base.view_res_partner_filter` and adds three predefined filters:

| Filter name | Domain |
|---|---|
| **At-Risk Customers** | `x_rfm_score > 0 AND x_rfm_score < 40` |
| **Customers Needing Attention** | `x_rfm_score >= 40 AND x_rfm_score < 70` |
| **Healthy Customers** | `x_rfm_score >= 70` |

Plus a **Group By → RFM Health Band** option.

---

## Translations

The module ships `.po` files for:

| Language | Code |
|---|---|
| Spanish | `es` |
| Catalan | `ca` |
| German | `de` |
| French | `fr` |
| Portuguese | `pt` |
| Italian | `it` |

---

## Dependencies

| Module | Reason |
|---|---|
| `base` | `res.partner` model |
| `mail` | `mail.activity` creation |
| `account` | `account.move` (posted invoices) |
| `sale` | `customer_rank` field on partner |

---

## Manual user guide

### 1. Installation

Install the module from **Apps** → search for *CRM Customer Churn RFM* → **Install**.

### 2. Viewing scores in the list

Go to **Contacts** (or **Sales → Customers**). The **RFM Score (%)** column is shown by default. Rows are colour-coded:

- **Red text** → score < 40 % — the customer is at risk and a follow-up activity has been (or will be) created automatically.
- **Orange text** → score 40–70 % — the customer needs monitoring.
- **Green text** → score ≥ 70 % — the customer is healthy.

If the column is not visible, click the optional-columns icon (⚙ at the right of the column header row) and enable **RFM Score (%)**.

### 3. Filtering at-risk customers

In the search bar, click **Filters → At-Risk Customers** to show only partners whose score is below 40 %. Use **Customers Needing Attention** or **Healthy Customers** for the other bands.

### 4. Viewing the score on the partner form

Open any customer record. A **heartbeat smart button** at the top shows the current RFM score. Click it to **recompute the score immediately** (useful after manually verifying invoice history).

The **RFM Analysis** tab (next to *Sales & Purchases*) shows all three metrics in detail.

### 5. Viewing the kanban badge

Switch to the **Kanban** view of Contacts. Each customer card displays a coloured pill badge at the bottom showing the score. The colour follows the same red/orange/green logic.

### 6. Handling RFM activities

When a customer falls below 40 %, an automatic **To-Do activity** appears in the chatter of the partner record and in the salesperson's activity feed (**Sales → Activities**). The activity note explains the score drop and suggests proactive contact. Once the follow-up is done, mark the activity as **Done** in the standard Odoo way.

### 7. Scheduled action

The cron runs **once per day** automatically. To run it manually:

**Settings → Technical → Automation → Scheduled Actions** → search for *CRM Churn RFM: Compute Customer Health Scores* → **Run Manually**.

You can also adjust the interval (e.g. to every 12 hours) directly in the scheduled action form.

### 8. Score is 0 for a customer — why?

A score of 0 means the partner either:

- Has **fewer than 3 posted invoices** (minimum required for a statistically meaningful score), or
- Has `customer_rank = 0` (not flagged as a customer in Odoo).

Once the customer has at least 3 confirmed invoices, the next cron run will populate the score.
