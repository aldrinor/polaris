"""RACE prompt templates (DeepResearch-Bench, Du et al. arXiv:2506.11763).

These are copied VERBATIM (English variants) from the official harness
github.com/Ayanami0730/deep_research_bench (prompt/score_prompt_en.py and
prompt/criteria_prompt_en.py) so the POLARIS RACE re-implementation uses the SAME
criteria-generation and comparative-scoring prompts as the published benchmark. The
only substitutions vs the paper are (a) the judge model (kimi-k2.6 per the operator
DeepTRACE judge lock, DISCLOSED) and (b) the reference article (see race_scorer.py
header for the reference-provenance disclosure). Templates use str.format(); literal
JSON braces are doubled `{{ }}` exactly as upstream.
"""

# ---------------------------------------------------------------------------
# Dimension-weight generation (adaptive per-task weights, sum == 1.0)
# ---------------------------------------------------------------------------
GENERATE_DIMENSION_WEIGHT_PROMPT = """
<system_role>
You are an experienced research article evaluation expert. You excel at deeply understanding the objectives, challenges, and core value points of specific research tasks, and based on this, setting **dynamic, reasonable, and well-supported** dimension weights for subsequent article quality assessment.
</system_role>

<user_prompt>
There is a deep research task as follows:
<task>
"{task_prompt}"
</task>

<instruction>
**Background**: The research team will conduct in-depth and comprehensive research based on the `<task>` above and ultimately produce a high-quality research article.
**Your Task**: As an evaluation expert, you need to set the evaluation criteria weights for this specific `<task>` for our assessment team. The evaluation will be conducted across the following four dimensions:
1.  **Comprehensiveness:** The breadth, depth, and relevance of information coverage.
2.  **Insight:** The depth, originality, logic, and value of the analysis and conclusions.
3.  **Instruction Following:** Whether the report accurately and completely responds to all requirements and constraints of the task.
4.  **Readability:** Clarity of structure, fluency of language, effectiveness of data presentation, and overall ease of understanding.

**Evaluation Formula**: Total Score = Comprehensiveness * Comprehensiveness Weight + Insight * Insight Weight + Instruction Following * Instruction Following Weight + Readability * Readability Weight. (**Note: The sum of all weights must be exactly 1.0**)

**Core Requirements**:
1.  **In-depth Task Analysis**: Carefully study the specific content of the `<task>`, its implicit goals, potential difficulties, and the core value of its outcomes.
2.  **Dynamic Weight Allocation**: Based on your analysis, assign weights to the four dimensions (use decimals between 0 and 1, e.g., 0.3). **The key is to understand that different tasks have different focuses, and weights must be flexibly adjusted according to task characteristics, not fixed.**
3.  **Justify Allocation Reasons**: Your analysis (`<analysis>`) **must clearly and specifically explain why each dimension is given a particular weight**, and **directly link the reasons to the requirements and characteristics of the <task>**. This is crucial for evaluating the quality of your work.
4.  **Standard Format Output**: Strictly follow the format of the example below, first outputting the `<analysis>` text with detailed reasons, and then immediately providing the `<json_output>` with the weight allocation results.

</instruction>

<examples_rationale>
The following two examples are provided to demonstrate **how to adjust evaluation dimension weights and explain the reasons based on changes in task nature**. Please focus on learning the **thinking logic and analytical methods** in these examples, rather than simply imitating their content or weight values.
</examples_rationale>

<example_1>
<task>
"Analyze the feasibility of investing in electric vehicle (EV) charging infrastructure in suburban areas."
</task>
<output>
<analysis>
This task's core is to provide a clear feasibility analysis for a specific investment. The value lies in the thoroughness of the assessment and the practicality of its conclusions. Therefore, evaluation emphasizes insight and comprehensiveness.
* **Insight (0.35):** The task requires a deep analysis of feasibility, including market demand, costs, competition, and regulatory landscape. The quality of the strategic recommendations derived from this analysis is key.
* **Comprehensiveness (0.30):** A thorough investigation of all relevant factors (technical, economic, social, environmental) is crucial for a reliable feasibility study.
* **Instruction Following (0.20):** The report must specifically address EV charging infrastructure in suburban areas and focus on investment feasibility.
* **Readability (0.15):** Clearly communicating complex financial and technical analysis is important, but secondary to the depth and breadth of the study.
</analysis>
<json_output>
{{
    "comprehensiveness": 0.30,
    "insight": 0.35,
    "instruction_following": 0.20,
    "readability": 0.15
}}
</json_output>
</output>
</example_1>

<example_2>
<task>
"Provide a comprehensive overview of the historical performance of different renewable energy stocks over the past decade."
</task>
<output>
<analysis>
The core objective of this task is to deliver a broad, accurate, and decade-spanning overview of renewable energy stock performance. The emphasis is on the breadth of information, historical scope, and clear data presentation.
* **Comprehensiveness (0.40):** The task directly calls for covering "different" renewable energy stocks and a "decade" of data. The breadth and completeness of information are fundamental to the report's value, hence the highest weight.
* **Readability (0.25):** Presenting a large volume of historical financial data clearly and intuitively, enabling easy understanding and comparison, is a major challenge and key success factor for this task.
* **Instruction Following (0.20):** Ensuring the report strictly adheres to "renewable energy stocks," "past decade," and "historical performance" is a basic requirement.
* **Insight (0.15):** Summarizing trends or identifying key performance drivers based on the presented data can add value, but it's not the primary goal.
</analysis>
<json_output>
{{
    "comprehensiveness": 0.40,
    "insight": 0.15,
    "instruction_following": 0.20,
    "readability": 0.25
}}
</json_output>
</output>
</example_2>

Please strictly follow the above instructions and methods. Now, begin your work on the following specific task:
<task>
"{task_prompt}"
</task>
Please output your `<analysis>` and `<json_output>`.
</user_prompt>
"""

