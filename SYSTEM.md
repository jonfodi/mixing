## Goal
turn artists vision into mixed and mastered tracks 

## Architecture 
Artist input -> Agent -> tools -> adapter (ableton tday) -> client -> bridge -> DAW (ableton)

**Testable Modules** 

tools are used to create testable, independantly optimized functions the LLM can call 
example: 
- the classification tool splits the artist input into theme discussion and direct control requests 
- the theme tool uses the theme discussion text to create/update the theme 

both these tools can be tested and worked on in isolation. 
 - theme tool is a core part of the product. its system prompt and other features will be key to get right and test to ensure product works as expected. 
 - we can be more resource-efficient this way by optimizing which models we call for which step 
 - agent can still call either whenever

## Context Engineering / Declarative Flow
- system prompts give the agents guidance on when to call which tools 
- tool definitions tell the agents what the tools are, lets them decide when to use 
- code is still used when the set of steps is concrete 
- guardrails exist around hard volume limits, retries, number of iterations, and rollbacks 

**State Management**
- Context Management 
    - be mindful of optimizing context passed to the model 
    - data that must be referenced frequently and is important is stored as independant state as opposed to relying on conversation history 
    - future: prompts are categorized by semantic similarity to cache
    - future: conversation history is summarized to avoid token bloat 
    - future: remember artist preference for vocabulary and effects 
- Drift with external systems 
    - snapshot and reconcile to always keep in sync with whats in the DAW
    - 
- Product 
    - remember the effects that were applied for revert (and future artist preference)
    - only revert effects the agent changed, not what user changed

## Failure Handling

framed by what the artist experiences. the key question for each cause: can the model fix it?
- yes: send the reason back to the model and let it fix it
- no: code retries once and then stops the turn and tells the artist

**Product Failures**

| # | artist experiences | cause | status |
|---|---|---|---|
| 1 | wrong change | model asks for a setting or value that does not exist | handled |
| 2 | waiting for nothing | Ableton or Claude is down and the agent keeps trying | handled |
| 3 | two of the same effect | a retry adds the effect a second time | prevented |
| 4 | half changed track | effect added but settings never set. or only some controls applied | handled |
| 5 | agent describes the wrong track | agent thinks nothing changed but Ableton has new effects | not yet |
| 6 | artist hand edits undone | a rollback undoes dials the artist turned | handled |

Ableton down and Claude down both cause #4. a turn that stops halfway leaves the track half changed either way

**1. Wrong Change**
- each rejected control goes back to the model with the reason
- the reason lists the valid names or range or choices so the model can fix it in one step

**2. Waiting For Nothing**
- Ableton: every network error becomes one error (BridgeDown). code retries once after 0.5s and then stops the turn
- Ableton down before the turn starts: stop with 0 model calls
- Claude: the SDK retries twice on its own (429, 5xx, timeouts, dropped connections). then the turn stops
- Claude request timeout is 60s. the SDK default is 10 min and would freeze the program
- the artist sees one plain line. no traceback
- history stays valid so the artist can send the same message again

**3. Two Of The Same Effect**
- insert is never retried. it is the only bridge command that is not idempotent
- set_control checks for the effect before it inserts

**4. Half Changed Track**
- snapshot the track at the start of each turn
- if the turn fails, compare Ableton with the snapshot and put back every difference
- delete effects added after the snapshot and set back changed values


**6. Artist Hand Edits Undone**
- only put back the stems the agent touched this turn

**Testing**
- pytest with a fake bridge. no model and no Ableton needed
- fault injection: BRIDGE_FAIL_AT=N makes every bridge call from the Nth on fail

**Future**
- fall back to another model when one is down
- at scale: a queue and per artist limits so one artist cannot use up the shared rate limit
