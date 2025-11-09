# 🗓️ SYSTEM FLOWCHART: AI-Powered Schedule Generation with Feedback Loop

## 📊 Общая архитектура системы

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SCHEDULE GENERATION SYSTEM                          │
│                     (AI-Powered with Feedback Learning)                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 QUICK OVERVIEW (Simplified Flow)

```
┌──────────────┐
│  1. LOAD     │  ← shiftWeeks_24w.csv, employees, historical shiftDetails
│   DATA       │
└──────┬───────┘
       │
       ↓
┌──────────────┐
│  2. GENERATE │  ← CP-SAT AI Scheduler
│  SCHEDULE    │     (maximize skill match, fairness)
└──────┬───────┘
       │
       ↓
┌──────────────┐
│  3. EXPORT   │  → shiftDetails_24w.csv (skill points = EMPTY)
│   TO CSV     │     (goes to frontend/backend)
└──────┬───────┘
       │
       ↓
┌──────────────┐
│  4. EXECUTE  │  ← Employee works shift
│   SHIFTS     │
└──────┬───────┘
       │
       ↓
┌──────────────┐
│  5. FEEDBACK │  ← Manager submits: rating + comment + tags
│  COLLECTION  │     → Saved to Feedback table (DB)
└──────┬───────┘
       │
       ↓
┌──────────────┐
│  6. UPDATE   │  ← Update skill points in shiftDetails_24w.csv
│ SKILL POINTS │     (manual OR ML-assisted OR automated)
└──────┬───────┘
       │
       ↓
┌──────────────┐
│  7. AVERAGE  │  ← Recalculate employee average skills
│   SKILLS     │     → Update Employee table (base skills)
└──────┬───────┘
       │
       ↓
       └─────→ BACK TO STEP 2 (next week)
```

---

## 🔄 MAIN FLOW (Detailed)

### 1️⃣ INITIALIZATION & DATA PREPARATION
```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Data Loading                                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  📁 shiftWeeks_24w.csv                                      │
│     └─> Load into DB: Shift table                           │
│         (id, date, week_id)                                 │
│                                                              │
│  👥 employees_id.csv                                        │
│     └─> Load into DB: Employee table                        │
│         (employee_id, name, role, base_skills)              │
│                                                              │
│  📋 shiftDetails_24w.csv (HISTORICAL)                       │
│     └─> Load historical skill points                        │
│         └─> Calculate AVERAGE skills per employee           │
│             └─> Update Employee base skills                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
```

### 2️⃣ SCHEDULE GENERATION (CP-SAT)
```
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: AI Schedule Generation                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  🤖 CP-SAT Scheduler                                         │
│     ├─> Input:                                              │
│     │   • Shifts for week (from Shift table)               │
│     │   • Employees with average skills                     │
│     │   • Requirements (config.yaml)                        │
│     │                                                       │
│     ├─> Constraints:                                        │
│     │   • Role compatibility                                │
│     │   • One shift per day per employee                    │
│     │   • Coverage requirements                             │
│     │   • Hours fairness                                    │
│     │                                                       │
│     ├─> Objective:                                          │
│     │   • MAXIMIZE skill match                              │
│     │   • MINIMIZE hours deviation                          │
│     │                                                       │
│     └─> Output:                                             │
│         • List of Assignments                               │
│           (shift_id, emp_id, start_time, end_time, role)    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
```

### 3️⃣ EXPORT TO CSV (WITH EMPTY SKILL POINTS)
```
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Export Schedule to shiftDetails_24w.csv             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  📝 Format:                                                  │
│     shift_id, emp_id, start_time, end_time,                 │
│     coffee_rating, sandwich_rating,                         │
│     customer_service_rating, speed_rating,                  │
│     present, role                                            │
│                                                              │
│  ⚠️ IMPORTANT:                                               │
│     • Skill points columns = EMPTY/NULL                     │
│     • present = True (default)                              │
│     • This CSV goes to FRONTEND/BACKEND                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
                    ┌─────────┐
                    │ FRONTEND│
                    │ DISPLAY │
                    └─────────┘
```

### 4️⃣ SCHEDULE EXECUTION & FEEDBACK COLLECTION
```
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: During & After Shift Execution                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  📅 SHIFT DAY                                                │
│     ├─> Employee works assigned shift                       │
│     └─> Manager observes performance                        │
│                                                              │
│  ⏰ AFTER SHIFT ENDS                                         │
│     └─> Manager submits FEEDBACK:                           │
│         ├─> overall_service_rating (1-5)                    │
│         ├─> traffic_level (quiet/normal/busy)               │
│         ├─> comment (text)                                  │
│         ├─> tags (keywords)                                 │
│         └─> present (was employee present?)                 │
│                                                              │
│  💾 Save to:                                                 │
│     └─> Feedback table in DB                                │
│         (shift_id, emp_id, rating, comment, tags, etc.)     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
```

