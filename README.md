# Urban Air Quality Assistant

**PromptWars Virtual, Challenge 6 (Hack2Skill)**

A GenAI-powered assistant that helps families and communities navigate severe
winter smog and urban air pollution. The application suggests low-emission
daily routines, indoor air quality hacks, and sustainable alternatives
tailored to a family's location and lifestyle, while clearly explaining the
direct impact of their choices.

> Apps show data. Families need decisions.

---

## Chosen vertical

**Urban Air Quality Assistant (Challenge 6).**

### Persona

The Sharma family, Delhi NCR, November. Rohit (38) rides a two-wheeler to
work. Neha (35) works from home. Aarav (7) has outdoor PT at school. Dadi
(68) has asthma and walks at 6 am. Every morning they see an AQI like
"412 - Severe" and need a DECISION for each person, in plain words, within
their budget, with proof it helps. They do not need another number.

### Core problem

Apps show data, families need decisions. Decisions conflict (child vs
grandmother vs commuter), money is limited (often one purifier), and nobody
explains why a choice helps.

The three decisions that actually conflict on a Severe day are:

| Person | The decision | Why it is hard |
| --- | --- | --- |
| Aarav (7) | Outdoor PT at school | A child outdoors on a Severe day is the worst exposure in the house |
| Dadi (68, asthma) | Her 6 am walk | The coolest hour is usually the dirtiest hour, and she reacts to smoke |
| Rohit (38) | The two-wheeler ride | The trip itself is exposure, and the family often has money for only one purifier |

A single "AQI 412" number resolves none of these. The plan below resolves
all three, says which one wins when they conflict, and says why.

---

## Approach and logic

**The rules engine decides. The language model only explains.**

The central design decision is that a generative model is not trusted to make
the decisions. A model asked "what should a Delhi family do at AQI 412" can
confidently contradict itself between runs, invent a statistic, or forget the
grandmother with asthma. So the decision-making is deterministic and
inspectable, and the model, when it is added in Phase 2, only rewrites the
wording and adds a tone appropriate to the household. The rules output is
passed to the model as grounded input, never the other way around.

The consequence: **the application is fully useful with no API key and no
network access.** Phase 2 adds personalisation on top of a plan that is
already correct, and if the model call fails or no key is set, the app shows
the rule-based plan with a clearly labelled notice.

### The decision logic, step by step

1. **Read the air.** The numeric AQI is validated and mapped to a CPCB band.
   Out-of-range and non-numeric readings are rejected with clear errors.
2. **Read the household.** City, members, sensitivity, commute mode, home
   type and budget are validated once, up front.
3. **Set the strictness.** The band sets a baseline. A household containing a
   child, an older adult, or someone with asthma is guided **one step
   stricter** from the Moderate band upward, because the same air is a
   different problem for them.
4. **Evaluate the rule table.** Every recommendation is a row in a table with
   its own condition, wording, cost tier and benefit score. Member rules are
   evaluated per person, household rules once.
5. **Resolve conflicts.** When a rule that speaks for a vulnerable member
   applies, it **replaces** the softer household-wide advice rather than
   sitting beside it. The plan records what was replaced.
6. **Fit the budget.** Actions are ranked by benefit per rupee and bought in
   that order, with steps that protect the most vulnerable person considered
   first.
7. **Explain each step.** Every action carries a plain-language impact line
   and the assumption it rests on.

### Why the vulnerable member wins

This is the behaviour the whole product turns on, so it is enforced by the
engine and covered by tests rather than left to chance.

- At **AQI 250 (Poor)**, a household of healthy adults gets `STRICT` advice:
  *"Ventilate only in the cleanest hour."*
- At **AQI 250 (Poor)**, the same household plus Dadi (asthma) is bumped to
  `SEVERE` advice, and the household ventilation line is **removed**. What
  remains is Dadi's own instruction to keep her room windows shut, because
  her advice is stricter than the general advice.

`tests/test_rules.py` asserts both halves of this: the softer advice is
present without a vulnerable member, absent with one, and the replacing
action records which advice it replaced.

### What is deliberately not in the plan

- **No invented statistics.** There are no percentages, no particle counts,
  and no numbers the user did not supply. A test enforces this: the only
  numbers allowed in the wording are `95` and `2`, from the respirator class
  names `N95` and `FFP2`.
- **No medical advice.** The plan is general guidance and says so.
- **No advice for the sake of it.** On a clean day the plan says so rather
  than inventing steps.

