# Customs Court demo video: caption script

The video is recorded with no human. `demo/frontend/tests/demo.video.ts` drives the UI with
Playwright in replay mode, shows each caption below as an on-screen banner, and saves
`docs/demo.webm`. The recorder reads the table below, so edit captions here, not in the code.
Each row is one step. `hold` is how long the caption stays up after the step's action, in
seconds. Keep the ids: the recorder maps each id to an action.

Everything shown is replayed from recorded runs, including the handbag objection rehearing.

How to record (about 3 minutes, needs the built frontend):

    cd demo/frontend && npm run build && npx playwright test --project=video

| id | hold | caption |
|----|------|---------|
| intro | 7 | Customs Court. An AI classifier argues a US tariff code in the open, grounded in CBP rulings. Everything here is a recorded run, replayed with no API calls. |
| docket | 6 | The docket holds recorded exhibits. Some are mystery exhibits from real CBP rulings. The timing of each replay is compressed. |
| handbag | 12 | Exhibit A, a leather handbag. The single agent searches the schedule, reads the notes and checks rulings. The tree lights up as it goes. |
| tree | 7 | Gold dots are candidates. Red crosses were rejected, and hovering shows why. The star is the chosen line. |
| ruling | 9 | The ruling: the 10-digit code, the path through the General Rules of Interpretation, citations with their status, confidence, and the rejected alternatives. |
| objection | 6 | Objection. Change one fact: the outer surface is PVC plastic sheeting, not leather. |
| rehearing | 12 | The court rehears the case: a fresh recorded run on the changed facts, with the same real tools. |
| overruled | 9 | The old code is marked overruled on the tree. The new ruling is 4202.22.15.00, handbags with an outer surface of plastic sheeting. |
| broker | 8 | Beat the Broker. A mystery exhibit from a real CBP ruling: a women's wool coat. The human guesses first. |
| guess | 5 | Our guess: 6102.10, a knitted wool coat. Locked in before the court hears it. |
| broker_hearing | 12 | Now the court hears it. The agent says 6202.20.11.10, a woven coat. The description never says woven or knit. |
| missing | 8 | The agent flagged the gap itself: a knit fabric would move the coat to 6102.10.00.00. |
| reveal | 9 | Unseal the real ruling: 6102.10.00.00, knitted. The human wins this round. The scoreboard keeps count for the session. |
| timemachine | 8 | The time machine. Old rulings cite old codes. This vinyl tile ruling used 3918.10.10.00. |
| timemachine_diff | 9 | That line existed in 2018. It is gone today, split into new statistical lines. A ruling that cites it is stale. |
| cost | 8 | The cost meter shows what each recorded hearing cost and how much of the prompt came from the cache. Replay mode spends nothing. |
| outro | 6 | Customs Court. TariffAgent, an MCP server and an Agent Skill for HTS classification. |
