# I-hygiene-001 root-cleanup inventory

Source: `C:\POLARIS` enumerated 2026-05-11.
Total entries: 178 | KEEP: 35 | ARCHIVE: 142 | INSPECT: 1

## KEEP (essential, must remain at root)

[D] .claude — essential project structure
[D] .codex — essential project structure
[F] .dockerignore — essential project structure
[F] .env — essential project structure
[F] .env.example — essential project structure
[D] .git — essential project structure
[D] .github — essential project structure
[F] .gitignore — essential project structure
[D] .legacy — essential project structure
[D] .private — essential project structure
[F] CLAUDE.md — essential project structure
[F] Dockerfile — essential project structure
[F] README.md — essential project structure
[F] architecture.md — essential project structure
[D] archive — essential project structure
[D] config — essential project structure
[D] data — essential project structure
[F] docker-compose.yml — essential project structure
[D] docs — essential project structure
[F] ground_rules.md — essential project structure
[D] helm — essential project structure
[D] logs — essential project structure
[D] memory — essential project structure
[D] models — essential project structure
[D] outputs — essential project structure
[D] polaris-controls — essential project structure
[F] pytest.ini — essential project structure
[F] requirements-orchestrator.txt — essential project structure
[F] requirements-v6.txt — essential project structure
[F] requirements.txt — essential project structure
[D] scripts — essential project structure
[D] src — essential project structure
[D] state — essential project structure
[D] tests — essential project structure
[D] web — essential project structure

## ARCHIVE (move to archive/2026-05-11-root-hygiene/)