### 5️⃣ SKILL POINTS UPDATE (based on Feedback)
```
┌─────────────────────────────────────────────────────────────┐
│ STEP 5: Update Skill Points in shiftDetails_24w.csv         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  🔄 UPDATE PROCESS                                           │
│                                                              │
│  Option A: MANUAL (начальный этап)                          │
│     └─> Manager directly edits shiftDetails_24w.csv         │
│         └─> Updates: coffee_rating, sandwich_rating, etc.   │
│                                                              │
│  Option B: SEMI-AUTOMATED (ML-assisted)                     │
│     ├─> ML Model predicts skill points from feedback:       │
│     │   • Input: Feedback (rating, comment, tags)           │
│     │   • Output: Predicted skill points                    │
│     │                                                       │
│     └─> Manager reviews & approves                          │
│         └─> Updates shiftDetails_24w.csv                    │
│                                                              │
│  Option C: FULLY AUTOMATED (будущее)                        │
│     └─> ML Model automatically updates skill points         │
│         └─> Based on feedback + historical patterns         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
```

### 6️⃣ SKILL AVERAGING & LEARNING
```
┌─────────────────────────────────────────────────────────────┐
│ STEP 6: Recalculate Average Skills                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  📊 SKILL AVERAGING MODULE                                   │
│                                                              │
│  ┌──────────────────────────────────────────┐              │
│  │ Load: shiftDetails_24w.csv               │              │
│  │  (with updated skill points)             │              │
│  └──────────────────────────────────────────┘              │
│              ↓                                               │
│  ┌──────────────────────────────────────────┐              │
│  │ Group by: employee_id                    │              │
│  │ Calculate:                               │              │
│  │  • Average coffee_rating                 │              │
│  │  • Average sandwich_rating               │              │
│  │  • Average customer_service_rating       │              │
│  │  • Average speed_rating                  │              │
│  └──────────────────────────────────────────┘              │
│              ↓                                               │
│  ┌──────────────────────────────────────────┐              │
│  │ Update: Employee table                   │              │
│  │  (base skills = averaged from history)   │              │
│  └──────────────────────────────────────────┘              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
                    ┌──────────┐
                    │ NEXT     │
                    │ WEEK     │
                    └──────────┘
                          ↓
                    (Back to STEP 2)
```

---

## 📋 DETAILED DATA FLOW

### CSV Files Structure

#### 📁 shiftWeeks_24w.csv
```
id,date,week_id
1000,2025-09-01,2025-W36
1001,2025-09-02,2025-W36
...
1167,2026-02-15,2026-W07
```
**Purpose**: Master list of all shifts (24 weeks coverage)  
**Updates**: Rarely (only when adding new weeks)

---

#### 📁 shiftDetails_24w.csv (MASTER FILE)
```
shift_id,emp_id,start_time,end_time,coffee_rating,sandwich_rating,
customer_service_rating,speed_rating,present,role

1000,1001,2025-09-01T07:00:00,2025-09-01T15:00:00,,,,,
True,MANAGER

1000,1003,2025-09-01T07:00:00,2025-09-01T15:00:00,50,,76,80,True,WAITER
...
```

**Purpose**: 
- Complete schedule + performance data
- Source of truth for assignments AND skill points

**Lifecycle**:
1. **Initial state**: Generated by CP-SAT, skill points = EMPTY
2. **After feedback**: Updated with skill points from manager/ML
3. **Historical data**: Used to calculate averages for next generation

**Updates**:
- **Frequency**: After each shift (when feedback is submitted)
- **Who updates**: Manager (manually) or ML model (automated)
- **Trigger**: Feedback submission

---

#### 📁 Feedback (Database Table, future: CSV export)
```
id,week_id,date,shift_id,emp_id,role,
overall_service_rating,traffic_level,comment,tags,
submitted_at

1,2025-W36,2025-09-01,1000,1003,WAITER,
5,normal,"Отлично работает с клиентами",communication;speed,
2025-09-01T16:00:00
...
```

**Purpose**: Raw feedback data from managers  
**Updates**: After each shift (when manager submits)

---

## 🔁 FEEDBACK LOOP ARCHITECTURE

