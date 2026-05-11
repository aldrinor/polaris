Audit 1 claim. Output YAML only.

CLAIM (POLARIS Q2 Canada-US Population Subgroups section):
"Protecting integrated supply chains is a key Canadian priority, with one analysis noting Canada already supplies many minerals deemed critical by the United States, with bilateral mineral trade valued at $95.6 billion in 2020."

CITED [5]: Analysis of Canada-US CUSMA trade dynamics, likely Canada-US bilateral economic analysis.

PRIMARY-SOURCE GROUND TRUTH (Canada-US bilateral mineral / metals trade):
- The $95.6 billion bilateral mineral trade figure for 2020 is large and notable.
- For 2020 context: Canada-US TOTAL bilateral goods trade was ~CAD 600B / USD ~470B in 2020. Mineral trade as ~$95.6B would represent ~20% of total bilateral goods trade — plausible for the resources-heavy Canada-US trade structure.
- StatCan and USITC data on bilateral mineral/metals/energy trade in 2020:
  - Energy (oil/gas) was the dominant bilateral category at ~$70-100B
  - Critical minerals + metals + non-energy mining: ~$20-40B
  - Combined energy + minerals could approach $95.6B for 2020 if "minerals" is broadly defined to include hydrocarbons.
- The claim specifies "minerals deemed critical by the United States" — this is a narrower subset (lithium, cobalt, nickel, REEs, etc.) per US Geological Survey 2022 Critical Minerals List.
- CAVEAT: If "$95.6B in 2020" refers to NARROW critical-minerals trade, the figure is likely overstated. If it refers to BROAD energy + metals + minerals, plausible.
- The specific decimal $95.6B suggests a particular source citation — possibly Natural Resources Canada / Canadian Critical Minerals Strategy 2022 documentation.

AUDIT:
1. "$95.6 billion in 2020" for bilateral mineral trade: PLAUSIBLE if broadly defined (energy+metals+minerals); QUESTIONABLE if narrow critical-minerals only.
2. The framing ambiguity (what counts as "minerals critical to the US") makes precise verification difficult without seeing citation [5]'s exact wording.
3. Source [5] (T4 secondary analysis): appropriate for the policy-context claim but the specific decimal needs the original cited source for precision.

Output YAML:
```yaml
claim_id: POLARIS-Q2-C2
cited_source_tier: T4
primary_source_verified: partial
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
