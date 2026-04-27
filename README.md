
# factraiser<img width="1402" height="1122" alt="factraiser" src="https://github.com/user-attachments/assets/835f820a-cead-48e3-a2e7-b9b532f58e20" />

AI Memory for enterprises. 

We all know the problem. The memory your org needs is fragmented across all of your users. 

A Claude memory here, an .MD file there. 

The Problems? 

1.) Not all memories and MD files are suitable for public consumption. 
2.) Some Memories and MF files are needed to help move the org forward. 


The impact. 

This means that despite your supertalented team and your AI spend, at some level your org may feel more disconnected than ever learnings aren't shared across teams and orgs the way they should be. 






The answer? 

A tiered hierarchical memory structure that allows users on the same enterprise account to interact with broader memory features and push .md files to rag with appropriate access. The LLM itself looks at the org and team level items to derive insights, and help steer people correctly. You can think of this as an  


<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="2040" height="1260" viewBox="0 0 680 420" role="img" aria-label="Tiered memory hierarchy">
  <title>Tiered memory hierarchy</title>
  <desc>Three tiers (org, team, personal) by two primitives (derived from chats, authored .md). Only personal tier has derived memory. Team and org are authored-only. Promotion across tiers is via explicit commit verbs.</desc>

  <style>
    text { font-family: system-ui, -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif; }
    .t  { font-size: 14px; fill: #2C2C2A; }
    .ts { font-size: 12px; fill: #5F5E5A; }
    .th { font-size: 14px; font-weight: 500; fill: #2C2C2A; }
    .c-teal > rect   { fill: #E1F5EE; stroke: #0F6E56; }
    .c-teal .th      { fill: #085041; }
    .c-teal .ts      { fill: #0F6E56; }
    .c-purple > rect { fill: #EEEDFE; stroke: #534AB7; }
    .c-purple .th    { fill: #3C3489; }
    .c-purple .ts    { fill: #534AB7; }
    .c-gray > rect   { fill: #F1EFE8; stroke: #5F5E5A; }
    .c-gray .ts      { fill: #5F5E5A; }
  </style>

  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M2 1L8 5L2 9" fill="none" stroke="#0F6E56" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </marker>
  </defs>

  <text class="ts" x="230" y="35" text-anchor="middle">Derived (auto from chats)</text>
  <text class="ts" x="450" y="35" text-anchor="middle">Authored (committed .md)</text>

  <text class="th" x="50" y="100" dominant-baseline="central">Org</text>
  <g class="c-gray">
    <rect x="130" y="60" width="200" height="80" rx="8" stroke-width="0.5" stroke-dasharray="4 3"/>
    <text class="ts" x="230" y="92" text-anchor="middle" dominant-baseline="central">—</text>
    <text class="ts" x="230" y="112" text-anchor="middle" dominant-baseline="central">no chats at this tier</text>
  </g>
  <g class="c-teal">
    <rect x="350" y="60" width="200" height="80" rx="8" stroke-width="0.5"/>
    <text class="th" x="450" y="92" text-anchor="middle" dominant-baseline="central">Authored</text>
    <text class="ts" x="450" y="114" text-anchor="middle" dominant-baseline="central">policies, charters</text>
  </g>

  <text class="th" x="50" y="200" dominant-baseline="central">Team</text>
  <g class="c-gray">
    <rect x="130" y="160" width="200" height="80" rx="8" stroke-width="0.5" stroke-dasharray="4 3"/>
    <text class="ts" x="230" y="192" text-anchor="middle" dominant-baseline="central">—</text>
    <text class="ts" x="230" y="212" text-anchor="middle" dominant-baseline="central">no chats at this tier</text>
  </g>
  <g class="c-teal">
    <rect x="350" y="160" width="200" height="80" rx="8" stroke-width="0.5"/>
    <text class="th" x="450" y="192" text-anchor="middle" dominant-baseline="central">Authored</text>
    <text class="ts" x="450" y="214" text-anchor="middle" dominant-baseline="central">runbooks, ADRs</text>
  </g>

  <text class="th" x="50" y="300" dominant-baseline="central">Personal</text>
  <g class="c-purple">
    <rect x="130" y="260" width="200" height="80" rx="8" stroke-width="0.5"/>
    <text class="th" x="230" y="292" text-anchor="middle" dominant-baseline="central">Derived</text>
    <text class="ts" x="230" y="314" text-anchor="middle" dominant-baseline="central">auto-summarized chats</text>
  </g>
  <g class="c-teal">
    <rect x="350" y="260" width="200" height="80" rx="8" stroke-width="0.5"/>
    <text class="th" x="450" y="292" text-anchor="middle" dominant-baseline="central">Authored</text>
    <text class="ts" x="450" y="314" text-anchor="middle" dominant-baseline="central">private notes, prefs</text>
  </g>

  <line x1="575" y1="345" x2="575" y2="55" stroke="#0F6E56" stroke-width="1.5" marker-end="url(#arrow)" fill="none"/>
  <text class="ts" x="585" y="195" dominant-baseline="central">commit</text>
  <text class="ts" x="585" y="211" dominant-baseline="central">verbs</text>

  <text class="ts" x="40" y="372">Read injection: org/team content flows into personal context per read perms.</text>
  <text class="ts" x="40" y="392">Derivation is a query-time function over readable tiers, not a stored layer.</text>
</svg>



Step 1.) Name your org

Create youe organization and add users. This automatically create an org repository for memories and .md files


Step 2.) Define permissions. Some team should never commit to team memory? Some teams should never commit anything to org memory? specify it here. 

Step 3.) Define your guardrails. By default PII, HR, and Legal related matters are not committed to anything that's not personal memory or.MD. However remember these systems are imperfect and you should do your best to give the Ai context 

Step 2.) Optional Create teams You can add users to a team in the web interface team members can see anything in the "team level" memory or MD files. 

Step 3.) 
