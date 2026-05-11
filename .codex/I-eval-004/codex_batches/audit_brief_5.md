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

# Claims to audit (batch 5, 7 claims)

[
  {
    "claim_id": "GM-Q1-T1-029",
    "sentence": "Google Cloud Platform (GCP) leverages its Vertex AI platform and deep integration with proprietary silicon (Tensor Processing Units, or TPUs) to power the Gemini model family, earning recognition as a Leader in the 2026 Forrester Wave for Sovereign Cloud Platforms.",
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
    "claim_id": "GM-Q1-T1-030",
    "sentence": "A raw, unmanaged cluster of 1,000 advanced B200 GPUs is exceptionally powerful in theory, but without a mature software ecosystem, federal data scientists must expend vast, highly expensive engineering resources managing container orchestration, load balancing across nodes, model weight distribution, and vital security patching entirely manually.The Government of Canada has astutely recognized this severe vulnerability in its procurement strategy.",
    "numeric_tokens": [
      "1,000"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_000",
        "url": "https://www.newswire.ca/news-releases/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure-854223505.html",
        "matching_tokens": [
          "1,000"
        ],
        "content_excerpt": "TELUS and Government of Canada advance work to scale Canada's sovereign AI infrastructure Accessibility Statement Skip Navigation Resources Investor Relations Journalists Webcasts Français --> Français my CNW&nbsp; Login Register Client Login&nbsp; PR Newswire Amplify™ Next Gen Communications Cloud Cision Communications Cloud® Sign Up Send a Release News Products Contact Search Search When typing in this field, a list of search results will appear and be automatically updated as you type. Searching for your content... No results found. Please change your search terms and try again. Advanced Search News in Focus Browse News Releases All News Releases All Public Company News Releases Overview Multimedia Gallery All Multimedia All Photos All Videos Multimedia Gallery Overview Trending Topics All Trending Topics Business Auto &amp; Transportation All Automotive &amp; Transportation Aerospace, Defense Air Freight Airlines &amp; Aviation Automotive Maritime &amp; Shipbuilding Railroads and Intermodal Transportation Supply Chain/Logistics Transportation, Trucking &amp; Railroad Travel Trucking and Road Transportation Auto &amp; Transportation Overview View All Auto &amp; Transportation Business Technology All Business Technology Blockchain Broadcast Tech Computer &amp; Electronics Computer Hardware Computer Software Data Analytics Electronic Commerce Electronic Components Electronic Design Automation Financial Technology High Tech Security Internet Technology Nanotechnology Networks"
      },
      {
        "evidence_id": "gm_ev_008",
        "url": "https://briefglance.com/articles/qubecs-green-energy-premium-data-centers-face-steep-power-rate-hikes",
        "matching_tokens": [
          "1,000"
        ],
        "content_excerpt": "Québec&#39;s Green Energy Premium: Data Centers Face Steep Power Rate Hikes - BriefGlance.com Skip to main content BriefGlance.com INTELLIGENCE Media Center Contact Market pulse Wire Sign In Menu &times; Media Center Contact Wire Sign In Home Margaret Mitchell: Unfiltered Québec&#39;s Green Energy Premium: Data Centers Face Steep Power Rate Hikes Québec&#39;s Green Energy Premium: Data Centers Face Steep Power Rate Hikes 📊 Key Data New data center rate : 13¢ per kWh (double the current rate for large-power customers) Blockchain rate : 19.5¢ per kWh Projected demand surge : Data center electricity use expected to grow from 200 MW to over 1,000 MW by 2035 🎯 Expert Consensus Experts would likely conclude that Hydro-Québec&#39;s proposed rate hikes represent a strategic shift to balance industrial growth with social equity, testing whether Québec&#39;s renewable energy premium can sustain its competitive edge in the tech sector. MM Margaret Mitchell Margaret Mitchell: Unfiltered 3 months ago Québec&#39;s Green Energy Premium: Data Centers Face Steep Power Rate Hikes MONTRÉAL, QC – February 19, 2026 – The era of exceptionally cheap power for Québec&#39;s most energy-intensive tech industries is drawing to a close. Hydro-Québec, the province&#39;s public utility, has proposed dramatic rate hikes for large data centers and blockchain operators, signaling a major strategic shift aimed at capturing the true economic value of its vast renewable energy resources. Under the proposal subm"
      },
      {
        "evidence_id": "gm_ev_009",
        "url": "https://news.hydroquebec.com/news/press-releases/all-quebec/hydro-quebec-proposing-regie-energie-new-rate-large-data-centres-adjustment-rate-cryptographic-use-applied-blockchains.html",
        "matching_tokens": [
          "1,000"
        ],
        "content_excerpt": "A new rate for data centres and a rate adjustment for blockchains to reflect the value of renewable electricity Direct access to main content Direct access to footer menu All Sites News Contact Us Power Outages Français Login Newsroom Launch Search Menu Login Homepage Press releases Media contacts Media Library Homepage Press releases Media contacts Media Library News Press releases A new rate for data centres and a rate adjustment for blockchains to reflect the value of renewable electricity General news, February 19, 2026 --> Last modified date : February 19, 2026 --> A new rate for data centres and a rate adjustment for blockchains to reflect the value of renewable electricity Montréal – Hydro-Québec is proposing to the Régie de l’énergie a new rate for large data centres and an adjustment of the rate for cryptographic use applied to blockchains. These changes are meant to ensure businesses in these sectors cover the costs associated with their high electricity demand while still paying prices comparable to those elsewhere in North America. This initiative is backed by the government of Québec, which has issued Orders in Council addressing the related economic, social and environmental concerns. Through this approach, Hydro-Québec is managing the growth of its assets responsibly by limiting the impact on its other customer categories. Bloomberg figures reveal the need to take action: in US jurisdictions experiencing strong growth in the data centre sector, electricity bill"
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-031",
    "sentence": "Ultimately, the quality trade-off in 2026 undeniably favors the hyperscalers for immediate, out-of-the-box application development and rapid deployment.",
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
    "claim_id": "GM-Q1-T1-032",
    "sentence": "However, the heavily funded sovereign National Service Layer is actively closing this capability gap, aiming to provide customized, highly secure, and functionally comparable environments optimized specifically for foundational model training and sensitive government inference tasks.Synthesizing the Trilemma for Federal Workloads in 2026The complex decision matrix for deploying federal government AI workloads in 2026 cannot be solved by a uniform, monolithic policy directive.",
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
    "claim_id": "GM-Q1-T1-033",
    "sentence": "For Protected B AI workloads, the optimal trade-off in 2026 heavily favors leveraging the mature, localized hyperscaler ecosystems.Jurisdiction: Hyperscalers have successfully and demonstrably met the Government of Canada's stringent technical requirements for this tier.",
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
    "claim_id": "GM-Q1-T1-034",
    "sentence": "ConclusionThe 2026 landscape of Canadian federal AI compute is defined by the profound tension between the immense gravitational pull of United States hyperscale efficiency and the indispensable, non-negotiable necessity of sovereign jurisdictional control.",
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
    "claim_id": "GM-Q1-T1-035",
    "sentence": "The Government of Canada has astutely recognized that neither path is universally superior, nor can a single architecture satisfy the vast, disparate needs of the modern federal apparatus.The $2 billion Sovereign AI Compute Strategy, underscored by the massive SCIP infrastructure build and the targeted SME support of the AI Compute Access Fund, successfully ensures that Canada will not be entirely dependent on foreign infrastructure for its most critical operations or the cultivation of its domestic innovation ecosystem.",
    "numeric_tokens": [
      "$2 billion"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_026",
        "url": "https://oecd.ai/en/dashboards/policy-initiatives/ai-sovereign-compute-infrastructure-program",
        "matching_tokens": [
          "$2 billion"
        ],
        "content_excerpt": "AI Sovereign Compute Infrastructure Program - OECD.AI Going Digital DPP Blog Live data Policies and initiatives Priority issues Tools Resources About Search AI Risk &amp; Accountability AI has risks and all actors must be accountable. AI, Data &amp; Privacy Data and privacy are primary policy issues for AI. Generative AI Managing the risks and benefits of generative AI. Future of Work How AI can and will affect workers and working environments AI Index The OECD AI will be a synthetic measurement framework on Trustworthy Artificial Intelligence (AI) AI Incidents To manage risks, governments must track and understand AI incidents and hazards. AI in Government Governments are not only AI regulators and investors, but also developers and users. Data Governance Expertise on data governance to promote its safe and faire use in AI Responsible AI The responsible development, use and governance of human-centred AI systems Innovation &amp; Commercialisation How to drive cooperation on AI and transfer research results into products AI Compute and the Environment AI computing capacities and their environmental impact. AI &amp; Health AI can help health systems overcome their most urgent challenges. AI Futures AI’s potential futures. WIPS Programme on Work, Innovation, Productivity and Skills in AI. Catalogue Tools &amp; Metrics Explore tools &amp; metrics to build and deploy AI systems that are trustworthy. AIM: AI Incidents and Hazards Monitor Gain valuable insights on global AI inciden"
      },
      {
        "evidence_id": "gm_ev_043",
        "url": "https://ised-isde.canada.ca/site/ised/en/canadian-sovereign-ai-compute-strategy",
        "matching_tokens": [
          "$2 billion"
        ],
        "content_excerpt": "Canadian Sovereign AI Compute Strategy Skip to main content Skip to \"About this site\" Language selection WxT Language switcher Français fr / Gouvernement du Canada WxT Search form Search Search Menu Main Menu Home You are here Canada.ca Artificial intelligence ecosystem Canadian Sovereign AI Compute Strategy From: Innovation, Science and Economic Development Canada Help define the next chapter of Canada's AI strategy. Take part in the consultation between October 1 and October 31. --> To strengthen Canada's position as a global leader in artificial intelligence (AI), it is essential for Canadian AI industries and researchers to have access to affordable, cutting‑edge compute infrastructure. By boosting access to powerful computing resources right here in Canada, we can drive innovation, create new opportunities and ensure that Canada stays competitive in the global AI race. What is AI compute? AI compute refers to the computational resources required for AI systems to perform tasks, such as processing data, running algorithms and training machine learning models. In other words, AI compute is the technology that powers AI. More compute power means faster and more accurate results. And that means more innovation, more productivity and more opportunity for Canadian AI companies, researchers and talent. That is why the Government of Canada is committed to building a strong and secure AI compute foundation. Budget 2024 announced $2 billion over five years, starting in 2024–25, to"
      },
      {
        "evidence_id": "gm_ev_066",
        "url": "https://www.glennklockwood.com/garden/Canadian-sovereign-AI",
        "matching_tokens": [
          "$2 billion"
        ],
        "content_excerpt": "Canadian sovereign AI Glenn's Digital Garden Search Search !a.data&amp;&amp;!b.data||a.data&amp;&amp;b.data?a.data?.tags?.includes(\\&quot;evergreen\\&quot;)&amp;&amp;!b.data?.tags?.includes(\\&quot;evergreen\\&quot;)?-1:!a.data?.tags?.includes(\\&quot;evergreen\\&quot;)&amp;&amp;b.data?.tags?.includes(\\&quot;evergreen\\&quot;)?1:a.displayName.localeCompare(b.displayName):a.data&amp;&amp;!b.data?1:-1&quot;,&quot;filterFn&quot;:&quot;node=>!(node.data?.tags?.includes(\\&quot;seedling\\&quot;)===!0||node.data?.tags?.includes(\\&quot;unlisted\\&quot;)===!0||node.displayName==\\&quot;entities\\&quot;&amp;&amp;!node.data)&quot;,&quot;mapFn&quot;:&quot;node=>node&quot;}\"> Explorer Home ❯ Canadian sovereign AI Canadian sovereign AI Apr 24, 2026 artificial-intelligence canada History In December 2024, Canada announced a Canadian Sovereign AI Compute Strategy that calls for how to use a $2 billion, five-year investment in sovereign AI. The salient points of the proposal: 1 $700M to support public-private AI partnership projects, awarded on a competitive basis, that expand Canadian datacenters and supporting technology. This is called the AI Compute Challenge . $1B for major capital investments $705 million for a single, large sovereign supercomputing facility called SCIP . A small amount for a secure computing facility to be managed by Shared Services Canada (SSC) and National Research Council of Canada (NRC). $200M of near-term investment to shore up domestic compute infrastructure $300M to subsi"
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