---

## How the solution works

```
             AQI reading + household profile
                          |
                          v
  +--------------------------------------------+
  |  src/aqi.py      numeric reading -> band  |
  |  src/profile.py  validated household       |
  +--------------------------------------------+
                          |
                          v
  +--------------------------------------------+
  |  src/rules.py     RULE_TABLE               |
  |                   band + profile -> actions |
  |                   strictness + overrides    |
  +--------------------------------------------+
                          |
                          v
  +--------------------------------------------+
  |  src/impact.py    impact line + assumption |
  |  src/budget.py    value per rupee -> plan  |
  +--------------------------------------------+
                          |
                          v
              plan for each person (Phase 3 UI)
```

### Module map

| Module | Responsibility | Depends on |
| --- | --- | --- |
| `src/aqi.py` | Validate an AQI reading, map it to a CPCB band, describe the band | nothing |
| `src/profile.py` | Validate the household: members, sensitivity, commute, home, budget | nothing |
| `src/rules.py` | Make the decisions: the rule table, strictness, overrides | `aqi`, `profile`, `budget`, `impact` |
| `src/impact.py` | Own all user-facing wording: impact lines, assumptions, disclaimer | nothing |
| `src/budget.py` | Rank actions by benefit per rupee and fit them to the budget | nothing (uses a `Protocol`) |
| `app.py` | Entry point. A placeholder until the Phase 3 UI | `src` |

`src/budget.py` talks to actions through a `typing.Protocol` rather than
importing `src/rules.py`, so the two modules do not depend on each other and
the dependency graph has no cycles.

### The three categories of step

Every action belongs to one of three categories, matching the brief:

- **`daily_routine`** - what changes in the day: school PT, the morning walk,
  the ride to work.
- **`indoor_air`** - what changes inside the home: when to open the windows,
  where one purifier should go, smoke and dust inside.
- **`sustainable_alternatives`** - the lower emission choice: public transport
  over a solo ride, no idling, no burning of leaves or garbage, no
  firecrackers.

### The rule table

Rules are data, not branches. Each row carries its own condition, wording,
cost tier, benefit score, and any advice it replaces:

```python
Rule(
    rule_id="sensitive.windows_closed",
    category=ActionCategory.DAILY_ROUTINE,
    title="Keep {name}'s room windows shut",
    detail="Keep {name}'s room windows shut through the morning and evening peaks, ...",
    audience=Audience.MEMBER,
    condition=all_of(
        member_with_sensitivity(Sensitivity.CHILD, Sensitivity.ELDERLY, Sensitivity.ASTHMATIC),
        severity_at_least(3),
    ),
    cost_tier=CostTier.FREE,
    benefit_score=9.0,
    safety_critical=True,
    overrides=("household.ventilation.moderate", "household.ventilation.poor"),
)
```

Adding a rule means adding a row. There is no `if` chain to edit, and the
rule ids are shared with `src/impact.py`, so the wording for a step and the
rule that produces it cannot drift apart (a test enforces this too).

### Cost tiers and budget ranking

Three coarse tiers, because that is how a family thinks: **Rs 0**, **about
Rs 500**, **about Rs 10,000**.

Actions are ranked by **benefit per rupee** and bought in that order. Free
steps are always taken. Two rules protect the most vulnerable member:

1. Steps marked `safety_critical` are considered before others.
2. When two steps cost the same, the one protecting the person the smog hits
   hardest wins. In practice this means Dadi's respirator is bought before
   the child's, when the budget only covers one.

If a step that protects the most vulnerable member cannot be afforded, the
plan says so by name rather than silently dropping it.

### Why the language model comes second

Phase 2 will add a Gemini layer with three properties:

- It receives the **rules output** as its input, so it can only reword a
  decision the engine has already made.
- User free text is isolated in `<user_notes>` delimiters and the model is
  instructed to treat it as data, not instructions.
- If the call fails or times out, or no `GEMINI_API_KEY` is set, the app
  falls back to the rule-based plan and says so: *"AI unavailable - showing
  rule-based plan."*

---

## Assumptions made

These are the project's assumptions. They are stated plainly because the
wording depends on them, and several of them are judgement calls rather than
facts.

1. **Benefit scores are relative judgements, not medical facts.** The scores
   (5 to 9) put steps in an order against each other. They are not measured
   effects, and they are never shown to a user as if they were.