# ---------------------------------------------------------------------------
# Per-dimension adaptive criteria generation (each list's weights sum to 1.0)
# ---------------------------------------------------------------------------
GENERATE_CRITERIA_PROMPT_COMPREHENSIVENESS = """
<system_role>
You are an experienced research article evaluation expert. You excel at breaking down abstract evaluation dimensions (like "Comprehensiveness") into actionable, clear, and task-specific criteria, assigning appropriate weights and justifications for each.
</system_role>

<user_prompt>
**Background**: We are evaluating a deep research article written for the following task across four dimensions: Comprehensiveness, Insight, Instruction Following, and Readability.
1.  **Comprehensiveness:** The breadth, depth, and relevance of information coverage.
2.  **Insight:** The depth, originality, logic, and value of the analysis and conclusions.
3.  **Instruction Following:** Whether the report accurately and completely responds to all requirements and constraints of the task.
4.  **Readability:** Clarity of structure, fluency of language, effectiveness of data presentation, and overall ease of understanding.

<task>
"{task_prompt}"
</task>

<instruction>
**Your Goal**: For the **Comprehensiveness** dimension of this research article, develop a set of detailed, specific, and highly task-relevant evaluation criteria. You need to:
1.  **Analyze Task**: Deeply analyze the `<task>` to identify key information areas, perspectives, and depths that must be covered to achieve "comprehensiveness."
2.  **Formulate Criteria**: Based on the analysis, propose specific evaluation criteria items.
3.  **Explain Rationale**: Provide a brief explanation (`explanation`) for each criterion, stating why it is important for assessing the comprehensiveness of this `<task>`.
4.  **Assign Weights**: Assign a reasonable weight (`weight`) to each criterion, ensuring the sum of all criteria weights is exactly **1.0**. Weights should reflect the relative importance of each criterion in achieving the task's comprehensiveness goals.
5.  **Avoid Overlap**: Clearly focus on criteria related to the **Comprehensiveness** dimension, avoiding overlap with Insight, Instruction Following, or Readability.

**Core Requirements**:
1.  **Task-Centric**: Analysis, criteria, explanations, and weights must directly relate to the core requirements and characteristics of the `<task>`.
2.  **Well-Justified**: The `<analysis>` section must clearly articulate the overall thinking behind setting these criteria and weights, linking it to the `<task>`. The `explanation` for each criterion must justify its specific relevance.
3.  **Criteria Diversity**: Criteria should minimize overlap and cover all aspects of comprehensiveness as thoroughly as possible, avoiding omissions.
4.  **Reasonable Weights**: Weight allocation must be logical, reflecting the relative importance of each item within the comprehensiveness dimension.
5.  **Standard Format Output**: Strictly follow the example format below, first outputting the `<analysis>` text, then immediately providing the `<json_output>`.
</instruction>

<example>
<json_output>
[
  {{
    "criterion": "Comprehensive Coverage of Core Sub-topics",
    "explanation": "Assesses whether the article covers every key sub-topic, perspective, and stakeholder the task explicitly or implicitly requires.",
    "weight": 0.5
  }},
  {{
    "criterion": "Breadth and Quality of Evidence",
    "explanation": "Assesses whether the article draws on a wide, credible evidence base rather than a narrow set of sources.",
    "weight": 0.5
  }}
]
</json_output>
</example>

Please strictly follow the above instructions and methods. Now, begin your work on the following specific task:
<task>
"{task_prompt}"
</task>
Please output your `<analysis>` and `<json_output>`.
</user_prompt>
"""

