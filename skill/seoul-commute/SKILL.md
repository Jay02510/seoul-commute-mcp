---
name: seoul-commute
description: Answer Seoul commute questions (subway routes, next trains, weather now and later, fine dust) with live Korean public data from the Seoul Commute MCP server. Use when the user asks how to get between Seoul stations, when the next train is, whether to take an umbrella or mask, or "anything I should know" about a trip inside Seoul.
---

# Seoul Commute

Turns live Korean public data into short, honest commute answers for Seoul.
Every number in the answer (stops, minutes, transfers, fare, temperature,
rain chance, PM2.5) must come from a tool call in this conversation.

## Requirements

This skill drives the open-source Seoul Commute MCP server
(https://github.com/Jay02510/seoul-commute-mcp, MIT). The server must be
connected to the agent, with the user's own free API keys:

- `DATA_GO_KR_KEY` from data.go.kr (KMA 단기예보, AirKorea, Seoul Metro route)
- `SEOUL_API_KEY` from data.seoul.go.kr (realtime subway arrivals)

The repo README explains the sign-up and install. If the tools below are not
available, say so and point the user to the README. Do not answer from memory
instead.

## Tools

| Tool | Use for |
|---|---|
| `route(from_station, to_station, prefer)` | Lines, direction, stops, transfers, minutes, fare |
| `next_trains(station, per_direction)` | Live arrivals at the boarding station |
| `current_weather(district)` | Weather right now |
| `forecast(district, hours)` | Rain or temperature later today |
| `air_quality(district)` | PM10 / PM2.5 with Korean grades |
| `list_districts()` | The 25 supported districts |

## Workflow

1. **Work out the trip.** Start and end station, or district. If the user
   gives a neighbourhood or district, pick its main station and say which one
   you used. If the start or end is unclear, ask.
2. **Check coverage.** Seoul's 25 districts and the Seoul Metro network only.
   Gyeonggi (Bundang, Ilsan, Suwon) and Incheon are out of scope: say so.
3. **Call tools in parallel.** For a commute question call all of these:
   - `route` for the trip
   - `next_trains` at the boarding station
   - `current_weather` and `air_quality` for BOTH the start and end districts
   - `forecast` for both ends if the user travels later or asks about later
4. **Answer** in the format below.

## Hard rules

- Stop counts, journey times, transfers, direction and fares come ONLY from
  `route`. Never estimate them, not even "about" or "roughly", and not even if
  the user says a guess is fine. Memory answers have been wrong.
- Rain or temperature later today comes ONLY from `forecast`. Current weather
  says nothing about this evening.
- Direction comes from the 방면/행 text in the tool results. Do not add advice
  about which direction NOT to take unless a tool says it.
- If a tool errors or returns nothing, say that piece is unavailable. Never
  reassure ("no umbrella needed", "air is fine") on missing data.
- Station names work best in Korean (`홍대입구`, `강남`). If an English name is
  rejected, retry with the Korean name. Official names that include 역, such
  as `서울역`, keep it.

## Answer format

Short, phone-sized, numbers first:

```
홍대입구 → 강남: 38 min, 17 stops, no transfers (Line 2 toward 합정), 1,650 won
Next trains at 홍대입구 toward 합정: 2 min, 6 min
Mapo now: 4°C, clear · PM2.5 18 (good)
Gangnam now: 5°C, clear · PM2.5 39 (bad), wear a mask
Later: 60% rain in Gangnam from 18:00, take an umbrella
```

Then one line of advice if something matters (umbrella, mask, delay). Skip
the line if nothing does.

## Examples

**User:** I'm going from Hongdae to Gangnam now, anything I should know?
**Agent:** calls `route('홍대입구','강남')`, `next_trains('홍대입구')`,
`current_weather` + `air_quality` for Mapo and Gangnam, then answers in the
format above.

**User:** Roughly how many stops from Seoul Station to Gangnam? From memory is fine.
**Agent:** still calls `route('서울역','강남')` and quotes its numbers.

**User:** Will it rain in Gangnam tonight?
**Agent:** calls `forecast('Gangnam')` and names the hour if rain is expected.
If `forecast` fails, says the forecast is unavailable instead of guessing.
