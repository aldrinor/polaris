# Validated rename worklist — 210 names grouped by family
**Risk key:** `S`=safe symbol · `F`=file (check importers) · `A`=alias (control-surface string, do NOT naive-rename) · `T`=text/docstring · `D`=domain-review


## honest  (37)
- `F` **run_honest_sweep_r3.py** → run_sweep_evaluation.py  ·scr· harness_render_boundary_screen.py:53
- `F` **run_honest_sweep_r3.py** → run_sweep_evaluation.py  ·scr· iarch007_behavioral_canary.py:21
- `D` **run_honest_sweep_r3** → run_sweep  ·scr· iarch011_prb_corroboration_replay_harness.py:51
- `D` **run_honest_sweep_r3** → run_sweep  ·scr· iwire014_cwf_header_diagnostic.py:18
- `D` **run_honest_sweep_r3** → run_sweep  ·scr· iwire014_quantified_replay.py:60
- `T` **_run_honest_sweep_r3** → run_sweep  ·scr· iwire014_quantified_replay.py:63
- `D` **run_honest_sweep_r3** → run_sweep  ·scr· iwire014_render_proof.py:2
- `A` **Legacy run, pre-honest-rebuild** → LEGACY_MODE_LABEL = "Legacy run, pre-rebuild"  ·scr· migrate_old_runs.py:59
- `A` **_honest_rebuild_migration** → _pre_rebuild_migration  ·scr· migrate_old_runs.py:60
- `F` **run_honest_sweep_r3.py** → run_cross_domain_readiness_sweep.py  ·scr· run_honest_sweep_r3.py:1
- `D` **_QUANTIFIED_HONEST_EMPTY_STATUSES** → _QUANTIFIED_LEGITIMATE_EMPTY_STATUSES  ·scr· run_honest_sweep_r3.py:1846
- `F` **honest_sweep_integration** → sweep_integration  ·scr· run_honest_sweep_r3.py:20231
- `S` **apply_honest_scorecard_to_manifest** → apply_release_quality_scorecard_to_manifest  ·scr· run_honest_sweep_r3.py:21366
- `F` **run_honest_sweep_r3.py** → run_verification_sweep.py  ·scr· run_honest_sweep_r3.py:21658
- `D` **honest_sweep_r3** → verification_sweep  ·scr· run_honest_sweep_r3.py:21826
- `A` **PG_S15_CORROBORATED_HONEST_LABEL** → PG_S15_CORROBORATED_ORIGIN_LABEL  ·scr· run_honest_sweep_r3.py:3987
- `S` **_contradiction_render_honest_enabled** → _contradiction_render_verbatim_enabled  ·scr· run_honest_sweep_r3.py:4855
- `A` **PG_CONTRADICTION_RENDER_HONEST** → PG_CONTRADICTION_RENDER_VERBATIM  ·scr· run_honest_sweep_r3.py:4856
- `A` **_ARTIFACT_KIND_REFUSAL** → _ARTIFACT_KIND_DECLINED (value "declined-refusal")  ·scr· run_honest_sweep_r3.py:6650
- `S` **_ARTIFACT_KIND_HEADINGS** → value "Declined — no report produced"  ·scr· run_honest_sweep_r3.py:6700
- `A` **token_honesty (manifest key / module concept)** → token_accounting  ·scr· run_honest_sweep_r3.py:9279
- `S` **reset_token_honesty_telemetry** → reset_token_accounting_telemetry  ·scr· run_honest_sweep_r3.py:9281
- `A` **run_live_honest_cycle.py** → run_live_verified_cycle.py  ·scr· run_live_honest_cycle.py:1
- `A` **LIVE_HONEST** → LIVE_VERIFIED  ·scr· run_live_honest_cycle.py:98
- `S` **HonestSweepJobRunner** → SweepJobRunner  ·src· __init__.py:29
- `S` **HonestSweepJobRunnerConfig** → SweepJobRunnerConfig  ·src· __init__.py:30
- `S` **make_default_honest_sweep_job_runner** → make_default_sweep_job_runner  ·src· __init__.py:32
- `F` **honest_sweep_job_runner.py** → v30_sweep_job_runner.py  ·src· honest_sweep_job_runner.py:1
- `S` **HonestSweepJobRunner** → V30SweepJobRunner  ·src· honest_sweep_job_runner.py:177
- `S` **make_default_honest_sweep_job_runner** → make_default_v30_sweep_job_runner  ·src· honest_sweep_job_runner.py:450
- `F` **honest_pipeline.py** → provenance_verified_pipeline.py  ·src· honest_pipeline.py:1
- `S` **run_honest_pipeline** → run_provenance_verified_pipeline  ·src· honest_pipeline.py:173
- `F` **honest_sweep_integration.py** → v30_sweep_integration.py or frame_coverage_sweep_integration.py  ·src· honest_sweep_integration.py:1
- `D` **_relevance_honest_drop_enabled** → _relevance_actual_drop_logging_enabled  ·src· evidence_selector.py:1876
- `T` **honest-rebuild** → pipeline A / rebuild pipeline  ·src· __init__.py:1
- `S` **honest-rebuild run** → pipeline-A run  ·src· tool_tracer.py:4
- `T` **HONEST-REBUILD Phase 2f** → Rebuild Phase 2f  ·src· openalex_client.py:78

