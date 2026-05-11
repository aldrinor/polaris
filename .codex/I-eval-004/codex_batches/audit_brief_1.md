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

# Claims to audit (batch 1, 7 claims)

[
  {
    "claim_id": "GM-Q1-T1-001",
    "sentence": "**Question:** What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026? --- I've completed your research.",
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
    "claim_id": "GM-Q1-T1-002",
    "sentence": "HyperscalerThe 2026 AI Compute Trilemma: Navigating Cost, Quality, and Jurisdiction in Canada's Federal AI WorkloadsIntroduction: The Sovereign Compute Imperative in 2026As artificial intelligence transitions from a frontier experimental capability to a foundational element of public infrastructure, the Canadian federal government is confronting a profound architectural and policy trilemma.",
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
    "claim_id": "GM-Q1-T1-003",
    "sentence": "In 2026, this dynamic is encapsulated by the strategic choice between cultivating a domestic, sovereign AI compute ecosystem—anchored by massive federal initiatives like the Artificial Intelligence Sovereign Compute Infrastructure Program (SCIP) and industry clusters like SCALE AI—versus leveraging the immense scale, ecosystem maturity, and localized cryptographic adaptations of United States-headquartered hyperscalers such as Microsoft Azure, Amazon Web Services (AWS), and Google Cloud Platform (GCP).The stakes in 2026 extend far beyond the mechanics of public procurement; they encompass national security, economic competitiveness, and the absolute preservation of domestic intellectual property.",
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
    "claim_id": "GM-Q1-T1-004",
    "sentence": "By the end of 2025, total global AI data center power capacity exceeded 30 gigawatts—a figure comparable to the peak power usage of entire industrialized states such as New York, and substantially larger than the baseline demand of many developed nations.",
    "numeric_tokens": [
      "30 gigawatts",
      "2025"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_000",
        "url": "https://www.newswire.ca/news-releases/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure-854223505.html",
        "matching_tokens": [
          "2025"
        ],
        "content_excerpt": "TELUS and Government of Canada advance work to scale Canada's sovereign AI infrastructure Accessibility Statement Skip Navigation Resources Investor Relations Journalists Webcasts Français --> Français my CNW&nbsp; Login Register Client Login&nbsp; PR Newswire Amplify™ Next Gen Communications Cloud Cision Communications Cloud® Sign Up Send a Release News Products Contact Search Search When typing in this field, a list of search results will appear and be automatically updated as you type. Searching for your content... No results found. Please change your search terms and try again. Advanced Search News in Focus Browse News Releases All News Releases All Public Company News Releases Overview Multimedia Gallery All Multimedia All Photos All Videos Multimedia Gallery Overview Trending Topics All Trending Topics Business Auto &amp; Transportation All Automotive &amp; Transportation Aerospace, Defense Air Freight Airlines &amp; Aviation Automotive Maritime &amp; Shipbuilding Railroads and Intermodal Transportation Supply Chain/Logistics Transportation, Trucking &amp; Railroad Travel Trucking and Road Transportation Auto &amp; Transportation Overview View All Auto &amp; Transportation Business Technology All Business Technology Blockchain Broadcast Tech Computer &amp; Electronics Computer Hardware Computer Software Data Analytics Electronic Commerce Electronic Components Electronic Design Automation Financial Technology High Tech Security Internet Technology Nanotechnology Networks"
      },
      {
        "evidence_id": "gm_ev_001",
        "url": "https://www.canada.ca/en/innovation-science-economic-development/news/2026/05/government-of-canada-and-telus-advance-work-to-build-sovereign-ai-infrastructure.html",
        "matching_tokens": [
          "2025"
        ],
        "content_excerpt": "Government of Canada and TELUS advance work to build sovereign AI infrastructure - Canada.ca Skip to main content Skip to &#34;About government&#34; Language selection Fran&ccedil;ais fr / Gouvernement du Canada Search Search Canada.ca Search Menu Main Menu Jobs and the workplace Immigration and citizenship Travel and tourism Business and industry Benefits Health Taxes Environment and natural resources National security and defence Culture, history and sport Policing, justice and emergencies Transport and infrastructure Canada and the world Money and finances Science and innovation Manage life events You are here: Canada.ca Government of Canada and TELUS advance work to build sovereign AI infrastructure From: Innovation, Science and Economic Development Canada News release This marks a significant step to bringing large-scale data centre capacity online This marks a significant step to bringing large-scale data centre capacity online May 11, 2026 – Vancouver, British Columbia Globally, industry and government alike are moving quickly to bring large-scale data centre capacity online. Access to cutting-edge compute infrastructure is crucial for maintaining Canada’s leadership in artificial intelligence (AI), empowering researchers and industries to thrive. Today, the Honourable Evan Solomon, Minister of Artificial Intelligence and Digital Innovation and Minister responsible for the Federal Economic Development Agency for Southern Ontario, announced that the Government of Canada"
      },
      {
        "evidence_id": "gm_ev_003",
        "url": "https://www.canada.ca/en/shared-services/corporate/about-us/transparency/departmental-plan/2026-27/shared-services-canada-2026-27-departmental-plan.html",
        "matching_tokens": [
          "2025"
        ],
        "content_excerpt": "Shared Services Canada 2026–27 Departmental Plan - Canada.ca Skip to main content Skip to &#34;About government&#34; Language selection Fran&ccedil;ais fr / Gouvernement du Canada Search Search Canada.ca Search Menu Main Menu Jobs and the workplace Immigration and citizenship Travel and tourism Business and industry Benefits Health Taxes Environment and natural resources National security and defence Culture, history and sport Policing, justice and emergencies Transport and infrastructure Canada and the world Money and finances Science and innovation Manage life events You are here: Canada.ca Shared Services Canada About Shared Services Canada Transparency Departmental plan Shared Services Canada 2026–27 Departmental Plan Expand all Collapse all On this page At a glance From the Minister Plans to deliver on core responsibilities and internal services Core responsibility : Common Government of Canada IT Operations Internal services Department-wide considerations Related government priorities Key risks Planned spending and human resources Spending Funding Future-oriented condensed statement of operations Human resources Supplementary information tables Federal tax expenditures Corporate information Definitions Copyright Information Except as otherwise specifically noted, the information in this publication may be reproduced, in part or in whole and by any means, without charge or further permission from Shared Services Canada, provided that due diligence is exercised to ensure "
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-005",
    "sentence": "Within this constrained and fiercely competitive global market, Canada has launched a $2 billion Sovereign AI Compute Strategy to secure domestic capacity, committing approximately $890 million to the Infrastructure Build Layer of SCIP alone.",
    "numeric_tokens": [
      "$890 million",
      "$2 billion"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_005",
        "url": "https://ised-isde.canada.ca/site/ised/en/ai-sovereign-compute-infrastructure-program",
        "matching_tokens": [
          "$890 million"
        ],
        "content_excerpt": "AI Sovereign Compute Infrastructure Program Skip to main content Skip to \"About this site\" Language selection WxT Language switcher Français fr / Gouvernement du Canada WxT Search form Search Search Menu Main Menu Home You are here Canada.ca Artificial intelligence ecosystem AI Sovereign Compute Infrastructure Program On this page About the AI Sovereign Compute Infrastructure Program Available funding Call for applications Contact us Related links About the AI Sovereign Compute Infrastructure Program The AI Sovereign Compute Infrastructure Program (SCIP) is a key initiative under the Canadian Sovereign AI Compute Strategy that advances Canada's leadership in AI by delivering on historic investments from Budget 2024 and Budget 2025. This program is being delivered, in part, through an open call for applications to build a large-scale sovereign public AI supercomputer for Canadian researchers and innovators. Through this initiative, the Government of Canada will improve access to advanced computing for Canada's world-class researchers and innovative firms developing novel AI solutions or applications, to spur scientific discovery and economic growth. This investment will: give Canadian researchers the compute they need to undertake transformative AI projects; support access for innovative Canadian businesses and AI-related R&amp;D; enhance Canadian sovereignty and resilience; allow for the integration of Canadian technologies; and accelerate the build-out of national public AI "
      },
      {
        "evidence_id": "gm_ev_006",
        "url": "https://ised-isde.canada.ca/site/ised/en/program-guide-artificial-intelligence-sovereign-compute-infrastructure-program-scip",
        "matching_tokens": [
          "$890 million"
        ],
        "content_excerpt": "Program guide: Artificial Intelligence Sovereign Compute Infrastructure Program (SCIP) Skip to main content Skip to \"About this site\" Language selection WxT Language switcher Français fr / Gouvernement du Canada WxT Search form Search Search Menu Main Menu Home You are here Canada.ca Artificial intelligence ecosystem Program guide: Artificial Intelligence Sovereign Compute Infrastructure Program (SCIP) Table of contents Introduction Program description a. Program objectives b. Priorities c. Program scope d. Funding available Program requirements a. Sovereignty requirements b. Eligible applicants c. Eligible activities d. Eligible costs Application requirements Section 1: Applicant information Section 2: List of partners Section 3: Applicant and partners profile Section 4: Application summary Section 5: Technical requirements Section 6: Sovereignty requirements Section 7: Other application requirements Section 8: Source of funds Section 9: Estimated costs Section 10: List of attachments Section 11: Authorization and certification Application process a. Accessing the form and deadline Application assessment Initial screening Technical execution and priorities assessment Detailed description of program layers Introduction This program guide is intended to assist applicants in the completion of the application form for the Artificial Intelligence Sovereign Compute Infrastructure Program (SCIP). It provides information on the program, the application form, the process for submitti"
      },
      {
        "evidence_id": "gm_ev_025",
        "url": "https://grantedai.com/grants/ai-sovereign-compute-infrastructure-program-scip-innovation-science-and-economic-developm-57de806e",
        "matching_tokens": [
          "$890 million"
        ],
        "content_excerpt": "AI Sovereign Compute Infrastructure Program (SCIP) (2026) | Granted AI 1,000+ Opportunities Find the right grant Search federal, foundation, and corporate grants with AI — or browse by agency, topic, and state. Granted is making fundraising less tedious, more accessible, and more successful for everyone. Product AI Grant Writing Features Technology Data Coverage Data API Security Pricing FAQ Solutions For Researchers For Nonprofits For K-12 Schools For Environmental Orgs For SBIR Applicants For Farmers &amp; Agriculture First-Time Applicants Compare vs. Candid vs. Instrumentl vs. ChatGPT vs. Grant Writers vs. Grantable vs. GrantBoost Free Tools Find Grants Readiness Quiz Deadline Calendar Cost Calculator News Blog Learning Center Templates Browse Foundations Competitive Intel Foundation Maps Federal Awards Funded Research NIH Funding Rates Grant Success Rates Clinical Trials World Bank Projects EU Erasmus+ © 2026 Granted AI Contact Privacy Terms @GrantedAI Granted is making fundraising less tedious, more accessible, and more successful for everyone. Product AI Grant Writing Features Technology Data Coverage Data API Security Pricing FAQ Solutions For Researchers For Nonprofits For K-12 Schools For Environmental Orgs For SBIR Applicants For Farmers &amp; Agriculture First-Time Applicants Compare vs. Candid vs. Instrumentl vs. ChatGPT vs. Grant Writers vs. Grantable vs. GrantBoost Free Tools Find Grants Readiness Quiz Deadline Calendar Cost Calculator News Blog Learning Center "
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-006",
    "sentence": "Microsoft's unprecedented $19 billion commitment to Canada introduces localized cloud controls, confidential computing enclaves, and contractual legal shields designed to seamlessly mimic the benefits of physical sovereignty while retaining global cloud agility.",
    "numeric_tokens": [
      "$19 billion"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_007",
        "url": "https://blogs.microsoft.com/on-the-issues/2025/12/09/microsoft-deepens-its-commitment-to-canada-with-landmark-19b-ai-investment/",
        "matching_tokens": [
          "$19 billion"
        ],
        "content_excerpt": "Microsoft Deepens Its Commitment to Canada with Landmark $19B AI Investment - Microsoft On the Issues Skip to content Skip to main content Microsoft On the Issues About Microsoft Company Timeline Global Diversity &amp; Inclusion Microsoft on the Issues Microsoft Stories Official Microsoft Blog Microsoft Asia Microsoft Europe Microsoft India Microsoft Latin America Microsoft Middle East &amp; Africa Accessibility Blog AI Blog Customer Stories Education Stories Feature Stories Innovation Stories Microsoft Conexiones Microsoft Life Microsoft on the Issues Microsoft Research Microsoft Podcasts Official Microsoft Blog Azure Devices Microsoft 365 Windows Xbox Security Blog AI for Business Microsoft Industry Blogs Accessibility Access to Broadband AI for Good COVID-19 Cybersecurity Digital Safety Fundamental Rights Journalism Open Data Philanthropies Privacy Responsible AI Skills Sustainability United Nations Washington State Cloud Principles Image Gallery Press Releases Microsoft News on Twitter Events Executive Biographies Microsoft CEO Press Contacts Board of Directors Facts About Microsoft Investor Relations Worldwide News Video &amp; Broll Executive Speeches Automotive and Mobility Dynamics 365 Healthcare Manufacturing Microsoft 365 Mixed Reality Philanthropies Surface Telecom Microsoft 365 Azure Copilot Windows Surface Xbox Deals Small Business Support Windows Apps Outlook OneDrive Microsoft Teams OneNote Microsoft Edge Moving from Skype to Teams Computers Shop Xbox Accessorie"
      },
      {
        "evidence_id": "gm_ev_019",
        "url": "https://balsilliepapers.ca/canadian-data/",
        "matching_tokens": [
          "$19 billion"
        ],
        "content_excerpt": "Whose Law Governs Canadian Data? - Balsillie Papers Skip to content Skip to content Main Menu Mandate Editorial Team Podcast Volumes Current Volume Volume 8 Volume 7 Volume 6 Volume 5 Volume 4 Volume 3 Volume 2 Volume 1 Special Reports TransCanada Power Corridor Whose Law Governs Canadian Data? Submissions Whose Law Governs Canadian Data? The CLOUD Act, Executive Agreements and Digital Sovereignty SPECIAL REPORT MARCH 11, 2026 Barry Appleton 1. Executive Summary 1.1 The Core Problem Canadian government data — including national defence communications — can be compelled by US authorities without Canadian judicial review or governmental notification. This is not a hypothetical risk. It is the operational reality created by the US Clarifying Lawful Overseas Use of Data or CLOUD Act of 2018. When a senior Microsoft executive was asked under oath before the French Senate in June 2025 whether he could guarantee that French government data stored in Microsoft’s cloud would never be transmitted to US authorities without French authorization, his answer was unequivocal: “Non, je ne peux pas le garantir” — “No, I cannot guarantee it.” The same is true for Canadian data. 1.2 Why This Matters Now Over 80 percent of Canadian cloud services rely on foreign infrastructure. Critical government systems — including the Department of National Defence’s Defence 365 platform — depend on US-headquartered providers. Canada’s largest telecommunications companies (Rogers, BCE, TELUS), financial servi"
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-007",
    "sentence": "The Extraterritorial Reach of the US CLOUD ActThe primary catalyst for Canada's aggressive sovereign compute push is the United States Clarifying Lawful Overseas Use of Data (CLOUD) Act of 2018.",
    "numeric_tokens": [
      "2018"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_013",
        "url": "https://www.blg.com/en/insights/2026/04/data-sovereignty-and-the-cloud-act-what-canadian-organizations-should-know",
        "matching_tokens": [
          "2018"
        ],
        "content_excerpt": "Data sovereignty in Canada and the CLOUD Act (2026) | BLG Skip Links Clear Search Loading Close People &nbsp; People Services &nbsp; Services Industries Back Industries Agribusiness Education Energy - Oil &amp; Gas Energy - Power Financial Services Forestry Government &amp; Public Sector Health Care &amp; Life Sciences Infrastructure Mining Private Equity &amp; Venture Capital Retail &amp; Hospitality Sports &amp; Gaming Law Technology Transportation Practice Areas Back Practice Areas Banking &amp; Financial Services Environmental, Social and Governance (ESG) Capital Markets Commercial Real Estate Competition/Antitrust and Foreign Investment Construction Corporate Commercial Cybersecurity, Privacy &amp; Data Security Disputes Environmental Health Law Indigenous Law Information Technology Insolvency &amp; Restructuring Intellectual Property International Trade &amp; Investment Investment Management Labour &amp; Employment Mergers &amp; Acquisitions Municipal &amp; Land Use Planning Private Client Projects Tax International Back International China India Japan Korea Latin America &amp; Caribbean United Kingdom United States View International Services Additional Services Back Additional Services Beyond Consulting Beyond Contract Review Beyond Legal Talent Beyond Lending eDiscovery Legal Translation Services BLG Beyond Insights &nbsp; Insights Careers &nbsp; Careers Legal Professionals Find out why BLG is the perfect place for experienced lawyers and new graduates to build a car"
      },
      {
        "evidence_id": "gm_ev_014",
        "url": "https://www.osler.com/en/insights/reports/2025-legal-outlook/data-sovereignty-looking-to-the-past-as-canada-decides-how-to-move-forward/",
        "matching_tokens": [
          "2018"
        ],
        "content_excerpt": "Data sovereignty: looking to the past as Canada decides how to move forward - Osler, Hoskin &amp; Harcourt LLP Search for: CONTACT US SUBSCRIBE ALUMNI NETWORK Skip to content Main Navigation People Expertise View all expertise Services Advertising and Marketing Artificial Intelligence Capital Markets Charities and Not-for-Profit Organizations Climate Change, Carbon Markets and Environmental Finance Commercial Real Estate Commercial Technology Transactions Competition and Foreign Investment Construction Corporate Governance Digital Assets and Blockchain Disputes Distribution and Supply Chain Services Emerging and High Growth Companies Employment and Labour Environmental Disputes and Enforcement Executive Compensation Financial Institution Transactions Financial Services Franchise French Language Laws Insolvency and Restructuring Intellectual Property International Trade Investment Funds Major Projects Mergers and Acquisitions Municipal, Land Use Planning and Development Pension Fund Investments Pensions and Benefits Privacy and Data Management Private Client Private Equity Project Finance Public Private Partnerships (P3) Regulatory, Indigenous and Environmental Risk Management and Crisis Response Tax Industries Agribusiness Automotive Banking and Financial Services Data Centres Defence, Security and Aerospace E-mobility Energy Food and Beverage Gaming Government and Public Sector Health Hydrogen and Alternative Fuels Infrastructure Investment Management Manufacturing Media and"
      },
      {
        "evidence_id": "gm_ev_015",
        "url": "https://aws.amazon.com/compliance/cloud-act/",
        "matching_tokens": [
          "2018"
        ],
        "content_excerpt": "Clarifying Lawful Overseas Use of Data (CLOUD) Act - Amazon Web Services Skip to main content Filter: All English Contact us AWS Marketplace Support My account Search Filter: All Sign in to console Create account AWS Cloud Security Security Services Use Cases Compliance Data Protection Blog More AWS Cloud Security Compliance Programs Clarifying Lawful Overseas Use of Data (CLOUD) Act Overview On&nbsp;March 23, 2018, the United States (U.S.) Congress passed the Clarifying Lawful Overseas Use of Data Act (CLOUD Act), which updated the legal framework used by law enforcement authorities to request data held by certain service providers. Importantly the CLOUD Act: Has resulted in zero disclosures of AWS enterprise or government customer content stored outside the U.S. to the U.S. government, since we started reporting the statistic in 2020. Does not give the U.S. government or any government unfettered or automatic access to data, including data stored in the cloud. Is not, despite its name, specifically targeted at infrastructure cloud service providers; rather, the legislation applies to a broad range of online service providers. It also applies to any service provider with operations in the U.S., not just companies with U.S. headquarters. Does not limit technical measures and operational controls AWS offers to customers to prevent access to customer data. As we disclose in our transparency reports , AWS receives a limited number of requests that result in the disclosure of cus"
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