GENERATE_CRITERIA_PROMPT_INSIGHT = """
<system_role>
You are an experienced research article evaluation expert. You excel at breaking down abstract evaluation dimensions (like "Insight") into actionable, clear, and task-specific criteria, assigning appropriate weights and justifications for each.
</system_role>

<user_prompt>
**Background**: We are evaluating a deep research article written for the following task across four dimensions: Comprehensiveness, Insight, Instruction Following, and Readability.
1.  **Comprehensiveness:** The breadth, depth, and relevance of information coverage.
2.  **Insight:** The depth, originality, logic, and value of the analysis and conclusions.
3.  **Instruction Following:** Whether the report accurately and completely responds to all requirements and constraints of the task.
4.  **Readability:** Clarity of structure, fluency of language, effectiveness of data presentation, and overall ease of understanding.

<task>
"{task_prompt}"
</task>

<instruction>
**Your Goal**: For the **Insight** dimension of this research article, develop a set of detailed, specific, and highly task-relevant evaluation criteria. You need to:
1.  **Analyze Task**: Deeply analyze the `<task>` to identify areas requiring in-depth analysis, logical deduction, viewpoint synthesis, or value judgment to demonstrate "insight."
2.  **Formulate Criteria**: Based on the analysis, propose specific criteria focusing on analytical depth, logical consistency, originality, and the value of conclusions.
3.  **Explain Rationale**: Provide a brief explanation (`explanation`) for each criterion, stating why it is important for assessing the insight of this `<task>`.
4.  **Assign Weights**: Assign a reasonable weight (`weight`) to each criterion, ensuring the sum of all criteria weights is exactly **1.0**. Weights should reflect the relative importance of each criterion in demonstrating the task's insight objectives.
5.  **Avoid Overlap**: Clearly focus on criteria related to the **Insight** dimension, avoiding overlap with Comprehensiveness, Instruction Following, or Readability.

**Core Requirements**:
1.  **Task-Centric**: Analysis, criteria, explanations, and weights must directly relate to the core requirements and characteristics of the `<task>`.
2.  **Beyond Surface-Level**: Criteria should assess analytical depth, logical rigor, originality of insights, and value of conclusions, not just information listing.
3.  **Well-Justified**: The `<analysis>` section must clearly articulate the overall thinking behind setting these criteria and weights, linking it to the `<task>`. The `explanation` for each criterion must justify its specific relevance.
4.  **Reasonable Weights**: Weight allocation must be logical, reflecting the relative importance of each item within the insight dimension.
5.  **Standard Format Output**: Strictly follow the example format below, first outputting the `<analysis>` text, then immediately providing the `<json_output>`.
</instruction>

<example>
<json_output>
[
  {{
    "criterion": "Analytical Depth and Causal Reasoning",
    "explanation": "Assesses whether the article moves beyond description to explain mechanisms, drivers, and causal relationships relevant to the task.",
    "weight": 0.5
  }},
  {{
    "criterion": "Original Synthesis and Forward-Looking Value",
    "explanation": "Assesses whether the article offers non-obvious synthesis, implications, or foresight rather than restating known facts.",
    "weight": 0.5
  }}
]
</json_output>
</example>

Please strictly follow the above instructions and methods. Now, begin your work on the following specific task:
<task>
"{task_prompt}"
</task>
Please output your `<analysis>` and `<json_output>`.
</user_prompt>
"""

