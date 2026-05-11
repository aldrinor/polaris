Tier-1 v2 §-1.1 line-by-line audit of Gemini Ultra DR Q1 claims. Output YAML only.

# Context

Auditing Gemini Ultra Deep Research output on Q1 "Canada sovereign frontier-LLM compute vs US hyperscalers for federal AI workloads 2026".
POLARIS comparison: 96.8% V on 31 claims via line-by-line audit vs captured spans.
Now auditing Gemini against ACTUAL cited URLs (harvested from live chat anchor tags, fetched, content excerpted).

# Audit instruction per claim

For each claim, check whether the candidate source content actually supports the claim:
- The specific decimal/dollar/year in the claim must be present in the candidate source content, OR the claim must be a faithful paraphrase of the source.

Tier-1 v2 schema per claim:
- claim_type: economic | regulatory | technical | comparative | geographical | epidemiology | background
- materiality: critical | major | minor | background
- citation_context_match: yes | partial | no | unverifiable
- verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
- rationale: one sentence quoting/paraphrasing the supporting evidence text
- reviewer_confidence: 0.0-1.0

# Banned shortcuts

- Do NOT auto-VERIFIED just because a candidate is given. Read the content_excerpt and confirm the specific decimal/year appears.
- Flag UNSUPPORTED if the specific decimal/year in the claim is NOT in any candidate's content.

# Claims to audit (batch 3, 7 claims)