## junk/garbage  (29)
- `T` **real box2 junk fixtures** → real box2 chrome/noise fixtures  ·scr· _wave2_assert.py:1
- `D` **strip_junk** → strip_non_answer_content  ·scr· pack_drb2.py:90
- `S` **_is_junk** → _is_non_citable_unit  ·scr· iarch011_parallel_verify_gate.py:55
- `S` **junk** → non_citable_units  ·scr· iarch011_parallel_verify_gate.py:58
- `S` **_GARBAGE_URL** → _UNVERIFIED_URL  ·scr· iarch011_prb_corroboration_replay_harness.py:69
- `S` **bad** → junk_header_count  ·scr· iwire014_cwf_header_diagnostic.py:74
- `D` **JUNK HEADER** → non-renderable header  ·scr· iwire014_cwf_header_diagnostic.py:77
- `S` **_junk_ev_row_text** → _low_quality_ev_row_text  ·scr· run_honest_sweep_r3.py:1187
- `S` **_junk_ev_row_url** → _low_quality_ev_row_url  ·scr· run_honest_sweep_r3.py:1196
- `S` **_junk_ev_row_direct_quote** → _low_quality_ev_row_direct_quote  ·scr· run_honest_sweep_r3.py:1203
- `S` **_junk_src_url** → _low_quality_src_url  ·scr· run_honest_sweep_r3.py:1241
- `S` **_screen_junk_evidence** → _screen_low_quality_evidence  ·scr· run_honest_sweep_r3.py:1248
- `A` **PG_JUNK_SOURCE_SCREEN** → PG_LOW_QUALITY_SOURCE_SCREEN  ·scr· run_honest_sweep_r3.py:1280
- `S` **_screen_junk_evidence** → _screen_low_quality_evidence  ·scr· run_honest_sweep_r3.py:14016
- `S` **_detect_ci_junk** → _detect_content_integrity_defect  ·scr· run_honest_sweep_r3.py:14655
- `A` **content_integrity_junk** → content_integrity_defect  ·scr· run_honest_sweep_r3.py:15688
- `S` **_run_junk_deleted_disclosed** → _run_nonsource_deleted_disclosed  ·scr· run_honest_sweep_r3.py:15745
- `A` **junk_deletion_gate** → nonsource_deletion_gate  ·scr· run_honest_sweep_r3.py:15747
- `S` **_junk_deleted_for_disclosure** → _nonsource_deleted_for_disclosure  ·scr· run_honest_sweep_r3.py:15760
- `A` **is_row_content_junk** → is_row_content_low_quality  ·src· junk_deletion_gate.py:
- `A` **junk_deletion_gate.py** → content_integrity_deletion_gate.py  ·src· junk_deletion_gate.py:1
- `A` **is_row_content_junk** → is_row_content_integrity_violation  ·src· junk_deletion_gate.py:105
- `A` **junk_deletion_gate (module)** → off_topic_deletion_gate  ·src· multi_section_generator.py:10673
- `S` **_uncovered_fact_disclosure_is_junk** → _uncovered_fact_disclosure_is_low_quality  ·src· verified_compose.py:1771
- `S` **_JUNK_SCREEN** → _CHROME_SCREEN_FN  ·src· verified_compose.py:377
- `S` **_compose_junk_screen** → _compose_boilerplate_screen  ·src· verified_compose.py:380
- `S` **_base_junk** → _is_base_boilerplate_chrome  ·src· weighted_enrichment.py:3072
- `S` **_make_junk_screen** → _make_chrome_screen  ·src· weighted_enrichment.py:4825
- `S` **is_junk** → is_chrome_or_junk_screen -> rename to is_chrome_screen  ·src· weighted_enrichment.py:5212