2. **The vulnerability order is asthma, then child, then older adult, then
   healthy adult.** A product decision, chosen so that the person most
   affected by smog sets the tone for the household. It is not a clinical
   ranking.
3. **The strictness bump starts at the Moderate band.** A household with a
   child, an older adult, or someone with asthma is guided one step stricter
   from AQI 101 upward, and not at all below it.
4. **Air is usually cleaner in the middle of the day than at dawn in
   winter.** This drives the "shift the walk" and "air at the cleanest hour"
   advice. The cleanest hour changes from day to day, so the advice is
   always expressed as a check to do, not a fixed time.
5. **One purifier helps one closed room meaningfully.** This is why the plan
   places a single purifier in the most vulnerable member's room rather than
   spreading it across the home. The cost tier is an illustrative household
   budget, not a price list.
6. **A properly fitted N95/FFP2-type respirator is the right protection for
   outdoor time.** The wording stresses the fit and the face seal, and says
   explicitly that a loose cloth or surgical mask does not seal the same way.
7. **A household can travel in more than one way.** The brief's profile
   lists one commute mode for the household, but the persona needs Rohit on
   a two-wheeler and Neha working from home. `Member.commute_mode` is an
   optional override that falls back to the household value.
8. **Only the six Delhi NCR cities are supported** (Delhi, Noida, Greater
   Noida, Gurugram, Ghaziabad, Faridabad). Common spellings such as
   "Gurgaon" are accepted and normalised.
9. **The AQI reading is entered by the person.** The app does not fetch air
   quality data in Phase 1, so there is no API key to leak and no network
   dependency. The reading is treated as an input to be validated, not as
   data to be trusted.
10. **The plan is general guidance, not medical advice.** A disclaimer
    travels with the plan.

---

## Traceability

Every requirement in the official brief maps to a feature and a file.

| Brief requirement | Feature | File |
| --- | --- | --- |
| "suggest low-emission daily routines" | Commute-aware routine rules: shift the walk, change the ride, keep the work room closed | `src/rules.py` |
| "indoor air quality hacks" | Window timing by band, purifier placed in the most vulnerable room, damp cleaning, sealing gaps, no indoor smoke | `src/rules.py` |
| "sustainable alternatives" | Public transport over a solo ride, no idling, no burning leaves or garbage, green-waste collection, no firecrackers | `src/rules.py` |
| "tailored to their location and lifestyle" | Validated household profile: city, members, sensitivity, commute, home type | `src/profile.py` |
| "within their budget" | Benefit-per-rupee ranking, three cost tiers, vulnerable member protected first | `src/budget.py` |
| "clearly explaining the direct impact of their choices" | Every action carries an impact line and its assumption | `src/impact.py` |
| "They do not need another number" | Band plus plain-language actions, not a number | `src/aqi.py`, `src/rules.py` |
| "Decisions conflict (child vs grandmother vs commuter)" | Per-member actions, and a vulnerable member's advice replaces softer household advice | `src/rules.py` |
| "money is limited (often one purifier)" | One purifier, placed in the room of the person who needs it most, ranked against the budget | `src/rules.py`, `src/budget.py` |
| "nobody explains why a choice helps" | Impact line and assumption on every action, with a visible disclaimer | `src/impact.py` |
| "AQI like 412 - Severe" | CPCB band mapping with the six official bands and full boundary coverage | `src/aqi.py` |
| "GenAI-powered assistant" | Deterministic decisions first, Gemini personalisation added on top in Phase 2 with a guaranteed fallback | planned: `src/llm.py`, `src/prompts.py` |

---

## Evaluation criteria