GENERATE_CRITERIA_PROMPT_INSTRUCTION = """
<system_role>
You are an experienced research article evaluation expert. You excel at breaking down abstract evaluation dimensions (like "Instruction Following") into actionable, clear, and task-specific criteria, assigning appropriate weights and justifications for each.
</system_role>

<user_prompt>
**Background**: We are evaluating a deep research article written for the following task across four dimensions: Comprehensiveness, Insight, Instruction Following, and Readability.
1.  **Comprehensiveness:** The breadth, depth, and relevance of information coverage.
2.  **Insight:** The depth, originality, logic, and value of the analysis and conclusions.
3.  **Instruction Following:** Whether the report accurately and completely responds to all requirements and constraints of the task.
4.  **Readability:** Clarity of structure, fluency of language, effectiveness of data presentation, and overall ease of understanding.

<task>
"{task_prompt}"
</task>

<instruction>
**Your Goal**: For the **Instruction Following** dimension of this research article, develop a set of detailed, specific, and highly task-relevant evaluation criteria. You need to:
1.  **Analyze Task**: Deeply analyze the specific instructions, questions, scope limitations (e.g., geography, time, subject), and core objectives within the `<task>`.
2.  **Formulate Criteria**: Based on the analysis, propose specific criteria focusing on whether the article accurately, completely, and directly responds to all task instructions, whether content strictly adheres to limitations, and if it remains on topic.
3.  **Explain Rationale**: Provide a brief explanation (`explanation`) for each criterion, stating why it is important for assessing the instruction adherence of this `<task>`.
4.  **Assign Weights**: Assign a reasonable weight (`weight`) to each criterion, ensuring the sum of all criteria weights is exactly **1.0**. Weights should reflect the relative importance of each criterion in ensuring the task is completed accurately and relevantly.
5.  **Avoid Overlap**: Clearly focus on criteria related to the **Instruction Following** dimension, avoiding overlap with Comprehensiveness, Insight, or Readability.

**Core Requirements**:
1.  **Instruction-Centric**: Analysis, criteria, explanations, and weights must directly correspond to the explicit requirements, questions, and limitations of the `<task>`.
2.  **Focus on Responsiveness and Relevance**: Criteria should assess if the content is on-topic, the scope is accurate, and all questions are directly and fully answered.
3.  **Well-Justified**: The `<analysis>` section must clearly articulate the overall thinking behind setting these criteria and weights, linking it to the `<task>`. The `explanation` for each criterion must justify its specific relevance.
4.  **Reasonable Weights**: Weight allocation must be logical, reflecting the relative importance of each instruction or limitation within the task.
5.  **Standard Format Output**: Strictly follow the example format below, first outputting the `<analysis>` text, then immediately providing the `<json_output>`.
</instruction>

<example>
<json_output>
[
  {{
    "criterion": "Direct Response to All Explicit Sub-questions",
    "explanation": "Assesses whether every explicitly requested section, question, or deliverable in the task is directly addressed.",
    "weight": 0.5
  }},
  {{
    "criterion": "Adherence to Stated Scope and Constraints",
    "explanation": "Assesses whether the article respects the task's scope limits (time period, subject, format, source restrictions).",
    "weight": 0.5
  }}
]
</json_output>
</example>

Please strictly follow the above instructions and methods. Now, begin your work on the following specific task:
<task>
"{task_prompt}"
</task>
Please output your `<analysis>` and `<json_output>`.
</user_prompt>
"""