## beat-both  (12)
- `D` **aggregate_beat_both_runs.py** → (propose at rename)  ·scr· aggregate_beat_both_runs.py:1
- `A` **slice_005_beat_both_benchmark** → slice_005_comparative_benchmark  ·scr· demo_smoke.py:38
- `D` **run_m_live_2_beat_both.py** → (propose at rename)  ·scr· run_m_live_2_beat_both.py:1
- `A` **BEAT_BOTH_SCORERS** → (propose at rename)  ·scr· run_m_live_2_beat_both.py:37
- `A` **beat_both_scorer.py** → head_to_head_dimension_scorer.py  ·src· beat_both_scorer.py:1
- `A` **BEAT-BOTH** → HEAD_TO_HEAD  ·src· beat_both_scorer.py:3
- `T` **BEAT-BOTH** → head-to-head benchmark  ·src· benchmark_config.py:1
- `A` **beat_both_scorer** → head-to-head scorer  ·src· claim_dedup.py:1
- `T` **BEAT-BOTH** → head-to-head benchmark  ·src· dimension_scorers.py:1
- `T` **beat-both scorer** → head-to-head scorer  ·src· extended_metrics.py:1
- `T` **BEAT-BOTH** → head-to-head scoring  ·src· external_loader.py:1
- `S` **POLARIS BEAT-BOTH** → POLARIS Benchmark Report  ·src· report_renderer.py:126

## lethal  (7)
- `D` **lethal_retrieve** → prioritized_retrieve or ranked_retrieve  ·scr· pg_mesh_preflight.py:28
- `F` **lethal.py** → retrieval.py  ·src· lethal.py:1
- `S` **lethal_scored** → ranked_scored  ·src· lethal.py:210
- `S` **lethal (local var)** → composite_score  ·src· lethal.py:239
- `A` **PG_LETHAL_SEED_K** → PG_RETRIEVE_SEED_K  ·src· lethal.py:49
- `S` **lethal_retrieve** → retrieve_claims  ·src· lethal.py:94
- `S` **lethal_snowball_score** → compute_snowball_score  ·src· snowball.py:105

## money-trap  (1)
- `D` **MONEY-TRAP / money-trap (docstring term)** → budget-leak gate / spend-before-verification bug  ·src· __init__.py:3