| Criterion | How this build addresses it |
| --- | --- |
| **Code Quality** | One responsibility per module. Pure, typed, documented functions. Rules are table rows, not branches. Ruff configured in `pyproject.toml` with docstring, annotation, import-order, bug-pattern and simplification rules; `ruff check` and `ruff format --check` are clean. No dead code. |
| **Security** | Every user-controlled value is validated once in `src/profile.py` and `src/aqi.py`, with length limits, enum checks and range checks. No `eval`/`exec`, no shell use, no network calls in Phase 1. Error messages state the expected format and never echo the rejected input back. No personal data is logged anywhere. The only key, `GEMINI_API_KEY`, is read from the environment and `.env` is gitignored. Phase 2 isolates user text in delimiters and caps its length. |
| **Efficiency** | Pure functions with no I/O, so the plan is computed once and reused. No repeated API calls, no caching needed yet. `src/budget.py` is a single sort and a single pass. |
| **Testing** | 187 tests, one file per module, including every band boundary (0, 50/51, 100/101, 200/201, 300/301, 400/401, 500), out-of-range and non-numeric readings, empty households, invalid cities, duplicate members, zero and very large budgets, unknown commute modes, and the full vulnerable-member override behaviour. Phase 2 adds tests with a mocked LLM and with a failing LLM. |
| **Accessibility** | All copy is short and plain. Band names are words, never colour alone. Every action carries a text title as well as any visual treatment, so the plan reads correctly with no colour perception at all. The disclaimer is text, not an icon. Phase 3 keeps clear labels, logical tab order, and readable contrast. |
| **Problem Statement Alignment** | The traceability table above maps every phrase of the brief to a feature and a file. The persona's three conflicting decisions are the acceptance test for the whole product, and each one has a test. |

---

## Project layout

```
app.py                  # entry point (placeholder until the Phase 3 UI)
pyproject.toml          # ruff and pytest configuration
requirements.txt        # pinned dependencies
.env.example            # the key name, with no key in it
src/
  __init__.py
  aqi.py                # CPCB band mapping and validation
  profile.py            # validated household dataclasses
  rules.py              # the rule table, strictness, overrides
  impact.py             # impact lines, assumptions, disclaimer
  budget.py             # cost tiers and budget ranking
tests/
  test_aqi.py
  test_profile.py
  test_rules.py
  test_budget.py
  test_impact.py
```

---

## Setup and run

Python 3.11 or newer.

```bash
# 1. Create and activate an environment
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash
# source .venv/bin/activate        # macOS and Linux

# 2. Install the pinned dependencies
python -m pip install -r requirements.txt

# 3. Check the build is sound
python -m pytest
python -m ruff check .
python -m ruff format --check .

# 4. Run the entry point
python app.py
```

### Environment variables

Copy `.env.example` to `.env` and fill it in when the Phase 2 Gemini layer
arrives. `.env` is gitignored and must never be committed.

```
GEMINI_API_KEY=
```

The app does not need this key to work. Without it, the rules engine produces
the complete plan on its own.

---

## Sources and figures

- **CPCB National Air Quality Index bands.** The six bands and their ranges
  used by this project are the ones given in the official challenge brief:
  Good 0-50, Satisfactory 51-100, Moderate 101-200, Poor 201-300, Very Poor
  301-400, Severe 401-500.
- **WHO 2021 global air quality guidelines.** Referenced as the general basis
  for why fine particles matter and why advice for a child, an older adult,
  and someone with asthma is different.
  **TODO-verify:** the numeric WHO guideline values are deliberately **not**
  reproduced in this README or anywhere in the product copy. Before
  submission, check the current WHO guideline table and add the exact values
  with a full citation if any of them are quoted.
- No other statistic, percentage, or measurement is claimed anywhere in this
  repository. Where a step rests on a judgement, it is labelled as an
  assumption on the step itself.

---

## Accessibility

- Every band is a **word** ("Severe"), never a colour on its own. Colour is
  optional decoration, never the only carrier of meaning.
- Every action has a **text title** and a **text explanation**, so the plan
  is complete in plain text.
- The copy is short, uses everyday words, and avoids jargon. "Shift the
  walk", not "modify the activity schedule".
- The disclaimer is a sentence, not an icon.
- Phase 3 will keep a logical tab order, clear field labels, and readable
  contrast.

## Disclaimer

General guidance for everyday planning, not medical advice. For personal
medical advice, speak to a doctor. The same disclaimer ships with the plan
in the code, as `src.impact.DISCLAIMER`, so it cannot be forgotten in the UI.

---

## Build status

| Phase | Status |
| --- | --- |
| **Phase 1** - structure, AQI mapping, profile validation, rules engine, impact wording, budget ranking, tests, README | **Done** |
| Phase 2 - Gemini layer with fallback, prompt-injection defence, "show what was sent to the AI" | Not started |
| Phase 3 - Streamlit UI: onboarding form, per-person morning brief, budget ranking, live AQI entry | Not started |
| Phase 4 - README polish, final tests, repository size and single-branch check | Not started |

The module boundaries are already in place for the later phases: `src/llm.py`
and `src/prompts.py` will sit beside `src/rules.py` and consume its output,
and `app.py` will hold the interface and no logic.
