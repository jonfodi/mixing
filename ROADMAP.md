## UX 
- improve Ableton bridge, general UX flow for getting up and running with the agent
    - do we need Ableton open? can we automate the first time setup? 
    - can it be "what track do u want to work on?" and we search their projects/tracks for a match? 
## Balance
- a tool that measures each stem's level after controls are applied. the LLM uses the theme to decide what good balance is and re-balances. needs audio measurement. until then, the artist listens and gives feedback.

## Bridge
- switch the bridge from UDP to TCP. macOS caps one UDP packet at 9216 bytes. a real project's track list is bigger, so the adapter times out on it.