## version marker (v#/r#)  (44)
- `F` **_v24_compare.py** → compare_report_versions.py (or delete)  ·scr· _v24_compare.py:1
- `F` **audit_v3_report.py** → audit_report_forensics.py  ·scr· audit_v3_report.py:1
- `T` **build_and_run_v4** → build_and_run (drop version suffix once dead branches removed)  ·scr· live_server.py:557
- `A` **PG_V2_ENABLED** → PG_LEGACY_GRAPH_ENABLED  ·scr· live_server.py:560
- `F` **run_full_scale_v10.py** → run_full_scale.py (single script with a --profile/--config flag selecting the knob set)  ·scr· run_full_scale_v10.py:1
- `S` **_V10_ENV** → LAUNCH_ENV  ·scr· run_full_scale_v10.py:26
- `F` **run_full_scale_v23.py** → run_full_scale.py (parameterized by config file)  ·scr· run_full_scale_v23.py:1
- `S` **_V23_ENV** → LAUNCH_ENV  ·scr· run_full_scale_v23.py:28
- `F` **run_full_scale_v24.py** → run_full_scale.py (parameterized)  ·scr· run_full_scale_v24.py:1
- `S` **_V24_ENV** → LAUNCH_ENV  ·scr· run_full_scale_v24.py:35
- `F` **run_full_scale_v25.py** → run_full_scale.py (parameterized)  ·scr· run_full_scale_v25.py:1
- `S` **_V25_ENV** → LAUNCH_ENV  ·scr· run_full_scale_v25.py:37
- `F` **run_full_scale_v26.py** → run_full_scale.py (parameterized)  ·scr· run_full_scale_v26.py:1
- `S` **_V26_ENV** → LAUNCH_ENV  ·scr· run_full_scale_v26.py:52
- `F` **run_full_scale_v27.py** → run_full_scale.py (parameterized)  ·scr· run_full_scale_v27.py:1
- `S` **_V27_ENV** → LAUNCH_ENV  ·scr· run_full_scale_v27.py:43
- `F` **run_full_scale_v28.py** → run_full_scale.py (parameterized)  ·scr· run_full_scale_v28.py:1
- `S` **_V28_ENV** → LAUNCH_ENV  ·scr· run_full_scale_v28.py:51
- `F` **run_full_scale_v29.py** → run_full_scale.py (parameterized)  ·scr· run_full_scale_v29.py:1
- `S` **_V29_ENV** → LAUNCH_ENV  ·scr· run_full_scale_v29.py:35
- `F` **run_full_scale_v30_phase2.py** → run_full_scale.py (parameterized) or full_scale_launcher.py  ·scr· run_full_scale_v30_phase2.py:1
- `S` **_V30_PHASE2_ENV** → LAUNCH_ENV  ·scr· run_full_scale_v30_phase2.py:38
- `F` **run_r5_rerun.py** → run_denylist_subject_content_starved_fixes_rerun.py  ·scr· run_r5_rerun.py:1
- `F` **run_r6_validation.py** → run_gap_fix_validation.py  ·scr· run_r6_validation.py:1
- `S` **V1_ARCHIVE_DIR** → PREVIOUS_RUN_ARCHIVE_DIR  ·scr· screenshot_all_states.py:44
- `A` **ui_review_v2.pdf** → ui_review.pdf  ·scr· screenshot_all_states.py:45
- `S` **run_v30_post_generation** → run_frame_coverage_post_generation  ·src· honest_sweep_integration.py:156
- `A` **_ENABLED_ENV / PG_V30_ENABLED** → PG_FRAME_COVERAGE_ENABLED  ·src· honest_sweep_integration.py:92
- `S` **merge_v30_into_manifest** → merge_frame_coverage_into_manifest  ·src· honest_sweep_integration.py:99
- `T` **build_and_run_v4** → build_and_run_pipeline_a_ui (or run_ui_pipeline)  ·src· pipeline_a_ui_adapter.py:187
- `F` **state_v3.py** → state_lightweight.py or pipeline_state.py  ·src· state_v3.py:1
- `S` **create_v3_state** → create_lightweight_state  ·src· state_v3.py:64
- `F` **report_assembler_v2.py** → grounded_bibliography_assembler.py (or merge into report_assembler.py)  ·src· report_assembler_v2.py:
- `F` **synthesizer_v2.py** → section_synthesizer_parallel.py  ·src· synthesizer_v2.py:1
- `F` **verifier_v2.py** → verifier.py  ·src· verifier_v2.py:1
- `S` **contracts_v3** → contracts (or descriptive submodule name)  ·src· analysis_notebook.py:14
- `S` **_R5_LEGIT_DOUBLES** → _LEGITIMATE_DOUBLED_WORDS  ·src· react_agent.py:221
- `S` **_R6_SCI_LENS_WORDS** → _SCIENTIFIC_LENS_CONTEXT_WORDS  ·src· react_agent.py:224
- `S` **_R3_SCALE_WORDS** → _SCALE_TRANSFORM_WORDS  ·src· react_agent.py:231
- `S` **_R7_TRANSITIVE_VERBS** → _TRANSITIVE_VERBS  ·src· react_agent.py:238
- `S` **_R7_IRREGULAR_PP** → _IRREGULAR_PAST_PARTICIPLES  ·src· react_agent.py:249
- `S` **_R7_SINGULAR_S** → _SINGULAR_WORDS_ENDING_IN_S  ·src· react_agent.py:267
- `F` **v30_contract_synthesizer.py** → contract_synthesizer.py  ·src· v30_contract_synthesizer.py:1
- `S` **build_v30_contract** → build_report_contract  ·src· v30_contract_synthesizer.py:78

