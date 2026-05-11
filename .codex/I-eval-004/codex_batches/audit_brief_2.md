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

# Claims to audit (batch 2, 7 claims)

[
  {
    "claim_id": "GM-Q1-T1-008",
    "sentence": "When a senior Microsoft executive was asked under oath before the French Senate in June 2025 whether he could guarantee that French government data stored in Microsoft's cloud would never be transmitted to US authorities without French authorization, his answer was unequivocal: \"Non, je ne peux pas le garantir\" (\"No, I cannot guarantee it\").",
    "numeric_tokens": [
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
    "claim_id": "GM-Q1-T1-009",
    "sentence": "To address the jurisdictional gap without fracturing their highly integrated global network architectures, hyperscalers have pioneered a concept that can be termed \"cryptographic sovereignty.\" In 2026, Microsoft launched its Sovereign AI Landing Zone (SAIL) in Canada, backed by an unprecedented $19 billion capital investment pledge.",
    "numeric_tokens": [
      "$19 billion",
      "2026"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_007",
        "url": "https://blogs.microsoft.com/on-the-issues/2025/12/09/microsoft-deepens-its-commitment-to-canada-with-landmark-19b-ai-investment/",
        "matching_tokens": [
          "$19 billion",
          "2026"
        ],
        "content_excerpt": "Microsoft Deepens Its Commitment to Canada with Landmark $19B AI Investment - Microsoft On the Issues Skip to content Skip to main content Microsoft On the Issues About Microsoft Company Timeline Global Diversity &amp; Inclusion Microsoft on the Issues Microsoft Stories Official Microsoft Blog Microsoft Asia Microsoft Europe Microsoft India Microsoft Latin America Microsoft Middle East &amp; Africa Accessibility Blog AI Blog Customer Stories Education Stories Feature Stories Innovation Stories Microsoft Conexiones Microsoft Life Microsoft on the Issues Microsoft Research Microsoft Podcasts Official Microsoft Blog Azure Devices Microsoft 365 Windows Xbox Security Blog AI for Business Microsoft Industry Blogs Accessibility Access to Broadband AI for Good COVID-19 Cybersecurity Digital Safety Fundamental Rights Journalism Open Data Philanthropies Privacy Responsible AI Skills Sustainability United Nations Washington State Cloud Principles Image Gallery Press Releases Microsoft News on Twitter Events Executive Biographies Microsoft CEO Press Contacts Board of Directors Facts About Microsoft Investor Relations Worldwide News Video &amp; Broll Executive Speeches Automotive and Mobility Dynamics 365 Healthcare Manufacturing Microsoft 365 Mixed Reality Philanthropies Surface Telecom Microsoft 365 Azure Copilot Windows Surface Xbox Deals Small Business Support Windows Apps Outlook OneDrive Microsoft Teams OneNote Microsoft Edge Moving from Skype to Teams Computers Shop Xbox Accessorie"
      },
      {
        "evidence_id": "gm_ev_019",
        "url": "https://balsilliepapers.ca/canadian-data/",
        "matching_tokens": [
          "$19 billion",
          "2026"
        ],
        "content_excerpt": "Whose Law Governs Canadian Data? - Balsillie Papers Skip to content Skip to content Main Menu Mandate Editorial Team Podcast Volumes Current Volume Volume 8 Volume 7 Volume 6 Volume 5 Volume 4 Volume 3 Volume 2 Volume 1 Special Reports TransCanada Power Corridor Whose Law Governs Canadian Data? Submissions Whose Law Governs Canadian Data? The CLOUD Act, Executive Agreements and Digital Sovereignty SPECIAL REPORT MARCH 11, 2026 Barry Appleton 1. Executive Summary 1.1 The Core Problem Canadian government data — including national defence communications — can be compelled by US authorities without Canadian judicial review or governmental notification. This is not a hypothetical risk. It is the operational reality created by the US Clarifying Lawful Overseas Use of Data or CLOUD Act of 2018. When a senior Microsoft executive was asked under oath before the French Senate in June 2025 whether he could guarantee that French government data stored in Microsoft’s cloud would never be transmitted to US authorities without French authorization, his answer was unequivocal: “Non, je ne peux pas le garantir” — “No, I cannot guarantee it.” The same is true for Canadian data. 1.2 Why This Matters Now Over 80 percent of Canadian cloud services rely on foreign infrastructure. Critical government systems — including the Department of National Defence’s Defence 365 platform — depend on US-headquartered providers. Canada’s largest telecommunications companies (Rogers, BCE, TELUS), financial servi"
      },
      {
        "evidence_id": "gm_ev_000",
        "url": "https://www.newswire.ca/news-releases/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure-854223505.html",
        "matching_tokens": [
          "2026"
        ],
        "content_excerpt": "TELUS and Government of Canada advance work to scale Canada's sovereign AI infrastructure Accessibility Statement Skip Navigation Resources Investor Relations Journalists Webcasts Français --> Français my CNW&nbsp; Login Register Client Login&nbsp; PR Newswire Amplify™ Next Gen Communications Cloud Cision Communications Cloud® Sign Up Send a Release News Products Contact Search Search When typing in this field, a list of search results will appear and be automatically updated as you type. Searching for your content... No results found. Please change your search terms and try again. Advanced Search News in Focus Browse News Releases All News Releases All Public Company News Releases Overview Multimedia Gallery All Multimedia All Photos All Videos Multimedia Gallery Overview Trending Topics All Trending Topics Business Auto &amp; Transportation All Automotive &amp; Transportation Aerospace, Defense Air Freight Airlines &amp; Aviation Automotive Maritime &amp; Shipbuilding Railroads and Intermodal Transportation Supply Chain/Logistics Transportation, Trucking &amp; Railroad Travel Trucking and Road Transportation Auto &amp; Transportation Overview View All Auto &amp; Transportation Business Technology All Business Technology Blockchain Broadcast Tech Computer &amp; Electronics Computer Hardware Computer Software Data Analytics Electronic Commerce Electronic Components Electronic Design Automation Financial Technology High Tech Security Internet Technology Nanotechnology Networks"
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-010",
    "sentence": "The Domestic Ecosystem: SCALE AI and the Sovereign Compute StrategyTo establish a definitive, legally impregnable alternative to foreign CSPs, the Government of Canada initiated the $2 billion Canadian Sovereign AI Compute Strategy.",
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
  },
  {
    "claim_id": "GM-Q1-T1-011",
    "sentence": "Backed by approximately $890 million directed explicitly toward the Infrastructure Build Layer, SCIP represents a coordinated national effort to repatriate compute capacity and anchor a secure ecosystem.",
    "numeric_tokens": [
      "$890 million"
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
    "claim_id": "GM-Q1-T1-012",
    "sentence": "By late 2025, Scale AI announced a historic, record-breaking $128.5 million CAD funding round to support 44 new applied AI projects, driving collective investments toward the $500 million mark.",
    "numeric_tokens": [
      "$128.5 million",
      "2025",
      "$500 million"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_029",
        "url": "https://www.scaleai.ca/",
        "matching_tokens": [
          "2025",
          "$500 million"
        ],
        "content_excerpt": "Scale AI | Canada’s AI Cluster, promoting artificial intelligence Skip to main content Skip to footer Projects What we do Our investments How to apply for funding Training What we do Our investments How to apply for funding AI Research Chair Program STEM Youth Awareness Program Acceleration What we do Our investments Accelerators &#038; incubators: How to apply for funding About us Who we are Events News Impact Publications Membership Workplace diversity and inclusion FAQ Career Contact Blog IP Why Ecosystem ALL IN Dubai VivaTech Official Page of the Canadian Delegation at Vivatech 2026 Canada’s Delegates Delegation’s Partners Organizations Projects What we do Our investments How to apply for funding Training What we do Our investments How to apply for funding AI Research Chair Program STEM Youth Awareness Program Acceleration What we do Our investments Accelerators &#038; incubators: How to apply for funding About us Who we are Events News Impact Publications Membership Workplace diversity and inclusion FAQ Career Contact Blog IP Why Ecosystem ALL IN Dubai VivaTech Official Page of the Canadian Delegation at Vivatech 2026 Canada’s Delegates Delegation’s Partners Organizations Portal Fr Search... Fr Projects What we do Our investments How to apply for funding Training What we do Our investments How to apply for funding AI Research Chair Program STEM Youth Awareness Program Acceleration What we do Our investments Accelerators &#038; incubators: How to apply for funding About u"
      },
      {
        "evidence_id": "gm_ev_030",
        "url": "https://league.com/newsroom/scale-ai-135m-investment-launch/",
        "matching_tokens": [
          "$128.5 million",
          "2025"
        ],
        "content_excerpt": "League hosts SCALE AI’s historic $129M AI investment launch Skip to content Platform Platform Built to transform the healthcare consumer experience Platform overview Leadership in AI Solutions Agent teams Platform releases Developer program Partners WEBINAR The end of passive AI in healthcare Watch the recording Who We Serve Who We Serve Intuitive member experiences designed for health plans Payers Engage members with experiences that stand out from competitors. Lines of business Use cases Case study Heading Better consumer experience across the healthcare ecosystem Providers Become a provider of choice with an omni-channel patient experience. Consumer Health Be a digital destination for care and establish local health stewardship. Resources Resources Industry news and insights Resource hub A collection of content advancing healthcare consumer experiences. League Connect Content &#038; key takeaways from our annual CX transformation event. Blog Thought leadership &#038; insights on healthcare CX innovation. WEBINAR From care gaps to closed loops Watch the recording Company Company Empowering people to live happier, healthier lives About Newsroom League trust centre Careers REPORT League was named a Leader in CX Platforms For Healthcare Evaluation Learn more Login Talk to sales Login en fr en fr Dec 16, 2025 League hosts launch of SCALE AI’s record-breaking $129M investment to drive Canadian AI innovation Dec 16, 2025 By League Announcement SCALE AI , Canada’s artificial intel"
      },
      {
        "evidence_id": "gm_ev_000",
        "url": "https://www.newswire.ca/news-releases/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure-854223505.html",
        "matching_tokens": [
          "2025"
        ],
        "content_excerpt": "TELUS and Government of Canada advance work to scale Canada's sovereign AI infrastructure Accessibility Statement Skip Navigation Resources Investor Relations Journalists Webcasts Français --> Français my CNW&nbsp; Login Register Client Login&nbsp; PR Newswire Amplify™ Next Gen Communications Cloud Cision Communications Cloud® Sign Up Send a Release News Products Contact Search Search When typing in this field, a list of search results will appear and be automatically updated as you type. Searching for your content... No results found. Please change your search terms and try again. Advanced Search News in Focus Browse News Releases All News Releases All Public Company News Releases Overview Multimedia Gallery All Multimedia All Photos All Videos Multimedia Gallery Overview Trending Topics All Trending Topics Business Auto &amp; Transportation All Automotive &amp; Transportation Aerospace, Defense Air Freight Airlines &amp; Aviation Automotive Maritime &amp; Shipbuilding Railroads and Intermodal Transportation Supply Chain/Logistics Transportation, Trucking &amp; Railroad Travel Trucking and Road Transportation Auto &amp; Transportation Overview View All Auto &amp; Transportation Business Technology All Business Technology Blockchain Broadcast Tech Computer &amp; Electronics Computer Hardware Computer Software Data Analytics Electronic Commerce Electronic Components Electronic Design Automation Financial Technology High Tech Security Internet Technology Nanotechnology Networks"
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-013",
    "sentence": "As of March 2025, 100% of the IP created in the cluster's first 100 projects remained Canadian-owned, ensuring that the algorithmic innovations generated domestically are not immediately absorbed by foreign conglomerates.",
    "numeric_tokens": [
      "100%",
      "2025"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_003",
        "url": "https://www.canada.ca/en/shared-services/corporate/about-us/transparency/departmental-plan/2026-27/shared-services-canada-2026-27-departmental-plan.html",
        "matching_tokens": [
          "100%",
          "2025"
        ],
        "content_excerpt": "Shared Services Canada 2026–27 Departmental Plan - Canada.ca Skip to main content Skip to &#34;About government&#34; Language selection Fran&ccedil;ais fr / Gouvernement du Canada Search Search Canada.ca Search Menu Main Menu Jobs and the workplace Immigration and citizenship Travel and tourism Business and industry Benefits Health Taxes Environment and natural resources National security and defence Culture, history and sport Policing, justice and emergencies Transport and infrastructure Canada and the world Money and finances Science and innovation Manage life events You are here: Canada.ca Shared Services Canada About Shared Services Canada Transparency Departmental plan Shared Services Canada 2026–27 Departmental Plan Expand all Collapse all On this page At a glance From the Minister Plans to deliver on core responsibilities and internal services Core responsibility : Common Government of Canada IT Operations Internal services Department-wide considerations Related government priorities Key risks Planned spending and human resources Spending Funding Future-oriented condensed statement of operations Human resources Supplementary information tables Federal tax expenditures Corporate information Definitions Copyright Information Except as otherwise specifically noted, the information in this publication may be reproduced, in part or in whole and by any means, without charge or further permission from Shared Services Canada, provided that due diligence is exercised to ensure "
      },
      {
        "evidence_id": "gm_ev_020",
        "url": "https://publicsectornetwork.com/insight/cloud-act-and-data-protection-encryption-doesnt-guarantee-sovereignty",
        "matching_tokens": [
          "100%",
          "2025"
        ],
        "content_excerpt": "CLOUD Act and Data Protection: Encryption Doesn’t Guarantee Sovereignty - Insights | Public Sector Network Skip to main content Explore Communities All Communities General Discussion Cyber Security and Risk Management Data, Analytics and AI Digital Services and Customer Experience IT Modernization and Cloud Workforce, Skills and Capability Events Upcoming events Government Innovation Week --> Past event highlights --> Past events Event management services Sponsorship Digital Leaders Series Academy Overview Courses Insights On Demand Marketplace Partner with us For government For academia For industry --> My homepage Communities Communities Toggle communities dropdown All Communities General Discussion Cyber Security and Risk Management Data, Analytics and AI Digital Services and Customer Experience IT Modernization and Cloud Workforce, Skills and Capability Events Upcoming events Government Innovation Week --> Past event highlights --> Past events Event management services Sponsorship Digital Leaders Series Academy Overview Courses Insights On&nbsp;Demand Marketplace Join now Login Menu What are you looking for? Insights | Industry Trends | Cyber Security and Risk Management PARTNER CONTENT CLOUD Act and Data Protection: Encryption Doesn’t Guarantee Sovereignty Data encryption is often presented as a strong solution, especially when data is entrusted to a U.S.-based cloud provider. But does encryption truly guarantee digital sovereignty? Laura Maltais-provençal 17 February 20"
      },
      {
        "evidence_id": "gm_ev_046",
        "url": "https://ised-isde.canada.ca/site/ised/en/canadian-sovereign-ai-compute-strategy/ai-compute-access-fund/program-guide-ai-compute-access-fund",
        "matching_tokens": [
          "100%",
          "2025"
        ],
        "content_excerpt": "Program Guide: AI Compute Access Fund Skip to main content Skip to \"About this site\" Language selection WxT Language switcher Français fr / Gouvernement du Canada WxT Search form Search Search Menu Main Menu Home You are here Canada.ca Artificial intelligence ecosystem Canadian Sovereign AI Compute Strategy AI Compute Access Fund Program Guide: AI Compute Access Fund Current status: Closed The AI Compute Access Fund is not currently accepting applications. The most recent Call for Proposals closed at 11:59pm ET on July 31, 2025 and has received a high degree of interest and proposals representing projects from across Canada that span multiple industries. Review and assessment of applications is ongoing. Sign up to receive program updates . Table of contents Program Description 1.1 Description &amp; Objectives 1.2 Eligibility criteria 1.3 Eligible activities 1.4 Financial support 1.5 Eligible costs 1.6 Ineligible costs Submitting an Application 2.1 Competitive process 2.2 Sign up, create an account and verify your identity 2.3 Submit your statement of interest 2.4 Submit a full application Assessment and Selection 3.1 Due diligence and benefits assessment 3.2 Recipient selection and prioritization 3.3 Attributes of a strong proposal 3.4 Intellectual Property obligations Signing a Contribution Agreement 4.1 Accepting the terms and conditions Managing a Project funded by ISED 5.1 Reporting requirements 5.2 Submitting claims for reimbursement Resources and Contact information 6.1"
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-014",
    "sentence": "Following the rapid, unprecedented sell-out of its initial facility in Rimouski, Quebec, TELUS is executing a massive expansion into British Columbia with a cluster projected to scale to an astonishing 60,000 high-performance GPUs and 150 megawatts of power demand by 2032.",
    "numeric_tokens": [
      "60,000",
      "150 megawatts"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_000",
        "url": "https://www.newswire.ca/news-releases/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure-854223505.html",
        "matching_tokens": [
          "60,000"
        ],
        "content_excerpt": "TELUS and Government of Canada advance work to scale Canada's sovereign AI infrastructure Accessibility Statement Skip Navigation Resources Investor Relations Journalists Webcasts Français --> Français my CNW&nbsp; Login Register Client Login&nbsp; PR Newswire Amplify™ Next Gen Communications Cloud Cision Communications Cloud® Sign Up Send a Release News Products Contact Search Search When typing in this field, a list of search results will appear and be automatically updated as you type. Searching for your content... No results found. Please change your search terms and try again. Advanced Search News in Focus Browse News Releases All News Releases All Public Company News Releases Overview Multimedia Gallery All Multimedia All Photos All Videos Multimedia Gallery Overview Trending Topics All Trending Topics Business Auto &amp; Transportation All Automotive &amp; Transportation Aerospace, Defense Air Freight Airlines &amp; Aviation Automotive Maritime &amp; Shipbuilding Railroads and Intermodal Transportation Supply Chain/Logistics Transportation, Trucking &amp; Railroad Travel Trucking and Road Transportation Auto &amp; Transportation Overview View All Auto &amp; Transportation Business Technology All Business Technology Blockchain Broadcast Tech Computer &amp; Electronics Computer Hardware Computer Software Data Analytics Electronic Commerce Electronic Components Electronic Design Automation Financial Technology High Tech Security Internet Technology Nanotechnology Networks"
      },
      {
        "evidence_id": "gm_ev_031",
        "url": "https://www.ipolitics.ca/2026/05/11/ottawa-taps-telus-to-help-build-sovereign-ai-computing-power/",
        "matching_tokens": [
          "150 megawatts"
        ],
        "content_excerpt": "Ottawa taps TELUS to help build sovereign AI computing power - iPolitics Skip to content Log In Account Subscribe Subscribe News Opinions Podcasts INTEL News Opinions Liberal Leadership 2025 Podcasts INTEL Log In Account News Ottawa taps TELUS to help build sovereign AI computing power Expert praises federal government for moving ahead in its call to build large-scale sovereign data centres, although he says it does not address critical IP concerns. Published May 11th, 2026 at 4:17pm Aya Dufour and Sydney Ko Share on Facebook Share on Twitter Share on LinkedIn Share via Email Evan Solomon, Minister of Artificial Intelligence and Digital Innovation (left), speaks with Darren Entwistle, President and CEO of TELUS (centre) and MP Taleeb Noormohamed after plans for three large-scale AI data centre project in British Columbia during a press event in Vancouver on Monday, May 11, 2026. THE CANADIAN PRESS/Rich Lam Telecommunications giant TELUS is moving forward on plans to grow its AI data centre footprint in B.C, with an expansion in Kamloops and the launch of new facilities in Mount Pleasant and downtown Vancouver. The company’s AI cluster pitch is the first to be supported by the federal government as part of its calls for large-scale AI centre proposals. At a Vancouver-area announcement Monday, federal Artificial Intelligence and Digital Innovation Minister Evan Solomon said “Canada cannot compete in the AI company without the infrastructure to back it up.” “By advancing this pr"
      },
      {
        "evidence_id": "gm_ev_032",
        "url": "https://investingnews.com/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure/",
        "matching_tokens": [
          "60,000"
        ],
        "content_excerpt": "Raven.config('https://6b64f5cc8af542cbb920e0238864390a@sentry.io/147999').install(); TELUS and Government of Canada advance work to scale Canada&#x27;s sovereign AI infrastructure | INN Connect with us Information About Us Contact Us Careers Partnerships Advertise With Us Authors Browse Topics Events Disclaimer Privacy Policy Australia North America World Login Investing News Network Your trusted source for investing success North America Australia World My INN Videos Companies Press Releases Private Placements SUBSCRIBE Reports &amp; Guides Market Outlook Reports Investing Guides Button Resource Precious Metals Battery Metals Base Metals Energy Critical Minerals Tech Life Science Market Market Market News Market Stocks Market Market Market News Market Stocks Home &gt; Market News &gt; TELUS and Government of Canada advance work to scale Canada&#39;s sovereign AI infrastructure Investing News Network May 11, 2026 With Canada&#39;s first Sovereign AI Factory in Rimouski, Quebec, now sold out, Telus is expanding its sovereign AI infrastructure with three world-class facilities in B.C. Designed to be the world&#39;s most sustainable sovereign data centres, the cluster will scale to over 60,000 GPUs and 150 MW by 2032 Telus is advancing work with the Government of Canada on a proposed Sovereign AI Factory cluster under the federal Enabling Large-Scale Sovereign AI Data Centres initiative a program designed to build the sovereign, high-performance AI compute infrastructure Canada "
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