GENERATE_CRITERIA_PROMPT_READABILITY = """
<system_role>
You are an experienced research article evaluation expert. You excel at breaking down abstract evaluation dimensions (like "Readability") into actionable, clear, and task-specific criteria, assigning appropriate weights and justifications for each.
</system_role>

<user_prompt>
**Background**: We are evaluating a deep research article written for the following task across four dimensions: Comprehensiveness, Insight, Instruction Following, and Readability.
1.  **Comprehensiveness:** The breadth, depth, and relevance of information coverage.
2.  **Insight:** The depth, originality, logic, and value of the analysis and conclusions.
3.  **Instruction Following:** Whether the report accurately and completely responds to all requirements and constraints of the task.
4.  **Readability:** Clarity of structure, fluency of language, effectiveness of data presentation, and overall ease of understanding.

<task>
"{task_prompt}"
</task>

<instruction>
**Your Goal**: For the **Readability** dimension of this research article, develop a set of detailed, specific, and relatively general evaluation criteria, while also considering the characteristics of the `<task>`. You need to:
1.  **Analyze Readability Elements**: Identify key elements that constitute the readability of a high-quality research report, such as structural logic, language expression, information presentation, formatting, etc.
2.  **Formulate Criteria**: Based on the analysis, propose specific criteria covering language clarity, structure, information presentation, data/visualization, formatting, and audience adaptation.
3.  **Explain Rationale**: Provide a brief explanation (`explanation`) for each criterion, stating why it is important for enhancing report readability and reader comprehension, potentially linking to the `<task>` type.
4.  **Assign Weights**: Assign a reasonable weight (`weight`) to each criterion, ensuring the sum of all criteria weights is exactly **1.0**. Weights should reflect the relative importance of each criterion to overall readability.
5.  **Avoid Overlap**: Clearly focus on criteria related to the **Readability** dimension, avoiding overlap with Comprehensiveness, Insight, or Instruction Following.

**Core Requirements**:
1.  **Cover Key Elements**: Criteria should systematically cover the main aspects affecting readability.
2.  **Clear and Actionable**: Each criterion should be specific, easy to understand, and assessable.
3.  **Well-Justified**: The `<analysis>` section must articulate the overall thinking behind these criteria and weights. The `explanation` for each criterion must justify its importance.
4.  **Reasonable Weights**: Weight allocation must be logical, reflecting the relative contribution of each item to readability.
5.  **Standard Format Output**: Strictly follow the example format below, first outputting the `<analysis>` text, then immediately providing the `<json_output>`.
</instruction>

<example>
<json_output>
[
  {{
    "criterion": "Overall Structure and Logical Organization",
    "explanation": "Assesses whether the article has a clear, logically ordered structure with appropriate headings guiding the reader.",
    "weight": 0.4
  }},
  {{
    "criterion": "Language Clarity and Fluency",
    "explanation": "Assesses whether the writing is clear, grammatical, and precise.",
    "weight": 0.3
  }},
  {{
    "criterion": "Effective Information and Data Presentation",
    "explanation": "Assesses whether tables, lists, and emphasis are used effectively to convey key information (e.g., a required summary table).",
    "weight": 0.3
  }}
]
</json_output>
</example>

Please strictly follow the above instructions and methods. Now, begin your work on the following specific task:
<task>
"{task_prompt}"
</task>
Please output your `<analysis>` and `<json_output>`.
</user_prompt>
"""