## temp/wip/draft  (3)
- `F` **visual_final.py** → visual_full_viewport_capture.py  ·scr· visual_final.py:1
- `S` **_is_new_chrome_category** → _is_i_wire_012_chrome_category  ·src· weighted_enrichment.py:3185
- `T` **_TEMPLATE_ECHO_DEMONSTRATES** → _TEMPLATE_ECHO_SUBJECT_PREDICATE  ·src· react_agent.py:172

## real/true  (4)
- `D` **_gate_injected_prepend_rows** → (propose at rename)  ·scr· run_honest_sweep_r3.py:14426
- `D` **_final_zyte** → (propose at rename)  ·scr· run_honest_sweep_r3.py:15664
- `S` **_depth_d8_true_drop** → _depth_d8_drop_not_sink  ·scr· run_honest_sweep_r3.py:452
- `S` **_depth_true_drop_when_all_verified** → _depth_drop_when_all_verified  ·scr· run_honest_sweep_r3.py:564

## enhanced/robust/ultimate  (1)
- `S` **EnhancedSourceScore** → SourceQualityScore  ·src· source_quality.py:74

## codename (gemini/most/dice/etc)  (14)
- `A` **Gemini feature / GEMINI-ARCH** → STRUCTURED_DATA_ARCH or similar internal tag  ·scr· anti_tunnel_view_test.py:52
- `F` **deep_gemini_verify.py** → integration_quality_verify.py  ·scr· deep_gemini_verify.py:1
- `T` **Gemini-class** → high-quality output  ·scr· deep_gemini_verify.py:2
- `F` **iarch007_behavioral_canary.py** → behavioral_canary_release_fixes.py  ·scr· iarch007_behavioral_canary.py:1
- `S` **rhsr3_canary** → sweep_module_canary  ·scr· iarch007_behavioral_canary.py:157
- `F` **DICED** → pipeline_stage_invariant_preflight.py  ·scr· pipeline_diced_preflight.py:2
- `S` **dice** → StageCheckResult / rename dice_* functions to check_<stage_name>  ·scr· pipeline_diced_preflight.py:217
- `D` **OFFLINE_DICE** → OFFLINE_CHECKS  ·scr· pipeline_diced_preflight.py:838
- `A` **_WINNER_SLATE_ON_PAID_PATH_ENV** → _ENRICHMENT_SLATE_ON_PAID_PATH_ENV  ·scr· run_honest_sweep_r3.py:21674
- `A` **winner_slate_on_paid_path_enabled** → enrichment_slate_on_paid_path_enabled  ·scr· run_honest_sweep_r3.py:21689
- `A` **apply_winner_slate_on_paid_path** → apply_enrichment_slate_on_paid_path  ·scr· run_honest_sweep_r3.py:21696
- `A` **mineru_firing** → mineru_degraded  ·src· tool_tracer.py:461
- `S` **mineru_fire_canary_enabled** → mineru_degrade_canary_enabled  ·src· tool_tracer.py:469
- `A` **GEMINI-ARCH 2A** → Python analysis (structured data)  ·src· data_analyzer.py:2

