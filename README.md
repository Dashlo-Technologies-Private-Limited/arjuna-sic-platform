# ARJUNA: Autonomous Short Interval Control (SIC) Engine
> **Advanced Resource, Job, and Utility Navigation Algorithm**  
> Developed for **Hindustan Zinc Limited (HZL) AI Hackathon 2026**

---

## 🎯 Objective
Empower underground mine control rooms with real-time AI decision-making to recover production losses within the shift, accelerating metal productivity from **51T to 60T Metal/Person/Year**.

## ⚡ Key Features
- **Real-Time SIC Cockpit:** Plan vs. actual run-rate trajectory with dynamic recovery forecasting.
- **Dynamic Re-Dispatch Optimizer:** Mixed-Integer Linear Programming (MILP / Hungarian Algorithm) to resolve face starvation.
- **Bottleneck & Cycle State-Machine:** Continuous tracking through *Drilling → Charging → Fume Clearing → Mucking → Bolting*.
- **Automated Escalation Matrix:** Automated 3-tier routing (Shift Foreman → Mining Planning Engineer → Mine Superintendent).
- **Shift-Aware Authentication:** Built-in auto-detection for HZL 3-shift rotation (Shift A, Shift B, Shift C).

## 🚀 Quickstart

### 1. Clone the repository
```bash
git clone [https://github.com/](https://github.com/)<YOUR_USERNAME>/arjuna-sic-hzl.git
cd arjuna-sic-hzl