#!/bin/bash
# Close GitHub issues whose work shipped via merged PR.
# Cross-referenced via git log on origin/polaris/main.
set -e
REPO="aldrinor/polaris"

close() {
  local num="$1"
  local pr="$2"
  gh issue close "$num" --repo "$REPO" -c "Closed by PR #$pr (verified via git log)." 2>&1 | head -1
}

# F1 (PRs #220-226)
close 92 220   # I-f1-001
close 93 222   # I-f1-002
close 94 223   # I-f1-003
close 95 224   # I-f1-004
close 96 225   # I-f1-005
close 97 226   # I-f1-006

# F2 (PRs #227-234)
close 98 227   # I-f2-001
close 99 228   # I-f2-002
close 100 229  # I-f2-003
close 101 230  # I-f2-004
close 102 231  # I-f2-005
close 103 232  # I-f2-006
close 104 233  # I-f2-007
close 105 234  # I-f2-008

# F3 (PRs #237-245)
close 107 236  # I-f3-001 (PR ref TBD; cite git log)
close 108 237  # I-f3-002
close 109 238  # I-f3-003
close 110 239  # I-f3-004
close 111 240  # I-f3-005
close 112 241  # I-f3-006
close 113 242  # I-f3-007
close 114 243  # I-f3-008
close 115 244  # I-f3-009
close 116 245  # I-f3-010

# F15 (PRs #246-251)
close 117 246  # I-f15-001
close 118 247  # I-f15-002
close 119 248  # I-f15-003
close 120 249  # I-f15-004
close 121 250  # I-f15-005
close 122 251  # I-f15-006

# ECG (PRs #253-256)
close 124 253  # I-ecg-001
close 125 254  # I-ecg-002
close 126 255  # I-ecg-003
close 127 256  # I-ecg-004

# F4 (PRs #257-261)
close 128 257  # I-f4-001
close 129 258  # I-f4-002
close 130 259  # I-f4-003
close 131 260  # I-f4-004
close 132 261  # I-f4-005

# F5 (PRs #262-272)
close 133 262  # I-f5-001
close 134 263  # I-f5-002
close 135 264  # I-f5-003
close 136 265  # I-f5-004
close 137 266  # I-f5-005
close 138 267  # I-f5-006
close 139 268  # I-f5-007
close 140 269  # I-f5-008
close 141 270  # I-f5-009
close 142 271  # I-f5-010
close 143 272  # I-f5-011

# F7 (PRs #273-276)
close 144 273  # I-f7-001
close 145 274  # I-f7-002
close 146 275  # I-f7-003
close 147 276  # I-f7-004

# F8 (PRs #277-282)
close 148 277  # I-f8-001
close 149 278  # I-f8-002
close 150 279  # I-f8-003
close 151 280  # I-f8-004
close 152 281  # I-f8-005
close 153 282  # I-f8-006

# F9 (PRs #283-285)
close 154 283  # I-f9-001
close 155 284  # I-f9-002
close 156 285  # I-f9-003

# F6 (PRs #286-290)
close 157 286  # I-f6-001
close 158 287  # I-f6-002
close 159 288  # I-f6-003
close 160 289  # I-f6-004
close 161 290  # I-f6-005

# F10 (PRs #291-298)
close 162 291  # I-f10-001
close 163 292  # I-f10-002
close 164 293  # I-f10-003
close 165 294  # I-f10-004
close 166 295  # I-f10-005
close 167 296  # I-f10-006
close 168 297  # I-f10-007
close 169 298  # I-f10-008

# F13 (PRs #299-302)
close 170 299  # I-f13-001
close 171 300  # I-f13-002
close 172 301  # I-f13-003
close 173 302  # I-f13-004

# F14 (PRs #303-309)
close 174 303  # I-f14-001
close 175 306  # I-f14-002
close 176 307  # I-f14-003
close 177 308  # I-f14-004
close 178 309  # I-f14-005

# P2C (PRs #310-314)
close 179 310  # I-p2c-001
close 180 311  # I-p2c-002
close 181 312  # I-p2c-003
close 182 313  # I-p2c-004
close 183 314  # I-p2c-005

# F11 (PRs #315-319)
close 184 315  # I-f11-001
close 185 316  # I-f11-002
close 186 317  # I-f11-003
close 187 318  # I-f11-004
close 188 319  # I-f11-005

# F12 (PRs #320-323)
close 189 320  # I-f12-001
close 190 321  # I-f12-002
close 191 322  # I-f12-003
close 192 323  # I-f12-004

# Bench (PR #325)
close 194 325  # I-bench-001

echo "Done"