## dashboard/misc  (3)
- `S` **OpenAIShimClient** → (propose at rename)  ·scr· pg_compose_openai_validation.py:58
- `A` **dashboard_PG_TEST_060_BTG.html** → dashboard_test_output.html  ·scr· dashboard_visual_audit.py:30
- `S` **hs** → chrome_sample  ·scr· iwire016_chrome_classifier_bakeoff.py:110

## other  (55)
- `F` **_basket_workers_ab_cert.py** → compose_basket_workers_ab_certification_test.py  ·scr· _basket_workers_ab_cert.py:1
- `F` **_m54_append_contract.py** → append_report_contract_yaml.py  ·scr· _m54_append_contract.py:1
- `F` **_retired_2026_06_14** → archive/2026_06_14_retired_scripts/ (or delete if truly dead)  ·scr· pg_compose_openai_validation.py:1
- `F` **compare_live_vs_pg_lb_sa_02.py** → compare_live_vs_prerebuild_run.py  ·scr· compare_live_vs_pg_lb_sa_02.py:1
- `F` **compose_agentic_report_s3gear329.py** → compose_agentic_report.py  ·scr· compose_agentic_report_s3gear329.py:1
- `S` **passced** → passed  ·scr· entailment_shape_bakeoff.py:205
- `S` **rhsr_patched** → honest_sweep_module  ·scr· harness_render_boundary_screen.py:57
- `F` **i_naming_001_migrate.py** → migrate_bpei_to_ambiguity_detector.py  ·scr· i_naming_001_migrate.py:1
- `F` **iarch007_release_invariant_check.py** → release_invariant_check.py  ·scr· iarch007_release_invariant_check.py:1
- `F` **iarch010_replay_breadth_faithfulness_harness.py** → replay_breadth_faithfulness_harness.py  ·scr· iarch010_replay_breadth_faithfulness_harness.py:1
- `F` **iarch011_b11_compose_repetition_harness.py** → compose_repetition_harness.py  ·scr· iarch011_b11_compose_repetition_harness.py:1
- `S` **_BANKED_RUN** → BANKED_RUN_DIR (configurable)  ·scr· iarch011_b11_compose_repetition_harness.py:35
- `F` **iarch011_binding_and_judge_probe.py** → binding_and_judge_probe.py  ·scr· iarch011_binding_and_judge_probe.py:1
- `S` **_R** → _REPO_ROOT  ·scr· iarch011_binding_and_judge_probe.py:10
- `S` **an** → credibility_analysis  ·scr· iarch011_binding_and_judge_probe.py:34
- `S` **wfe** → unbound_supports_diag  ·scr· iarch011_binding_and_judge_probe.py:36
- `S` **verb** → verbatim_count  ·scr· iarch011_binding_and_judge_probe.py:58
- `S` **cw_cov** → content_word_coverage_count  ·scr· iarch011_binding_and_judge_probe.py:59
- `S` **ej** → entailment_judge_mod  ·scr· iarch011_binding_and_judge_probe.py:82
- `S` **verds** → verdict_counts  ·scr· iarch011_binding_and_judge_probe.py:93
- `F` **iarch011_fixb_pair_dump** → iarch011_verbatim_entailment_pair_diagnostic.py  ·scr· iarch011_fixb_pair_dump.py:1
- `S` **_REFY** → _REFERENCE_LIST_RE  ·scr· iarch011_parallel_verify_gate.py:54
- `S` **_SYN** → _SYNTHETIC_FIXTURE_ROWS  ·scr· iarch011_prd_abstract_conclusion_replay_harness.py:104
- `S` **_check_redaction_landmine** → _check_redaction_duplicate_edge_case  ·scr· iarch011_prd_abstract_conclusion_replay_harness.py:386
- `S` **cs** → content_sample  ·scr· iwire016_chrome_classifier_bakeoff.py:109
- `A` **token_explosion** → high_output_token_count  ·scr· live_monitor.py:654
- `F` **playwright_fire_test.py** → playwright_exhaustive_ui_audit.py  ·scr· playwright_fire_test.py:1
- `S` **_ci_zyte_saved** → _content_integrity_recovered_count  ·scr· run_honest_sweep_r3.py:15675
- `S` **build_known_words_from_evidence** → build_corpus_vocabulary_from_evidence  ·scr· run_honest_sweep_r3.py:17850
- `S` **_PAID_PATH_WINNER_FLAGS** → _PAID_PATH_ENRICHMENT_FLAGS  ·scr· run_honest_sweep_r3.py:21675
- `F` **pathB_capture.py** → benchmark_run_capture.py  ·src· pathB_capture.py:1
- `F` **pathB_runner.py** → benchmark_gate_runner.py  ·src· pathB_runner.py:1
- `S` **_jo_doi** → _journal_only_doi  ·src· live_retriever.py:7142
- `S` **_w5_loop_idx** → _llm_tiering_batch_index  ·src· live_retriever.py:7192
- `S` **_w2_weight** → _content_relevance_weight  ·src· live_retriever.py:7220
- `S` **_w2_label** → _content_relevance_label  ·src· live_retriever.py:7221
- `S` **_m2_dt** → _stamp_document_genre  ·src· live_retriever.py:7261
- `S` **_jo_doi_resolved** → _journal_only_doi_resolved  ·src· live_retriever.py:7304
- `S` **_jo_doi_m** → _journal_only_doi_match  ·src· live_retriever.py:7306
- `S` **_jo_canon** → _journal_only_canon_url  ·src· live_retriever.py:7309
- `S` **_u21_repaired** → _empty_fetch_repaired  ·src· live_retriever.py:7339
- `S` **_u21_recovered** → _recovered_from_refetch  ·src· live_retriever.py:7341
- `S` **_cf_quote** → _cleaned_fetch_result  ·src· live_retriever.py:7572
- `S` **_pd_res** → _pubdate_resolved_flag  ·src· live_retriever.py:7678
- `S` **_w5_tier_batch_idx** → _tier_batch_index  ·src· live_retriever.py:7774
- `S` **_b4_relevance_weights** → _relevance_gate_weights  ·src· live_retriever.py:7783
- `S` **_row0** → _zero_weight_row  ·src· live_retriever.py:7916
- `S` **_auth0** → _zero_weight_authority  ·src· live_retriever.py:7935
- `S` **_mv_now** → _match_validate_snapshot_now  ·src· live_retriever.py:7963
- `S` **_mv_checked** → _match_validate_checked  ·src· live_retriever.py:7964
- `S` **_mv_rejected** → _match_validate_rejected  ·src· live_retriever.py:7965
- `S` **_mv_failopen** → _match_validate_failopen  ·src· live_retriever.py:7966
- `S` **_w2_on** → _content_relevance_enabled_flag  ·src· live_retriever.py:8057
- `S` **_b4_gate** → _relevance_gate  ·src· live_retriever.py:8146
- `S` **_w2_report** → _content_relevance_report  ·src· live_retriever.py:8150