[D] .codex_tmp_m_int_6_v1_review_fresh — matches archive pattern: ^\.codex_tmp.*$
[D] .codex_tmp_md3_review — matches archive pattern: ^\.codex_tmp.*$
[D] .codex_tmp_scope_gate — matches archive pattern: ^\.codex_tmp.*$
[F] .coverage — matches archive pattern: ^\.coverage$
[D] .pytest-cache — matches archive pattern: ^\.pytest-cache.*$
[D] .pytest-cache-local — matches archive pattern: ^\.pytest-cache.*$
[D] .pytest_cache — matches archive pattern: ^\.pytest_cache.*$
[D] .pytest_cache_local — matches archive pattern: ^\.pytest_cache.*$
[D] .pytest_scope_gate_tmp2 — matches archive pattern: ^\.pytest_scope_gate_tmp.*$
[D] .pytest_tmp — matches archive pattern: ^\.pytest_tmp.*$
[D] .ruff_cache — matches archive pattern: ^\.ruff_cache$
[D] .tmp — matches archive pattern: ^\.tmp.*$
[D] .tmp-pytest — matches archive pattern: ^\.tmp.*$
[D] .tmp_pytest — matches archive pattern: ^\.tmp.*$
[D] .tmp_pytest_base — matches archive pattern: ^\.tmp.*$
[D] .tmp_pytest_m_int_2 — matches archive pattern: ^\.tmp.*$
[D] .tmp_pytest_m_int_3 — matches archive pattern: ^\.tmp.*$
[D] .tmp_pytest_m_live_1_review — matches archive pattern: ^\.tmp.*$
[D] .tmp_pytest_md3_review — matches archive pattern: ^\.tmp.*$
[D] .tmp_pytest_md3_review2 — matches archive pattern: ^\.tmp.*$
[D] POLARIS.tmppytest — matches archive pattern: ^POLARIS\.tmppytest$
[D] POLARIStmp_pytest_m_int_3_reviewbasetemp — matches archive pattern: ^POLARIStmp_pytest.*$
[D] __pycache__ — matches archive pattern: ^__pycache__$
[D] codex_cache_i_bug_107 — matches archive pattern: ^codex_cache_.*$
[D] codex_cache_i_bug_107_b — matches archive pattern: ^codex_cache_.*$
[D] codex_review_tmp_scope2 — matches archive pattern: ^codex_review_tmp.*$
[D] codex_review_tmp_workforce — matches archive pattern: ^codex_review_tmp.*$
[D] codex_tmp_billing_quota_store_review_alt — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_check — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug101_pytest_f14da804b7a045e1a94ff418f6069e0a — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_101_manual — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_101_manual_bad — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_101_manual_live_shape — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_101_review_b29519cc00af4bd29feae90730c607a1 — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_107 — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_107_b — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_107_iter3_manual — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_107_iter3_verify_run — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_107_manual — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_107_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_107_review_base — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_107_review_base2 — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_i_bug_107_review_writable — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_line_audit_manual — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_line_audit_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_10_v1_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_10_v1_review_rerun — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_10_v1_single — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_10_v1_single2 — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_10_v2_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_10_v2_review_fresh — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_10_v3_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_10_v3_review_probe — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_11_v1_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_11_v1_review_fresh_20260429 — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_11_v2_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_11_v2_review_fresh — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_11_v2_review_fresh_subset — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_5_v2_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_5_v3_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_5_v3_review_probe — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_5_v4_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_5_v4_review_fresh — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_5_v4_review_fresh2 — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_6_v1_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_7_v1_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_7_v1_review_fresh — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_7_v2_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_7_v2_review_alt — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_7_v2_single — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_7_v3_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_7_v3_review_fresh — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_9_v1_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_9_v1_review_single — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_9_v2_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_m_int_9_v2_review_fresh — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_md3_pytest — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_paid_eval_test — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_pytest — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_pytest_m11 — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_pytest_m15a_v2 — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_pytest_review — matches archive pattern: ^codex_tmp.*$
[D] codex_tmp_review — matches archive pattern: ^codex_tmp.*$
[D] dashboard_probe_f2ltuo3t — matches archive pattern: ^dashboard_probe.*$
[D] dashboard_probe_hhthuj3n — matches archive pattern: ^dashboard_probe.*$
[D] dashboard_probe_xdvktanm — matches archive pattern: ^dashboard_probe.*$
[D] dashboard_probe_znaia9ry — matches archive pattern: ^dashboard_probe.*$
[D] dashboard_probe_zw62d2fs — matches archive pattern: ^dashboard_probe.*$
[D] m10v2_manual_yz_33hqh — matches archive pattern: ^m\d+v\d+.*$
[D] m10v3_one_wlcrnh2f — matches archive pattern: ^m\d+v\d+.*$
[D] m8_tmp_check — matches archive pattern: ^m8_.*$
[D] m8_v4_pytest — matches archive pattern: ^m8_.*$
[D] m9_v2_manual_verify — matches archive pattern: ^m9_.*$
[D] m9v2_pytest_run1 — matches archive pattern: ^m\d+v\d+.*$
[D] m_int_10_manual_57asn199 — matches archive pattern: ^m_int_.*_manual_.*$
[D] m_int_7_v2_manual_5fgxbzoc — matches archive pattern: ^m_int_.*_manual_.*$
[D] m_int_7_v3_manual_dhypw5bz — matches archive pattern: ^m_int_.*_manual_.*$
[D] m_live_4_r2_3qyr9r66 — matches archive pattern: ^m_live_.*$
[D] manual_pytest_base_m_int_7 — matches archive pattern: ^manual_pytest_.*$
[D] manual_pytest_base_m_int_7_ok — matches archive pattern: ^manual_pytest_.*$
[D] manual_review_scratch_m_int_10_v3 — matches archive pattern: ^manual_review_scratch.*$
[D] manual_review_scratch_m_int_9_v2 — matches archive pattern: ^manual_review_scratch.*$
[D] manual_tmp_m_int_3 — matches archive pattern: ^manual_tmp.*$
[D] manual_tmp_m_int_3_v3 — matches archive pattern: ^manual_tmp.*$
[D] md3_pytest_run2 — matches archive pattern: ^md3_pytest.*$
[D] md3_round3_manual_tmp — matches archive pattern: ^md3_.*_tmp$
[D] md3_round3_pytest_tmp — matches archive pattern: ^md3_.*_tmp$
[D] py_pytest_b6ae8d9d497443b4b0306f18bf9b8ee9 — matches archive pattern: ^py_pytest.*$
[D] pytest-cache-files-kds8u4s5 — matches archive pattern: ^pytest-cache-files-.*$
[D] pytest-cache-files-o969a6s7 — matches archive pattern: ^pytest-cache-files-.*$
[D] pytest-cache-files-szrlm1db — matches archive pattern: ^pytest-cache-files-.*$
[D] pytest-cache-files-tw8jzxb3 — matches archive pattern: ^pytest-cache-files-.*$
[D] pytest_basetemp_i_bug_085_r2 — matches archive pattern: ^pytest_basetemp.*$
[D] pytest_run_3842f3b95af34ad8b6f93080344d5110 — matches archive pattern: ^pytest_run_.*$
[D] pytest_run_554e954860ba4943a4f9f6097fe8541f — matches archive pattern: ^pytest_run_.*$
[D] pytest_run_ae0dcde87f184046b2b4b8ec9cc6f7ba — matches archive pattern: ^pytest_run_.*$
[D] python_mode_700_probe — matches archive pattern: ^python_mode_.*_probe$
[D] tmp2ef0ie4p — matches archive pattern: ^tmp.*$
[D] tmp2hhmpr2y — matches archive pattern: ^tmp.*$
[D] tmp3jencwbw — matches archive pattern: ^tmp.*$
[D] tmp48c8ko2m — matches archive pattern: ^tmp.*$
[D] tmp63988s99 — matches archive pattern: ^tmp.*$
[D] tmp8u9ua575 — matches archive pattern: ^tmp.*$
[D] tmp9h7v7fon — matches archive pattern: ^tmp.*$
[D] tmp_ae3ucgg — matches archive pattern: ^tmp.*$
[D] tmp_i_bug_085_pytest — matches archive pattern: ^tmp.*$
[D] tmp_pytest_m_int_0b — matches archive pattern: ^tmp.*$
[D] tmp_pytest_m_int_2 — matches archive pattern: ^tmp.*$
[D] tmp_pytest_m_int_3 — matches archive pattern: ^tmp.*$
[D] tmp_pytest_m_int_3_review — matches archive pattern: ^tmp.*$
[D] tmpa3ivn9br — matches archive pattern: ^tmp.*$
[D] tmpaufjwjy5 — matches archive pattern: ^tmp.*$
[D] tmpgb143kt_ — matches archive pattern: ^tmp.*$
[D] tmppvxh8fwq — matches archive pattern: ^tmp.*$
[D] tmpq5bdi1rl — matches archive pattern: ^tmp.*$
[D] tmptgnkdlz5 — matches archive pattern: ^tmp.*$
[D] tmpu2b082f6 — matches archive pattern: ^tmp.*$
[D] tmpuyki_w88 — matches archive pattern: ^tmp.*$
[D] tmpv1dnokk6 — matches archive pattern: ^tmp.*$
[D] tmpw2ru3yoj — matches archive pattern: ^tmp.*$
[D] tmpxnalraft — matches archive pattern: ^tmp.*$
[D] tmpyl5f0goo — matches archive pattern: ^tmp.*$

## INSPECT (Codex must adjudicate — unrecognized at root)

[D] archived_d — unrecognized — needs Codex review

## CLAUDE.md §4.1 snake_case naming violations (subset of ARCHIVE — recorded for the report)

- `POLARIS.tmppytest`