# ---------------------------------------------------------------------------
# Comparative scoring (target = article_1, reference = article_2), one call
# VERBATIM from prompt/score_prompt_en.py (generate_merged_score_prompt).
# ---------------------------------------------------------------------------
GENERATE_MERGED_SCORE_PROMPT = """
<system_role>You are a strict, meticulous, and objective research article evaluation expert. You excel at using specific assessment criteria to deeply compare two articles on the same task, providing precise scores and clear justifications.</system_role>

<user_prompt>
**Task Background**
There is a deep research task, and you need to evaluate two research articles written for this task. We will assess the articles across four dimensions: Comprehensiveness, Insight, Instruction Following, and Readability. The content is as follows:
<task>
"{task_prompt}"
</task>

**Articles to Evaluate**
<article_1>
"{article_1}"
</article_1>

<article_2>
"{article_2}"
</article_2>

**Evaluation Criteria**
Now, you need to evaluate and compare these two articles based on the following **evaluation criteria list**, providing comparative analysis and scoring each on a scale of 0-10. Each criterion includes an explanation, please understand carefully.

<criteria_list>
{criteria_list}
</criteria_list>

<Instruction>
**Your Task**
Please strictly evaluate and compare `<article_1>` and `<article_2>` based on **each criterion** in the `<criteria_list>`. You need to:
1.  **Analyze Each Criterion**: Consider how each article fulfills the requirements of each criterion.
2.  **Comparative Evaluation**: Analyze how the two articles perform on each criterion, referencing the content and criterion explanation.
3.  **Score Separately**: Based on your comparative analysis, score each article on each criterion (0-10 points).

**Scoring Rules**
For each criterion, score both articles on a scale of 0-10 (continuous values). The score should reflect the quality of performance on that criterion:
*   0-2 points: Very poor performance. Almost completely fails to meet the criterion requirements.
*   2-4 points: Poor performance. Minimally meets the criterion requirements with significant deficiencies.
*   4-6 points: Average performance. Basically meets the criterion requirements, neither good nor bad.
*   6-8 points: Good performance. Largely meets the criterion requirements with notable strengths.
*   8-10 points: Excellent/outstanding performance. Fully meets or exceeds the criterion requirements.

**Output Format Requirements**
Please **strictly** follow the `<output_format>` below for each criterion evaluation. **Do not include any other unrelated content, introduction, or summary**. Start with "Standard 1" and proceed sequentially through all criteria:
</Instruction>

<output_format>
{{
    "comprehensiveness": [
        {{
            "criterion": [Text content of the first comprehensiveness evaluation criterion],
            "analysis": [Comparative analysis],
            "article_1_score": [Continuous score 0-10],
            "article_2_score": [Continuous score 0-10]
}},
{{
            "criterion": [Text content of the second comprehensiveness evaluation criterion],
            "analysis": [Comparative analysis],
            "article_1_score": [Continuous score 0-10],
            "article_2_score": [Continuous score 0-10]
        }},
        ...
    ],
    "insight": [
        {{
            "criterion": [Text content of the first insight evaluation criterion],
            "analysis": [Comparative analysis],
            "article_1_score": [Continuous score 0-10],
            "article_2_score": [Continuous score 0-10]
        }},
        ...
    ],
    ...
}}
</output_format>

Now, please evaluate the two articles based on the research task and criteria, providing detailed comparative analysis and scores according to the requirements above. Ensure your output follows the specified `<output_format>` and that the JSON format is parsable, with all characters that might cause JSON parsing errors properly escaped.
</user_prompt>
"""
