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

# Claims to audit (batch 4, 7 claims)

[
  {
    "claim_id": "GM-Q1-T1-022",
    "sentence": "The table below illustrates the narrowing gap between Canadian and US power pricing.JurisdictionSector ClassRate (cents/kWh)Strategic Impact on AI WorkloadsQuebec (H2 2026)Large Data Center (>5 MW)13.00¢Eliminates historical arbitrage; forces competition on sovereignty value.Texas (May 2026)Commercial10.77¢Highly attractive for hyperscale builds due to deregulated energy market.Virginia (May 2026)Commercial11.44¢Intense cluster density maintains competitive rates despite massive demand.US National AvgCommercial14.12¢Represents the baseline operating cost for broadly distributed hyperscale zones.Quebec (Crypto)Blockchain/Crypto19.50¢Punitive rate designed to force out low-economic-benefit workloads.Export to SheetsFrontier Hardware: The Economics of the NVIDIA Blackwell B200Beyond foundational power constraints, the silicon hardware itself dictates the ultimate cost-quality equation.",
    "numeric_tokens": [
      "5 MW",
      "2026"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_009",
        "url": "https://news.hydroquebec.com/news/press-releases/all-quebec/hydro-quebec-proposing-regie-energie-new-rate-large-data-centres-adjustment-rate-cryptographic-use-applied-blockchains.html",
        "matching_tokens": [
          "5 MW",
          "2026"
        ],
        "content_excerpt": "A new rate for data centres and a rate adjustment for blockchains to reflect the value of renewable electricity Direct access to main content Direct access to footer menu All Sites News Contact Us Power Outages Français Login Newsroom Launch Search Menu Login Homepage Press releases Media contacts Media Library Homepage Press releases Media contacts Media Library News Press releases A new rate for data centres and a rate adjustment for blockchains to reflect the value of renewable electricity General news, February 19, 2026 --> Last modified date : February 19, 2026 --> A new rate for data centres and a rate adjustment for blockchains to reflect the value of renewable electricity Montréal – Hydro-Québec is proposing to the Régie de l’énergie a new rate for large data centres and an adjustment of the rate for cryptographic use applied to blockchains. These changes are meant to ensure businesses in these sectors cover the costs associated with their high electricity demand while still paying prices comparable to those elsewhere in North America. This initiative is backed by the government of Québec, which has issued Orders in Council addressing the related economic, social and environmental concerns. Through this approach, Hydro-Québec is managing the growth of its assets responsibly by limiting the impact on its other customer categories. Bloomberg figures reveal the need to take action: in US jurisdictions experiencing strong growth in the data centre sector, electricity bill"
      },
      {
        "evidence_id": "gm_ev_035",
        "url": "https://montreal.citynews.ca/2026/02/19/hydro-quebec-proposes-rate-for-data-centers/",
        "matching_tokens": [
          "5 MW",
          "2026"
        ],
        "content_excerpt": "Hydro-Québec proposes a rate of 13¢/kWh for data centers Skip to main content Montreal Calgary Edmonton Halifax Kitchener Montreal Ottawa Toronto Vancouver Winnipeg About About Us Our Team Contact Contact Us Submit a News Tip News All Local Canada World Watch All Latest Videos Weather Montreal All Montreal Calgary Edmonton Halifax Kitchener Montreal Ottawa Toronto Vancouver Winnipeg About All About Us Our Team Contact All Contact Us Submit a News Tip Watch Live: CityNews at Six Montreal Close Hydro-Québec proposes a rate of 13¢/kWh for data centers Hydro-Québec head offices in downtown Montreal. Jan. 22, 2026. (Martin Daigle, CityNews) By The Canadian Press Posted February 19, 2026 7:41 am. Hydro-Québec has officially proposed a new rate for large data centers, set at 13 cents per kilowatt-hour (kWh), which is about double the price currently paid by customers on the high-power rate. In a press release issued Thursday morning, the Crown corporation asked the Régie de l&#8217;énergie to introduce this new rate, which would apply to data centers consuming more than 5 megawatts (MW). If the Régie de l&#8217;énergie approves its creation, this new rate will be introduced in the second half of 2026. Projects over 5 MW remain subject to a selection process. For data centers already connected to the grid, Hydro-Québec is proposing a gradual transition to the new rate over five years. Related: Quebec: Yes to data centres, but they&#8217;ll have to pay more for electricity Class actio"
      },
      {
        "evidence_id": "gm_ev_064",
        "url": "https://briefglance.com/companies/hydro-quebec/pulses/1493",
        "matching_tokens": [
          "5 MW",
          "2026"
        ],
        "content_excerpt": "Hydro-Québec Responds to Data Center Boom with Rate Hikes — Hydro-Québec | BriefGlance Skip to main content BriefGlance.com INTELLIGENCE Media Center Contact Market pulse Wire Sign In Menu &times; Media Center Contact Wire Sign In Market Pulse Hydro-Québec Hydro-Québec Responds to Data Center Boom with Rate Hikes February 19, 2026 · 6:00 AM Hydro-Québec Responds to Data Center Boom with Rate Hikes Event summary Hydro-Québec is proposing new electricity rates for large data centers (over 5 MW) and blockchain operations. Data center rates will average 13¢/kWh, double the current rate for large-power customers, effective H2 2026 (pending approval). Blockchain rates will rise to an average of 19.5¢/kWh, also effective H2 2026 (pending approval), reflecting energy intensity. Québec anticipates data center electricity consumption to reach over 1,000 MW by 2035, a sevenfold increase. The move is backed by the government of Québec via Orders in Council and aims to prevent electricity bill increases for all customers, as seen in US jurisdictions. The big picture Hydro-Québec&#39;s actions represent a proactive attempt to manage the rapid growth of energy-intensive industries like data centers and blockchain, preventing the cost burden from being passed on to other consumers. The government&#39;s backing underscores a strategic prioritization of energy resource management and economic stability, aligning with concerns about rising electricity costs observed in other North American juri"
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-023",
    "sentence": "In 2026, the NVIDIA B200 Blackwell architecture has become the undisputed, indispensable standard for frontier AI workloads, completely eclipsing the previous generation's H100 Hopper chips.",
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
    "claim_id": "GM-Q1-T1-024",
    "sentence": "In stark contrast, the B200 delivers roughly 57 tokens per second—a nearly 140% massive increase in raw throughput.",
    "numeric_tokens": [
      "140%"
    ],
    "candidate_sources": []
  },
  {
    "claim_id": "GM-Q1-T1-025",
    "sentence": "Consequently, while the B200 hardware commands a significant premium rental price—averaging $4.50 to $6.00 per hour for on-demand instances across global cloud providers, and soaring up to $9.86/hr depending on the cluster size and commitment duration—the ultimate cost-per-token generated actually plummets due to its vast efficiency gains.",
    "numeric_tokens": [
      "$9.86",
      "$4.50",
      "$6.00"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_076",
        "url": "https://lambda.ai/pricing",
        "matching_tokens": [
          "$9.86"
        ],
        "content_excerpt": "AI Cloud Pricing | GPU Compute &amp; AI Infrastructure | Lambda Skip to main content AI factories Products Supercomputers Superclusters 1-Click Clusters™ Instances Compare For every mission Superintelligence Enterprise Government Startups and Researchers Foundations AI factories Orchestration Lambda Stack Trust and security Docs Customer stories Documentation Blog Research Pricing Company Inside Lambda About Careers Leadership Investors Resources Research LLM index GPU benchmarks Customer stories Support Blog Partners Log in Get started Create account Talk to our team AI factories Products Supercomputers Superclusters 1-Click Clusters™ Instances Compare For every mission Superintelligence Enterprise Government Startups and Researchers Foundations AI factories Orchestration Lambda Stack Trust and security Docs Customer stories Documentation Blog Research Pricing Company Inside Lambda About Careers Leadership Investors Resources Research LLM index GPU benchmarks Customer stories Support Blog Partners Log in Get started Create account Talk to our team AI cloud pricing Clear, straightforward pricing for Instances, 1-Click Clusters™, and Superclusters. Contact us for reserved capacity at our lowest prices. Launch GPU instance Talk to our team 1-Click Clusters pricing Production-ready clusters from 16 to 2,000+ NVIDIA B200 or H100 GPUs. Learn more NVIDIA HGX B200 NVIDIA H100 NVIDIA HGX B200 systems Plan Duration GPU count Price per hour Action NVIDIA HGX B200 2 weeks – 1 year 16 $9"
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-026",
    "sentence": "ProviderHardware ProfilePricing ModelHourly Rate (per GPU)Market AvailabilityCoreWeaveNVIDIA B200Reserved$2.65Waitlisted / EnterpriseRunPodNVIDIA B200On-Demand$5.98ImmediateInworld ComputeNVIDIA B200On-DemandFrom $6.00Available NowLambdaNVIDIA B200 (16-node)On-Demand$9.862-week to 1-year termsIndustry AvgNVIDIA H100On-Demand$1.38 - $11.01Broad availabilityExport to SheetsFor the Canadian sovereign ecosystem, securing B200 availability is absolutely paramount for remaining technologically relevant.",
    "numeric_tokens": [
      "$5.98",
      "$2.65",
      "$9.862",
      "$1.38",
      "$6.00",
      "$11.01"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_041",
        "url": "https://inworld.ai/resources/nvidia-b200-gpu-cloud",
        "matching_tokens": [
          "$5.98",
          "$2.65"
        ],
        "content_excerpt": "Get started Menu Products Developers Company Pricing Contact Us Log In Integrate with AI Get started Published 04.13.2026 NVIDIA B200 GPU: Specs, Pricing, and Cloud Availability (2026) Summarize with: ChatGPT Perplexity Claude Grok Gemini Last updated: April 13, 2026 The NVIDIA B200 GPU is the flagship data center accelerator in the Blackwell generation, built on a dual-die GB100 design with 208 billion transistors. It delivers 192 GB of HBM3e memory at 8 TB/s bandwidth and up to 9,000 TFLOPS of FP4 Tensor performance, roughly 4x the inference throughput of the H100 it replaces. Inworld Compute has B200 capacity available now, starting from $6/hr, while most hardware orders remain backordered through mid-2026 with an estimated 3.6 million units in the queue. Cloud rental is currently the fastest way to access B200 GPUs, with pricing ranging from $2.65/hr (reserved) to $14.24/hr (on-demand) depending on the provider. What are the full specs of the NVIDIA B200 GPU? The B200 uses NVIDIA&#x27;s Blackwell architecture, which pairs two GB100 dies on a single module connected by a 10 TB/s chip-to-chip interconnect. This dual-die approach delivers substantially more compute density than Hopper while maintaining a single-GPU programming model. The fifth-generation Tensor Cores introduce native FP4 support, which is the critical spec for LLM inference. FP4 halves the memory footprint compared to FP8 while maintaining acceptable quality for most inference workloads, effectively doubling"
      },
      {
        "evidence_id": "gm_ev_074",
        "url": "https://getdeploying.com/gpus/nvidia-b200",
        "matching_tokens": [
          "$1.38"
        ],
        "content_excerpt": "B200 Cloud Pricing: Compare 22+ Providers (2026) show = true, 100); setTimeout(() => show = false, 5000)\" x-transition:enter=\"transition ease-out duration-300\" x-transition:enter-start=\"opacity-0 transform translate-y-8\" x-transition:enter-end=\"opacity-100 transform translate-y-0\" x-transition:leave=\"transition ease-in duration-300\" x-transition:leave-start=\"opacity-100\" x-transition:leave-end=\"opacity-0\" class=\"relative flex items-center w-full p-4 mb-2 border rounded space-x-4\" :class=\"message.tags === 'error' ? 'danger' : message.tags === 'success' ? 'success' : message.tags === 'warning' ? 'warn' : 'info'\" role=\"alert\"> Cloud Index By Country Object Storage VPS Egress GPUs LLMs Compare Cloud Index By Country Object Storage VPS Egress GPUs LLMs Compare 12) ? true: false\"> Thunder Compute H100 from $1.38/hr - No commitments - Hot swap hardware Our sponsor Try now → Nvidia B200 High-end Blackwell GPU for large-scale AI training and inference. Compare vs other GPUs → Aggregating historical prices... Key Specifications Architecture Blackwell Memory Up to 192GB HBM3e Memory Bandwidth 8,000 GB/s Release date Q1 2024 Compare Cloud Provider Prices We&#x27;re tracking 22 different cloud providers for the B200, and the pricing spread is significant. While the average sits at $4.99/hr, the lowest price is currently $2.25/hr per GPU (36-month reservation). Search Billing All On-Demand Spot Reserved Custom Max price/hr Min GPUs Min vCPUs Min RAM (GB) of shown How we sort results How we"
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-027",
    "sentence": "Global supply remains highly constrained, with an estimated 3.6 million units heavily backordered through mid-2026.",
    "numeric_tokens": [
      "6 million",
      "2026"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_000",
        "url": "https://www.newswire.ca/news-releases/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure-854223505.html",
        "matching_tokens": [
          "6 million",
          "2026"
        ],
        "content_excerpt": "TELUS and Government of Canada advance work to scale Canada's sovereign AI infrastructure Accessibility Statement Skip Navigation Resources Investor Relations Journalists Webcasts Français --> Français my CNW&nbsp; Login Register Client Login&nbsp; PR Newswire Amplify™ Next Gen Communications Cloud Cision Communications Cloud® Sign Up Send a Release News Products Contact Search Search When typing in this field, a list of search results will appear and be automatically updated as you type. Searching for your content... No results found. Please change your search terms and try again. Advanced Search News in Focus Browse News Releases All News Releases All Public Company News Releases Overview Multimedia Gallery All Multimedia All Photos All Videos Multimedia Gallery Overview Trending Topics All Trending Topics Business Auto &amp; Transportation All Automotive &amp; Transportation Aerospace, Defense Air Freight Airlines &amp; Aviation Automotive Maritime &amp; Shipbuilding Railroads and Intermodal Transportation Supply Chain/Logistics Transportation, Trucking &amp; Railroad Travel Trucking and Road Transportation Auto &amp; Transportation Overview View All Auto &amp; Transportation Business Technology All Business Technology Blockchain Broadcast Tech Computer &amp; Electronics Computer Hardware Computer Software Data Analytics Electronic Commerce Electronic Components Electronic Design Automation Financial Technology High Tech Security Internet Technology Nanotechnology Networks"
      },
      {
        "evidence_id": "gm_ev_030",
        "url": "https://league.com/newsroom/scale-ai-135m-investment-launch/",
        "matching_tokens": [
          "6 million",
          "2026"
        ],
        "content_excerpt": "League hosts SCALE AI’s historic $129M AI investment launch Skip to content Platform Platform Built to transform the healthcare consumer experience Platform overview Leadership in AI Solutions Agent teams Platform releases Developer program Partners WEBINAR The end of passive AI in healthcare Watch the recording Who We Serve Who We Serve Intuitive member experiences designed for health plans Payers Engage members with experiences that stand out from competitors. Lines of business Use cases Case study Heading Better consumer experience across the healthcare ecosystem Providers Become a provider of choice with an omni-channel patient experience. Consumer Health Be a digital destination for care and establish local health stewardship. Resources Resources Industry news and insights Resource hub A collection of content advancing healthcare consumer experiences. League Connect Content &#038; key takeaways from our annual CX transformation event. Blog Thought leadership &#038; insights on healthcare CX innovation. WEBINAR From care gaps to closed loops Watch the recording Company Company Empowering people to live happier, healthier lives About Newsroom League trust centre Careers REPORT League was named a Leader in CX Platforms For Healthcare Evaluation Learn more Login Talk to sales Login en fr en fr Dec 16, 2025 League hosts launch of SCALE AI’s record-breaking $129M investment to drive Canadian AI innovation Dec 16, 2025 By League Announcement SCALE AI , Canada’s artificial intel"
      },
      {
        "evidence_id": "gm_ev_032",
        "url": "https://investingnews.com/telus-and-government-of-canada-advance-work-to-scale-canada-s-sovereign-ai-infrastructure/",
        "matching_tokens": [
          "6 million",
          "2026"
        ],
        "content_excerpt": "Raven.config('https://6b64f5cc8af542cbb920e0238864390a@sentry.io/147999').install(); TELUS and Government of Canada advance work to scale Canada&#x27;s sovereign AI infrastructure | INN Connect with us Information About Us Contact Us Careers Partnerships Advertise With Us Authors Browse Topics Events Disclaimer Privacy Policy Australia North America World Login Investing News Network Your trusted source for investing success North America Australia World My INN Videos Companies Press Releases Private Placements SUBSCRIBE Reports &amp; Guides Market Outlook Reports Investing Guides Button Resource Precious Metals Battery Metals Base Metals Energy Critical Minerals Tech Life Science Market Market Market News Market Stocks Market Market Market News Market Stocks Home &gt; Market News &gt; TELUS and Government of Canada advance work to scale Canada&#39;s sovereign AI infrastructure Investing News Network May 11, 2026 With Canada&#39;s first Sovereign AI Factory in Rimouski, Quebec, now sold out, Telus is expanding its sovereign AI infrastructure with three world-class facilities in B.C. Designed to be the world&#39;s most sustainable sovereign data centres, the cluster will scale to over 60,000 GPUs and 150 MW by 2032 Telus is advancing work with the Government of Canada on a proposed Sovereign AI Factory cluster under the federal Enabling Large-Scale Sovereign AI Data Centres initiative a program designed to build the sovereign, high-performance AI compute infrastructure Canada "
      }
    ]
  },
  {
    "claim_id": "GM-Q1-T1-028",
    "sentence": "Managed under the Sovereign AI Compute Strategy, this $300 million fund is specifically designed to tackle the high cost of compute resources and the limited availability of domestic capacity.",
    "numeric_tokens": [
      "$300 million"
    ],
    "candidate_sources": [
      {
        "evidence_id": "gm_ev_043",
        "url": "https://ised-isde.canada.ca/site/ised/en/canadian-sovereign-ai-compute-strategy",
        "matching_tokens": [
          "$300 million"
        ],
        "content_excerpt": "Canadian Sovereign AI Compute Strategy Skip to main content Skip to \"About this site\" Language selection WxT Language switcher Français fr / Gouvernement du Canada WxT Search form Search Search Menu Main Menu Home You are here Canada.ca Artificial intelligence ecosystem Canadian Sovereign AI Compute Strategy From: Innovation, Science and Economic Development Canada Help define the next chapter of Canada's AI strategy. Take part in the consultation between October 1 and October 31. --> To strengthen Canada's position as a global leader in artificial intelligence (AI), it is essential for Canadian AI industries and researchers to have access to affordable, cutting‑edge compute infrastructure. By boosting access to powerful computing resources right here in Canada, we can drive innovation, create new opportunities and ensure that Canada stays competitive in the global AI race. What is AI compute? AI compute refers to the computational resources required for AI systems to perform tasks, such as processing data, running algorithms and training machine learning models. In other words, AI compute is the technology that powers AI. More compute power means faster and more accurate results. And that means more innovation, more productivity and more opportunity for Canadian AI companies, researchers and talent. That is why the Government of Canada is committed to building a strong and secure AI compute foundation. Budget 2024 announced $2 billion over five years, starting in 2024–25, to"
      },
      {
        "evidence_id": "gm_ev_044",
        "url": "https://ised-isde.canada.ca/site/ised/en/canadian-sovereign-ai-compute-strategy/ai-compute-access-fund",
        "matching_tokens": [
          "$300 million"
        ],
        "content_excerpt": "AI Compute Access Fund Skip to main content Skip to \"About this site\" Language selection WxT Language switcher Français fr / Gouvernement du Canada WxT Search form Search Search Menu Main Menu Home You are here Canada.ca Artificial intelligence ecosystem Canadian Sovereign AI Compute Strategy AI Compute Access Fund Current status: Closed The AI Compute Access Fund is not currently accepting applications. The most recent Call for Proposals closed at 11:59pm ET on July 31, 2025 and has received a high degree of interest and proposals representing projects from across Canada that span multiple industries. Review and assessment of applications is ongoing. Sign up to receive program updates . About the AI Compute Access Fund Program Do you need access to AI compute to power your innovation? The AI Compute Access Fund offers financial support to help small and medium-sized businesses (SMEs) access the compute power they need to scale and commercialize innovative AI projects. Save money and stay competitive right here at home. The AI Compute Access Fund will support successful projects with compute costs ranging from $100,000 up to $5 million by: Covering two-thirds of your eligible costs for Canadian, cloud-based AI compute services Covering half of your eligible costs for non-Canadian, cloud-based AI compute services Already applied? Sign in to access your account. Sign in &nbsp; Program objectives The call for applications closed on July 31, 2025 for the AI Compute Access Fund wh"
      },
      {
        "evidence_id": "gm_ev_045",
        "url": "https://grantedai.com/grants/canada-ai-compute-access-fund-innovation-science-and-economic-developm-e87c2a8c",
        "matching_tokens": [
          "$300 million"
        ],
        "content_excerpt": "Canada AI Compute Access Fund (2026) | Granted AI 1,000+ Opportunities Find the right grant Search federal, foundation, and corporate grants with AI — or browse by agency, topic, and state. Granted is making fundraising less tedious, more accessible, and more successful for everyone. Product AI Grant Writing Features Technology Data Coverage Data API Security Pricing FAQ Solutions For Researchers For Nonprofits For K-12 Schools For Environmental Orgs For SBIR Applicants For Farmers &amp; Agriculture First-Time Applicants Compare vs. Candid vs. Instrumentl vs. ChatGPT vs. Grant Writers vs. Grantable vs. GrantBoost Free Tools Find Grants Readiness Quiz Deadline Calendar Cost Calculator News Blog Learning Center Templates Browse Foundations Competitive Intel Foundation Maps Federal Awards Funded Research NIH Funding Rates Grant Success Rates Clinical Trials World Bank Projects EU Erasmus+ © 2026 Granted AI Contact Privacy Terms @GrantedAI Granted is making fundraising less tedious, more accessible, and more successful for everyone. Product AI Grant Writing Features Technology Data Coverage Data API Security Pricing FAQ Solutions For Researchers For Nonprofits For K-12 Schools For Environmental Orgs For SBIR Applicants For Farmers &amp; Agriculture First-Time Applicants Compare vs. Candid vs. Instrumentl vs. ChatGPT vs. Grant Writers vs. Grantable vs. GrantBoost Free Tools Find Grants Readiness Quiz Deadline Calendar Cost Calculator News Blog Learning Center Templates Browse Foun"
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