[
  {
    "claim_id": "GM-Q1-T1-015",
    "sentence": "This project represents a $9 billion economic injection and is explicitly marketed as a secure alternative to global hyperscalers.",
    "numeric_tokens": [
      "$9 billion"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_000",
        "url": "https://www.newswire.ca/news-releases/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure-854223505.html",
        "matching_tokens": [
          "$9 billion"
        ],
        "content_excerpt": "TELUS and Government of Canada advance work to scale Canada's sovereign AI infrastructure Accessibility Statement Skip Navigation Resources Investor Relations Journalists Webcasts Français --> Français my CNW&nbsp; Login Register Client Login&nbsp; PR Newswire Amplify™ Next Gen Communications Cloud Cision Communications Cloud® Sign Up Send a Release News Products Contact Search Search When typing in this field, a list of search results will appear and be automatically updated as you type. Searching for your content... No results found. Please change your search terms and try again. Advanced Search News in Focus Browse News Releases All News Releases All Public Company News Releases Overview Multimedia Gallery All Multimedia All Photos All Videos Multimedia Gallery Overview Trending Topics All Trending Topics Business Auto &amp; Transportation All Automotive &amp; Transportation Aerospace, Defense Air Freight Airlines &amp; Aviation Automotive Maritime &amp; Shipbuilding Railroads and Intermodal Transportation Supply Chain/Logistics Transportation, Trucking &amp; Railroad Travel Trucking and Road Transportation Auto &amp; Transportation Overview View All Auto &amp; Transportation Business Technology All Business Technology Blockchain Broadcast Tech Computer &amp; Electronics Computer Hardware Computer Software Data Analytics Electronic Commerce Electronic Components Electronic Design Automation Financial Technology High Tech Security Internet Technology Nanotechnology Networks"
      },
      {
        "evidence_id": "gm_ev_032",
        "url": "https://investingnews.com/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure/",
        "matching_tokens": [
          "$9 billion"
        ],
        "content_excerpt": "Raven.config('https://6b64f5cc8af542cbb920e0238864390a@sentry.io/147999').install(); TELUS and Government of Canada advance work to scale Canada&#x27;s sovereign AI infrastructure | INN Connect with us Information About Us Contact Us Careers Partnerships Advertise With Us Authors Browse Topics Events Disclaimer Privacy Policy Australia North America World Login Investing News Network Your trusted source for investing success North America Australia World My INN Videos Companies Press Releases Private Placements SUBSCRIBE Reports &amp; Guides Market Outlook Reports Investing Guides Button Resource Precious Metals Battery Metals Base Metals Energy Critical Minerals Tech Life Science Market Market Market News Market Stocks Market Market Market News Market Stocks Home &gt; Market News &gt; TELUS and Government of Canada advance work to scale Canada&#39;s sovereign AI infrastructure Investing News Network May 11, 2026 With Canada&#39;s first Sovereign AI Factory in Rimouski, Quebec, now sold out, Telus is expanding its sovereign AI infrastructure with three world-class facilities in B.C. Designed to be the world&#39;s most sustainable sovereign data centres, the cluster will scale to over 60,000 GPUs and 150 MW by 2032 Telus is advancing work with the Government of Canada on a proposed Sovereign AI Factory cluster under the federal Enabling Large-Scale Sovereign AI Data Centres initiative a program designed to build the sovereign, high-performance AI compute infrastructure Canada "
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-016",
    "sentence": "TELUS guarantees that intellectual property and sensitive data will never traverse outside Canadian borders, while running the entire operation on 98% clean hydroelectric energy and utilizing advanced liquid cooling with heat recovery technologies.",
    "numeric_tokens": [
      "98%"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_000",
        "url": "https://www.newswire.ca/news-releases/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure-854223505.html",
        "matching_tokens": [
          "98%"
        ],
        "content_excerpt": "TELUS and Government of Canada advance work to scale Canada's sovereign AI infrastructure Accessibility Statement Skip Navigation Resources Investor Relations Journalists Webcasts Français --> Français my CNW&nbsp; Login Register Client Login&nbsp; PR Newswire Amplify™ Next Gen Communications Cloud Cision Communications Cloud® Sign Up Send a Release News Products Contact Search Search When typing in this field, a list of search results will appear and be automatically updated as you type. Searching for your content... No results found. Please change your search terms and try again. Advanced Search News in Focus Browse News Releases All News Releases All Public Company News Releases Overview Multimedia Gallery All Multimedia All Photos All Videos Multimedia Gallery Overview Trending Topics All Trending Topics Business Auto &amp; Transportation All Automotive &amp; Transportation Aerospace, Defense Air Freight Airlines &amp; Aviation Automotive Maritime &amp; Shipbuilding Railroads and Intermodal Transportation Supply Chain/Logistics Transportation, Trucking &amp; Railroad Travel Trucking and Road Transportation Auto &amp; Transportation Overview View All Auto &amp; Transportation Business Technology All Business Technology Blockchain Broadcast Tech Computer &amp; Electronics Computer Hardware Computer Software Data Analytics Electronic Commerce Electronic Components Electronic Design Automation Financial Technology High Tech Security Internet Technology Nanotechnology Networks"
      },
      {
        "evidence_id": "gm_ev_003",
        "url": "https://www.canada.ca/en/shared-services/corporate/about-us/transparency/departmental-plan/2026-27/shared-services-canada-2026-27-departmental-plan.html",
        "matching_tokens": [
          "98%"
        ],
        "content_excerpt": "Shared Services Canada 2026–27 Departmental Plan - Canada.ca Skip to main content Skip to &#34;About government&#34; Language selection Fran&ccedil;ais fr / Gouvernement du Canada Search Search Canada.ca Search Menu Main Menu Jobs and the workplace Immigration and citizenship Travel and tourism Business and industry Benefits Health Taxes Environment and natural resources National security and defence Culture, history and sport Policing, justice and emergencies Transport and infrastructure Canada and the world Money and finances Science and innovation Manage life events You are here: Canada.ca Shared Services Canada About Shared Services Canada Transparency Departmental plan Shared Services Canada 2026–27 Departmental Plan Expand all Collapse all On this page At a glance From the Minister Plans to deliver on core responsibilities and internal services Core responsibility : Common Government of Canada IT Operations Internal services Department-wide considerations Related government priorities Key risks Planned spending and human resources Spending Funding Future-oriented condensed statement of operations Human resources Supplementary information tables Federal tax expenditures Corporate information Definitions Copyright Information Except as otherwise specifically noted, the information in this publication may be reproduced, in part or in whole and by any means, without charge or further permission from Shared Services Canada, provided that due diligence is exercised to ensure "
      },
      {
        "evidence_id": "gm_ev_032",
        "url": "https://investingnews.com/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure/",
        "matching_tokens": [
          "98%"
        ],
        "content_excerpt": "Raven.config('https://6b64f5cc8af542cbb920e0238864390a@sentry.io/147999').install(); TELUS and Government of Canada advance work to scale Canada&#x27;s sovereign AI infrastructure | INN Connect with us Information About Us Contact Us Careers Partnerships Advertise With Us Authors Browse Topics Events Disclaimer Privacy Policy Australia North America World Login Investing News Network Your trusted source for investing success North America Australia World My INN Videos Companies Press Releases Private Placements SUBSCRIBE Reports &amp; Guides Market Outlook Reports Investing Guides Button Resource Precious Metals Battery Metals Base Metals Energy Critical Minerals Tech Life Science Market Market Market News Market Stocks Market Market Market News Market Stocks Home &gt; Market News &gt; TELUS and Government of Canada advance work to scale Canada&#39;s sovereign AI infrastructure Investing News Network May 11, 2026 With Canada&#39;s first Sovereign AI Factory in Rimouski, Quebec, now sold out, Telus is expanding its sovereign AI infrastructure with three world-class facilities in B.C. Designed to be the world&#39;s most sustainable sovereign data centres, the cluster will scale to over 60,000 GPUs and 150 MW by 2032 Telus is advancing work with the Government of Canada on a proposed Sovereign AI Factory cluster under the federal Enabling Large-Scale Sovereign AI Data Centres initiative a program designed to build the sovereign, high-performance AI compute infrastructure Canada "
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-017",
    "sentence": "In early 2026, Alpha Compute officially activated the ALPHA-01 cluster in a Canadian datacenter, featuring 504 of the latest NVIDIA B200 GPUs, with aggressive plans to scale beyond 1,000 GPUs using specialized, hardware-backed non-recourse debt financing.",
    "numeric_tokens": [
      "1,000",
      "2026"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_000",
        "url": "https://www.newswire.ca/news-releases/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure-854223505.html",
        "matching_tokens": [
          "1,000",
          "2026"
        ],
        "content_excerpt": "TELUS and Government of Canada advance work to scale Canada's sovereign AI infrastructure Accessibility Statement Skip Navigation Resources Investor Relations Journalists Webcasts Français --> Français my CNW&nbsp; Login Register Client Login&nbsp; PR Newswire Amplify™ Next Gen Communications Cloud Cision Communications Cloud® Sign Up Send a Release News Products Contact Search Search When typing in this field, a list of search results will appear and be automatically updated as you type. Searching for your content... No results found. Please change your search terms and try again. Advanced Search News in Focus Browse News Releases All News Releases All Public Company News Releases Overview Multimedia Gallery All Multimedia All Photos All Videos Multimedia Gallery Overview Trending Topics All Trending Topics Business Auto &amp; Transportation All Automotive &amp; Transportation Aerospace, Defense Air Freight Airlines &amp; Aviation Automotive Maritime &amp; Shipbuilding Railroads and Intermodal Transportation Supply Chain/Logistics Transportation, Trucking &amp; Railroad Travel Trucking and Road Transportation Auto &amp; Transportation Overview View All Auto &amp; Transportation Business Technology All Business Technology Blockchain Broadcast Tech Computer &amp; Electronics Computer Hardware Computer Software Data Analytics Electronic Commerce Electronic Components Electronic Design Automation Financial Technology High Tech Security Internet Technology Nanotechnology Networks"
      },
      {
        "evidence_id": "gm_ev_008",
        "url": "https://briefglance.com/articles/qubecs-green-energy-premium-data-centers-face-steep-power-rate-hikes",
        "matching_tokens": [
          "1,000",
          "2026"
        ],
        "content_excerpt": "Québec&#39;s Green Energy Premium: Data Centers Face Steep Power Rate Hikes - BriefGlance.com Skip to main content BriefGlance.com INTELLIGENCE Media Center Contact Market pulse Wire Sign In Menu &times; Media Center Contact Wire Sign In Home Margaret Mitchell: Unfiltered Québec&#39;s Green Energy Premium: Data Centers Face Steep Power Rate Hikes Québec&#39;s Green Energy Premium: Data Centers Face Steep Power Rate Hikes 📊 Key Data New data center rate : 13¢ per kWh (double the current rate for large-power customers) Blockchain rate : 19.5¢ per kWh Projected demand surge : Data center electricity use expected to grow from 200 MW to over 1,000 MW by 2035 🎯 Expert Consensus Experts would likely conclude that Hydro-Québec&#39;s proposed rate hikes represent a strategic shift to balance industrial growth with social equity, testing whether Québec&#39;s renewable energy premium can sustain its competitive edge in the tech sector. MM Margaret Mitchell Margaret Mitchell: Unfiltered 3 months ago Québec&#39;s Green Energy Premium: Data Centers Face Steep Power Rate Hikes MONTRÉAL, QC – February 19, 2026 – The era of exceptionally cheap power for Québec&#39;s most energy-intensive tech industries is drawing to a close. Hydro-Québec, the province&#39;s public utility, has proposed dramatic rate hikes for large data centers and blockchain operators, signaling a major strategic shift aimed at capturing the true economic value of its vast renewable energy resources. Under the proposal subm"
      },
      {
        "evidence_id": "gm_ev_009",
        "url": "https://news.hydroquebec.com/news/press-releases/all-quebec/hydro-quebec-proposing-regie-energie-new-rate-large-data-centres-adjustment-rate-cryptographic-use-applied-blockchains.html",
        "matching_tokens": [
          "1,000",
          "2026"
        ],
        "content_excerpt": "A new rate for data centres and a rate adjustment for blockchains to reflect the value of renewable electricity Direct access to main content Direct access to footer menu All Sites News Contact Us Power Outages Français Login Newsroom Launch Search Menu Login Homepage Press releases Media contacts Media Library Homepage Press releases Media contacts Media Library News Press releases A new rate for data centres and a rate adjustment for blockchains to reflect the value of renewable electricity General news, February 19, 2026 --> Last modified date : February 19, 2026 --> A new rate for data centres and a rate adjustment for blockchains to reflect the value of renewable electricity Montréal – Hydro-Québec is proposing to the Régie de l’énergie a new rate for large data centres and an adjustment of the rate for cryptographic use applied to blockchains. These changes are meant to ensure businesses in these sectors cover the costs associated with their high electricity demand while still paying prices comparable to those elsewhere in North America. This initiative is backed by the government of Québec, which has issued Orders in Council addressing the related economic, social and environmental concerns. Through this approach, Hydro-Québec is managing the growth of its assets responsibly by limiting the impact on its other customer categories. Bloomberg figures reveal the need to take action: in US jurisdictions experiencing strong growth in the data centre sector, electricity bill"
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-018",
    "sentence": "While the federal SCIP funding and private debt markets provide the initial CapEx necessary to secure hardware, the OpEx of Canadian infrastructure is undergoing a radical, state-driven transformation in 2026.The Quebec Hydro Rate Shock and the Erosion of ArbitrageHistorically, Canada's primary competitive advantage in global datacenter hosting was rooted in the province of Quebec's abundant, exceptionally low-cost, and sustainable hydroelectric power.",
    "numeric_tokens": [
      "2026"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_000",
        "url": "https://www.newswire.ca/news-releases/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure-854223505.html",
        "matching_tokens": [
          "2026"
        ],
        "content_excerpt": "TELUS and Government of Canada advance work to scale Canada's sovereign AI infrastructure Accessibility Statement Skip Navigation Resources Investor Relations Journalists Webcasts Français --> Français my CNW&nbsp; Login Register Client Login&nbsp; PR Newswire Amplify™ Next Gen Communications Cloud Cision Communications Cloud® Sign Up Send a Release News Products Contact Search Search When typing in this field, a list of search results will appear and be automatically updated as you type. Searching for your content... No results found. Please change your search terms and try again. Advanced Search News in Focus Browse News Releases All News Releases All Public Company News Releases Overview Multimedia Gallery All Multimedia All Photos All Videos Multimedia Gallery Overview Trending Topics All Trending Topics Business Auto &amp; Transportation All Automotive &amp; Transportation Aerospace, Defense Air Freight Airlines &amp; Aviation Automotive Maritime &amp; Shipbuilding Railroads and Intermodal Transportation Supply Chain/Logistics Transportation, Trucking &amp; Railroad Travel Trucking and Road Transportation Auto &amp; Transportation Overview View All Auto &amp; Transportation Business Technology All Business Technology Blockchain Broadcast Tech Computer &amp; Electronics Computer Hardware Computer Software Data Analytics Electronic Commerce Electronic Components Electronic Design Automation Financial Technology High Tech Security Internet Technology Nanotechnology Networks"
      },
      {
        "evidence_id": "gm_ev_001",
        "url": "https://www.canada.ca/en/innovation-science-economic-development/news/2026/05/government-of-canada-and-telus-advance-work-to-build-sovereign-ai-infrastructure.html",
        "matching_tokens": [
          "2026"
        ],
        "content_excerpt": "Government of Canada and TELUS advance work to build sovereign AI infrastructure - Canada.ca Skip to main content Skip to &#34;About government&#34; Language selection Fran&ccedil;ais fr / Gouvernement du Canada Search Search Canada.ca Search Menu Main Menu Jobs and the workplace Immigration and citizenship Travel and tourism Business and industry Benefits Health Taxes Environment and natural resources National security and defence Culture, history and sport Policing, justice and emergencies Transport and infrastructure Canada and the world Money and finances Science and innovation Manage life events You are here: Canada.ca Government of Canada and TELUS advance work to build sovereign AI infrastructure From: Innovation, Science and Economic Development Canada News release This marks a significant step to bringing large-scale data centre capacity online This marks a significant step to bringing large-scale data centre capacity online May 11, 2026 – Vancouver, British Columbia Globally, industry and government alike are moving quickly to bring large-scale data centre capacity online. Access to cutting-edge compute infrastructure is crucial for maintaining Canada’s leadership in artificial intelligence (AI), empowering researchers and industries to thrive. Today, the Honourable Evan Solomon, Minister of Artificial Intelligence and Digital Innovation and Minister responsible for the Federal Economic Development Agency for Southern Ontario, announced that the Government of Canada"
      },
      {
        "evidence_id": "gm_ev_002",
        "url": "https://nationalmagazine.ca/en-ca/articles/law/in-depth/2026/canada-s-uncertain-digital-future",
        "matching_tokens": [
          "2026"
        ],
        "content_excerpt": "National - CBA National - Canadian Legal Affairs Skip to Content fran&#xE7;ais Search Toggle Navigation CBA Influence All Policy Resolutions Submissions Law All Judiciary Rule of law In-depth Hot topics Ethics Opinion Business &amp; corporate Access to justice Legal market All Regulatory Commentary Corporate Counsel Law Firms Legal Tech Partner Firms People All Profile Q&amp;A The practice All Corporate Counsel Legal education New Law Small and solo Workplace Young lawyers Contact Us Facebook Twitter Linkedin RSS Law In-depth Canada&#x2019;s uncertain digital future Observers say this country must create its own tools to move away from U.S. technology and enhance digital sovereignty, but a lack of political will is standing in the way BY Julie Sobowale 20 Apr. 2026 Just_Super (iStock) Share: Facebook Twitter Linkedin Email Earlier this year, the French government announced it would stop using Zoom, Microsoft Teams, and any other U.S.-based videoconferencing platforms by 2027 and begin using French-based Visio. The decision came after Anton Carniaux, director of public and legal affairs for Microsoft France, testified before the French Senate that, under the U.S. Cloud Act , Microsoft could be forced to hand over data from any country, regardless of where it is stored. Austria, Germany and Switzerland are also racing to find alternatives to U.S.-based technology. Digital sovereignty, which is the protection and control of Canadian data, is quickly becoming the most prominent i"
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-019",
    "sentence": "Global AI power capacity escalated to approximately 30 GW by late 2025, and Hydro-Québec internal projections indicate that datacenter electricity demand within the province will surge an astonishing sevenfold by 2035, exceeding 1,000 MW.",
    "numeric_tokens": [
      "1,000",
      "2025",
      "30 GW"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_000",
        "url": "https://www.newswire.ca/news-releases/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure-854223505.html",
        "matching_tokens": [
          "1,000",
          "2025"
        ],
        "content_excerpt": "TELUS and Government of Canada advance work to scale Canada's sovereign AI infrastructure Accessibility Statement Skip Navigation Resources Investor Relations Journalists Webcasts Français --> Français my CNW&nbsp; Login Register Client Login&nbsp; PR Newswire Amplify™ Next Gen Communications Cloud Cision Communications Cloud® Sign Up Send a Release News Products Contact Search Search When typing in this field, a list of search results will appear and be automatically updated as you type. Searching for your content... No results found. Please change your search terms and try again. Advanced Search News in Focus Browse News Releases All News Releases All Public Company News Releases Overview Multimedia Gallery All Multimedia All Photos All Videos Multimedia Gallery Overview Trending Topics All Trending Topics Business Auto &amp; Transportation All Automotive &amp; Transportation Aerospace, Defense Air Freight Airlines &amp; Aviation Automotive Maritime &amp; Shipbuilding Railroads and Intermodal Transportation Supply Chain/Logistics Transportation, Trucking &amp; Railroad Travel Trucking and Road Transportation Auto &amp; Transportation Overview View All Auto &amp; Transportation Business Technology All Business Technology Blockchain Broadcast Tech Computer &amp; Electronics Computer Hardware Computer Software Data Analytics Electronic Commerce Electronic Components Electronic Design Automation Financial Technology High Tech Security Internet Technology Nanotechnology Networks"
      },
      {
        "evidence_id": "gm_ev_004",
        "url": "https://epoch.ai/data-insights/ai-datacenter-power",
        "matching_tokens": [
          "2025",
          "30 GW"
        ],
        "content_excerpt": "Global AI power capacity is now comparable to peak power usage of New York State | Epoch AI Latest Topics AI Progress Scaling Software progress Open models Capabilities Math Industry Leading companies Finances Geopolitics Infrastructure Chips Data centers Energy Impacts Adoption and use Economic impact Future of AI See all topics Our work Featured AI Trends &amp; Statistics Data Explorers Capabilities &amp; Benchmarking Publications Papers &amp; Reports Data Insights Newsletter Podcast See all publications Data explorers Capabilities Models Frontier Data Centers Chip Owners Companies Polling on AI Use See all data explorers Benchmarks by Epoch AI Epoch Capabilities Index FrontierMath: Open Problems FrontierMath: Tiers 1-4 About About Epoch AI Donate Team Careers Consultations For press Transparency Contact Latest Topics AI Progress Scaling Software progress Open models Capabilities Math Industry Leading companies Finances Geopolitics Infrastructure Chips Data centers Energy Impacts Adoption and use Economic impact Future of AI See all topics Our work Featured AI Trends &amp; Statistics Data Explorers Capabilities &amp; Benchmarking Publications Papers &amp; Reports Data Insights Newsletter Podcast See all publications Data explorers Capabilities Models Frontier Data Centers Chip Owners Companies Polling on AI Use See all data explorers Benchmarks by Epoch AI Epoch Capabilities Index FrontierMath: Open Problems FrontierMath: Tiers 1-4 About About Epoch AI Donate Team Careers C"
      },
      {
        "evidence_id": "gm_ev_008",
        "url": "https://briefglance.com/articles/qubecs-green-energy-premium-data-centers-face-steep-power-rate-hikes",
        "matching_tokens": [
          "1,000",
          "2025"
        ],
        "content_excerpt": "Québec&#39;s Green Energy Premium: Data Centers Face Steep Power Rate Hikes - BriefGlance.com Skip to main content BriefGlance.com INTELLIGENCE Media Center Contact Market pulse Wire Sign In Menu &times; Media Center Contact Wire Sign In Home Margaret Mitchell: Unfiltered Québec&#39;s Green Energy Premium: Data Centers Face Steep Power Rate Hikes Québec&#39;s Green Energy Premium: Data Centers Face Steep Power Rate Hikes 📊 Key Data New data center rate : 13¢ per kWh (double the current rate for large-power customers) Blockchain rate : 19.5¢ per kWh Projected demand surge : Data center electricity use expected to grow from 200 MW to over 1,000 MW by 2035 🎯 Expert Consensus Experts would likely conclude that Hydro-Québec&#39;s proposed rate hikes represent a strategic shift to balance industrial growth with social equity, testing whether Québec&#39;s renewable energy premium can sustain its competitive edge in the tech sector. MM Margaret Mitchell Margaret Mitchell: Unfiltered 3 months ago Québec&#39;s Green Energy Premium: Data Centers Face Steep Power Rate Hikes MONTRÉAL, QC – February 19, 2026 – The era of exceptionally cheap power for Québec&#39;s most energy-intensive tech industries is drawing to a close. Hydro-Québec, the province&#39;s public utility, has proposed dramatic rate hikes for large data centers and blockchain operators, signaling a major strategic shift aimed at capturing the true economic value of its vast renewable energy resources. Under the proposal subm"
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-020",
    "sentence": "To prevent these colossal fixed infrastructure and grid expansion costs from being passed onto regular residential consumers—and to politically and economically extract the \"full value\" of the province's green energy premium—Hydro-Québec formally petitioned the provincial energy regulator (Régie de l'énergie) to double the electricity rates for new data centers exceeding 5 MW of capacity.",
    "numeric_tokens": [
      "5 MW"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_009",
        "url": "https://news.hydroquebec.com/news/press-releases/all-quebec/hydro-quebec-proposing-regie-energie-new-rate-large-data-centres-adjustment-rate-cryptographic-use-applied-blockchains.html",
        "matching_tokens": [
          "5 MW"
        ],
        "content_excerpt": "A new rate for data centres and a rate adjustment for blockchains to reflect the value of renewable electricity Direct access to main content Direct access to footer menu All Sites News Contact Us Power Outages Français Login Newsroom Launch Search Menu Login Homepage Press releases Media contacts Media Library Homepage Press releases Media contacts Media Library News Press releases A new rate for data centres and a rate adjustment for blockchains to reflect the value of renewable electricity General news, February 19, 2026 --> Last modified date : February 19, 2026 --> A new rate for data centres and a rate adjustment for blockchains to reflect the value of renewable electricity Montréal – Hydro-Québec is proposing to the Régie de l’énergie a new rate for large data centres and an adjustment of the rate for cryptographic use applied to blockchains. These changes are meant to ensure businesses in these sectors cover the costs associated with their high electricity demand while still paying prices comparable to those elsewhere in North America. This initiative is backed by the government of Québec, which has issued Orders in Council addressing the related economic, social and environmental concerns. Through this approach, Hydro-Québec is managing the growth of its assets responsibly by limiting the impact on its other customer categories. Bloomberg figures reveal the need to take action: in US jurisdictions experiencing strong growth in the data centre sector, electricity bill"
      },
      {
        "evidence_id": "gm_ev_035",
        "url": "https://montreal.citynews.ca/2026/02/19/hydro-quebec-proposes-rate-for-data-centers/",
        "matching_tokens": [
          "5 MW"
        ],
        "content_excerpt": "Hydro-Québec proposes a rate of 13¢/kWh for data centers Skip to main content Montreal Calgary Edmonton Halifax Kitchener Montreal Ottawa Toronto Vancouver Winnipeg About About Us Our Team Contact Contact Us Submit a News Tip News All Local Canada World Watch All Latest Videos Weather Montreal All Montreal Calgary Edmonton Halifax Kitchener Montreal Ottawa Toronto Vancouver Winnipeg About All About Us Our Team Contact All Contact Us Submit a News Tip Watch Live: CityNews at Six Montreal Close Hydro-Québec proposes a rate of 13¢/kWh for data centers Hydro-Québec head offices in downtown Montreal. Jan. 22, 2026. (Martin Daigle, CityNews) By The Canadian Press Posted February 19, 2026 7:41 am. Hydro-Québec has officially proposed a new rate for large data centers, set at 13 cents per kilowatt-hour (kWh), which is about double the price currently paid by customers on the high-power rate. In a press release issued Thursday morning, the Crown corporation asked the Régie de l&#8217;énergie to introduce this new rate, which would apply to data centers consuming more than 5 megawatts (MW). If the Régie de l&#8217;énergie approves its creation, this new rate will be introduced in the second half of 2026. Projects over 5 MW remain subject to a selection process. For data centers already connected to the grid, Hydro-Québec is proposing a gradual transition to the new rate over five years. Related: Quebec: Yes to data centres, but they&#8217;ll have to pay more for electricity Class actio"
      },
      {
        "evidence_id": "gm_ev_064",
        "url": "https://briefglance.com/companies/hydro-quebec/pulses/1493",
        "matching_tokens": [
          "5 MW"
        ],
        "content_excerpt": "Hydro-Québec Responds to Data Center Boom with Rate Hikes — Hydro-Québec | BriefGlance Skip to main content BriefGlance.com INTELLIGENCE Media Center Contact Market pulse Wire Sign In Menu &times; Media Center Contact Wire Sign In Market Pulse Hydro-Québec Hydro-Québec Responds to Data Center Boom with Rate Hikes February 19, 2026 · 6:00 AM Hydro-Québec Responds to Data Center Boom with Rate Hikes Event summary Hydro-Québec is proposing new electricity rates for large data centers (over 5 MW) and blockchain operations. Data center rates will average 13¢/kWh, double the current rate for large-power customers, effective H2 2026 (pending approval). Blockchain rates will rise to an average of 19.5¢/kWh, also effective H2 2026 (pending approval), reflecting energy intensity. Québec anticipates data center electricity consumption to reach over 1,000 MW by 2035, a sevenfold increase. The move is backed by the government of Québec via Orders in Council and aims to prevent electricity bill increases for all customers, as seen in US jurisdictions. The big picture Hydro-Québec&#39;s actions represent a proactive attempt to manage the rapid growth of energy-intensive industries like data centers and blockchain, preventing the cost burden from being passed on to other consumers. The government&#39;s backing underscores a strategic prioritization of energy resource management and economic stability, aligning with concerns about rising electricity costs observed in other North American juri"
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-021",
    "sentence": "Set to take effect in the second half of 2026, the new rate establishes a strict baseline of 13 cents per kilowatt-hour (kWh) for large AI data centers, while cryptographic and blockchain operations face an even steeper, punitive hike to an average of 19.5 cents/kWh.",
    "numeric_tokens": [
      "2026"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_000",
        "url": "https://www.newswire.ca/news-releases/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure-854223505.html",
        "matching_tokens": [
          "2026"
        ],
        "content_excerpt": "TELUS and Government of Canada advance work to scale Canada's sovereign AI infrastructure Accessibility Statement Skip Navigation Resources Investor Relations Journalists Webcasts Français --> Français my CNW&nbsp; Login Register Client Login&nbsp; PR Newswire Amplify™ Next Gen Communications Cloud Cision Communications Cloud® Sign Up Send a Release News Products Contact Search Search When typing in this field, a list of search results will appear and be automatically updated as you type. Searching for your content... No results found. Please change your search terms and try again. Advanced Search News in Focus Browse News Releases All News Releases All Public Company News Releases Overview Multimedia Gallery All Multimedia All Photos All Videos Multimedia Gallery Overview Trending Topics All Trending Topics Business Auto &amp; Transportation All Automotive &amp; Transportation Aerospace, Defense Air Freight Airlines &amp; Aviation Automotive Maritime &amp; Shipbuilding Railroads and Intermodal Transportation Supply Chain/Logistics Transportation, Trucking &amp; Railroad Travel Trucking and Road Transportation Auto &amp; Transportation Overview View All Auto &amp; Transportation Business Technology All Business Technology Blockchain Broadcast Tech Computer &amp; Electronics Computer Hardware Computer Software Data Analytics Electronic Commerce Electronic Components Electronic Design Automation Financial Technology High Tech Security Internet Technology Nanotechnology Networks"
      },
      {
        "evidence_id": "gm_ev_001",
        "url": "https://www.canada.ca/en/innovation-science-economic-development/news/2026/05/government-of-canada-and-telus-advance-work-to-build-sovereign-ai-infrastructure.html",
        "matching_tokens": [
          "2026"
        ],
        "content_excerpt": "Government of Canada and TELUS advance work to build sovereign AI infrastructure - Canada.ca Skip to main content Skip to &#34;About government&#34; Language selection Fran&ccedil;ais fr / Gouvernement du Canada Search Search Canada.ca Search Menu Main Menu Jobs and the workplace Immigration and citizenship Travel and tourism Business and industry Benefits Health Taxes Environment and natural resources National security and defence Culture, history and sport Policing, justice and emergencies Transport and infrastructure Canada and the world Money and finances Science and innovation Manage life events You are here: Canada.ca Government of Canada and TELUS advance work to build sovereign AI infrastructure From: Innovation, Science and Economic Development Canada News release This marks a significant step to bringing large-scale data centre capacity online This marks a significant step to bringing large-scale data centre capacity online May 11, 2026 – Vancouver, British Columbia Globally, industry and government alike are moving quickly to bring large-scale data centre capacity online. Access to cutting-edge compute infrastructure is crucial for maintaining Canada’s leadership in artificial intelligence (AI), empowering researchers and industries to thrive. Today, the Honourable Evan Solomon, Minister of Artificial Intelligence and Digital Innovation and Minister responsible for the Federal Economic Development Agency for Southern Ontario, announced that the Government of Canada"
      },
      {
        "evidence_id": "gm_ev_002",
        "url": "https://nationalmagazine.ca/en-ca/articles/law/in-depth/2026/canada-s-uncertain-digital-future",
        "matching_tokens": [
          "2026"
        ],
        "content_excerpt": "National - CBA National - Canadian Legal Affairs Skip to Content fran&#xE7;ais Search Toggle Navigation CBA Influence All Policy Resolutions Submissions Law All Judiciary Rule of law In-depth Hot topics Ethics Opinion Business &amp; corporate Access to justice Legal market All Regulatory Commentary Corporate Counsel Law Firms Legal Tech Partner Firms People All Profile Q&amp;A The practice All Corporate Counsel Legal education New Law Small and solo Workplace Young lawyers Contact Us Facebook Twitter Linkedin RSS Law In-depth Canada&#x2019;s uncertain digital future Observers say this country must create its own tools to move away from U.S. technology and enhance digital sovereignty, but a lack of political will is standing in the way BY Julie Sobowale 20 Apr. 2026 Just_Super (iStock) Share: Facebook Twitter Linkedin Email Earlier this year, the French government announced it would stop using Zoom, Microsoft Teams, and any other U.S.-based videoconferencing platforms by 2027 and begin using French-based Visio. The decision came after Anton Carniaux, director of public and legal affairs for Microsoft France, testified before the French Senate that, under the U.S. Cloud Act , Microsoft could be forced to hand over data from any country, regardless of where it is stored. Austria, Germany and Switzerland are also racing to find alternatives to U.S.-based technology. Digital sovereignty, which is the protection and control of Canadian data, is quickly becoming the most prominent i"
      }
    ]
  }
]

# Output schema

```yaml
records:
  - claim_id: GM-Q1-T1-XXX
    claim_type: ...
    materiality: ...
    citation_context_match: ...
    verdict: ...
    rationale: ...
    reviewer_confidence: ...
batch_summary:
  total: 7
  per_verdict: {VERIFIED: N, PARTIAL: N, UNSUPPORTED: N, FABRICATED: N, UNREACHABLE: N}
  per_context_match: {yes: N, partial: N, no: N, unverifiable: N}
```