```
                    ┌─────────────────────┐
                    │  GENERATE SCHEDULE  │
                    │   (CP-SAT AI)       │
                    └──────────┬──────────┘
                               │
                               ↓
                    ┌─────────────────────┐
                    │  Export to CSV      │
                    │  (skill points =    │
                    │   EMPTY)            │
                    └──────────┬──────────┘
                               │
                               ↓
                    ┌─────────────────────┐
                    │  Shift Execution    │
                    │  (Employee works)   │
                    └──────────┬──────────┘
                               │
                               ↓
                    ┌─────────────────────┐
                    │  Manager Feedback   │
                    │  (Rating + Comment) │
                    └──────────┬──────────┘
                               │
                               ↓
                    ┌─────────────────────┐
                    │  Update Skill Points│
                    │  (in shiftDetails)  │
                    └──────────┬──────────┘
                               │
                               ↓
                    ┌─────────────────────┐
                    │  Recalculate        │
                    │  Average Skills     │
                    └──────────┬──────────┘
                               │
                               ↓
                    ┌─────────────────────┐
                    │  Update Employee    │
                    │  Base Skills        │
                    └──────────┬──────────┘
                               │
                               │
                               └─────────┐
                                         │
                               (Loop back to generation)
```

---

## 🤖 ML INTEGRATION POINTS

### Current State (Phase 1):
- ✅ CP-SAT for schedule generation
- ✅ Historical skill averaging
- ⏳ Feedback collection (to be implemented)
- ⏳ ML model for skill prediction (future)

### Future Enhancement (Phase 2):
```
┌─────────────────────────────────────────────────────────────┐
│ ML MODEL: Feedback → Skill Points Prediction                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input Features:                                             │
│    • overall_service_rating (1-5)                           │
│    • traffic_level (one-hot encoded)                        │
│    • comment (text embedding via sentence-transformers)      │
│    • tags (keywords)                                        │
│    • employee_id (embedding)                                │
│    • shift context (day_of_week, time, etc.)                │
│                                                              │
│  Output:                                                     │
│    • Predicted coffee_rating (20-100)                       │
│    • Predicted sandwich_rating (20-100)                     │
│    • Predicted customer_service_rating (20-100)             │
│    • Predicted speed_rating (20-100)                        │
│                                                              │
│  Model Type:                                                 │
│    • Gradient Boosting (XGBoost/LightGBM)                   │
│    • Or Neural Network with text embeddings                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 KEY DECISIONS & NOTES

### 1. Skill Points Storage
- **Where**: `shiftDetails_24w.csv` (NOT in Employee table)
- **Why**: Skill points vary per shift (same employee can perform differently)
- **Employee.base_skills**: Average/aggregated from historical shifts

### 2. Feedback Collection
- **Storage**: Database table `Feedback`
- **Export**: Optional CSV export for analysis
- **Trigger**: After shift ends (manager submits)

### 3. Update Frequency
- **Skill points**: Updated after EACH shift (when feedback submitted)
- **Employee averages**: Recalculated weekly (before next schedule generation)
- **Schedule**: Generated weekly (using latest averages)

### 4. Data Consistency
- **shiftDetails_24w.csv** = Single source of truth for assignments + performance
- **Feedback table** = Raw feedback data (audit trail)
- **Employee table** = Aggregated skills (for scheduling)

---

## 🚀 IMPLEMENTATION PHASES

### Phase 1: Current State ✅
- [x] CP-SAT scheduler
- [x] Historical skill loading
- [x] CSV export/import
- [ ] Feedback collection UI/API (TO DO)

### Phase 2: Feedback Integration
- [ ] Feedback collection module
- [ ] Manual skill points update in CSV
- [ ] Recalculation of averages
- [ ] Integration with CP-SAT (use updated averages)

### Phase 3: ML Enhancement
- [ ] Text preprocessing for comments
- [ ] ML model training (feedback → skill points)
- [ ] Automated skill points prediction
- [ ] Continuous learning loop

---

## ❓ QUESTIONS TO CLARIFY

1. **Skill Points Update Method**:
   - A) Manager directly edits CSV?
   - B) Manager fills feedback → ML predicts → Manager approves?
   - C) Fully automated ML updates?

2. **Feedback Collection Interface**:
   - Web form?
   - Mobile app?
   - CSV import?
   - API endpoint?

3. **Update Frequency**:
   - Real-time updates after each shift?
   - Batch updates daily/weekly?

4. **Historical Data Handling**:
   - Keep all historical shiftDetails?
   - Archive old data?
   - Sliding window for averaging?

---

*Created: 2025-01-XX*  
*Version: 1.0*
