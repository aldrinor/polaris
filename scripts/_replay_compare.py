"""Compare two cp5 outputs (serial control vs concurrent treatment) for kept/dropped IDENTITY.

The kept sentence set of a section == its ``verified_text``; the dropped count == ``sentences_dropped``.
Byte-identical verified_text + identical verified/dropped counts across arms => the off-loop fix's
worker-thread concurrency changed NOTHING about the faithfulness verdict set. Exit 0 iff identical.
"""
import hashlib
import json
import sys


def _load(p):
    d = json.load(open(p, encoding="utf-8"))
    secs = {}
    for s in d["payload"]["section_drafts"]:
        secs[int(s["section_index"])] = {
            "verified_text": s.get("verified_text") or "",
            "sentences_verified": s.get("sentences_verified"),
            "sentences_dropped": s.get("sentences_dropped"),
            "is_gap_stub": s.get("is_gap_stub"),
        }
    return d, secs


def _sha(t):
    return hashlib.sha256(t.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def main():
    ctrl_path, treat_path = sys.argv[1], sys.argv[2]
    ctrl_d, ctrl = _load(ctrl_path)
    treat_d, treat = _load(treat_path)

    all_idx = sorted(set(ctrl) | set(treat))
    ok = True
    print(f"{'sec':>3} {'ctrl_v':>6} {'ctrl_d':>6} {'treat_v':>7} {'treat_d':>7} "
          f"{'ctrl_sha':>16} {'treat_sha':>16}  match")
    for i in all_idx:
        c = ctrl.get(i, {})
        t = treat.get(i, {})
        c_sha = _sha(c.get("verified_text", ""))
        t_sha = _sha(t.get("verified_text", ""))
        text_match = c.get("verified_text") == t.get("verified_text")
        cnt_match = (c.get("sentences_verified") == t.get("sentences_verified")
                     and c.get("sentences_dropped") == t.get("sentences_dropped"))
        m = text_match and cnt_match
        ok = ok and m
        print(f"{i:>3} {str(c.get('sentences_verified')):>6} {str(c.get('sentences_dropped')):>6} "
              f"{str(t.get('sentences_verified')):>7} {str(t.get('sentences_dropped')):>7} "
              f"{c_sha:>16} {t_sha:>16}  {'OK' if m else 'DIFFER'}")

    # whole-report identity too
    rep_c = ctrl_d["payload"]["assembled_report_md"]
    rep_t = treat_d["payload"]["assembled_report_md"]
    rep_match = rep_c == rep_t
    print(f"\nassembled_report_md: ctrl_sha={_sha(rep_c)} treat_sha={_sha(rep_t)} "
          f"len_ctrl={len(rep_c)} len_treat={len(rep_t)} match={rep_match}")
    ok = ok and rep_match

    print(f"\n=== VERDICT-SET IDENTITY: {'IDENTICAL (PASS)' if ok else 'DIVERGED (FAIL)'} ===")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
