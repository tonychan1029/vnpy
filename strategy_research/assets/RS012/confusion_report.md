# RS012 混淆矩阵报告（context_tag 判定 vs 操作性真值 GT v1.1）

- 预测文件: `D:\AIprj\vnpy\strategy_research\assets\RS012\incoming\predictions.csv`

## RB（n=2793）
| GT\PRED | TREND_UP | TREND_DN | RANGE | BREAKOUT | REVERSAL | UNDEFINED |
|---|---|---|---|---|---|---|
| TREND_UP | 139 | 126 | 76 | 109 | 23 | 0 |
| TREND_DN | 178 | 169 | 106 | 148 | 31 | 0 |
| RANGE | 149 | 119 | 86 | 46 | 47 | 0 |
| BREAKOUT | 208 | 175 | 106 | 167 | 30 | 0 |
| REVERSAL | 181 | 130 | 87 | 126 | 31 | 0 |
| UNDEFINED | 0 | 0 | 0 | 0 | 0 | 0 |

## CU（n=3569）
| GT\PRED | TREND_UP | TREND_DN | RANGE | BREAKOUT | REVERSAL | UNDEFINED |
|---|---|---|---|---|---|---|
| TREND_UP | 190 | 174 | 90 | 122 | 30 | 0 |
| TREND_DN | 177 | 182 | 111 | 128 | 40 | 0 |
| RANGE | 200 | 197 | 153 | 85 | 58 | 0 |
| BREAKOUT | 279 | 180 | 143 | 231 | 39 | 0 |
| REVERSAL | 211 | 209 | 130 | 163 | 47 | 0 |
| UNDEFINED | 0 | 0 | 0 | 0 | 0 | 0 |

## AG（n=4369）
| GT\PRED | TREND_UP | TREND_DN | RANGE | BREAKOUT | REVERSAL | UNDEFINED |
|---|---|---|---|---|---|---|
| TREND_UP | 206 | 166 | 109 | 130 | 30 | 0 |
| TREND_DN | 245 | 253 | 114 | 168 | 45 | 0 |
| RANGE | 293 | 250 | 126 | 94 | 83 | 0 |
| BREAKOUT | 385 | 379 | 239 | 280 | 67 | 0 |
| REVERSAL | 218 | 183 | 117 | 163 | 26 | 0 |
| UNDEFINED | 0 | 0 | 0 | 0 | 0 | 0 |

## M（n=2872）
| GT\PRED | TREND_UP | TREND_DN | RANGE | BREAKOUT | REVERSAL | UNDEFINED |
|---|---|---|---|---|---|---|
| TREND_UP | 115 | 102 | 44 | 80 | 26 | 0 |
| TREND_DN | 172 | 189 | 109 | 133 | 26 | 0 |
| RANGE | 150 | 142 | 87 | 52 | 44 | 0 |
| BREAKOUT | 272 | 226 | 128 | 205 | 34 | 0 |
| REVERSAL | 165 | 134 | 96 | 121 | 20 | 0 |
| UNDEFINED | 0 | 0 | 0 | 0 | 0 | 0 |

## MA（n=2784）
| GT\PRED | TREND_UP | TREND_DN | RANGE | BREAKOUT | REVERSAL | UNDEFINED |
|---|---|---|---|---|---|---|
| TREND_UP | 113 | 139 | 72 | 65 | 26 | 0 |
| TREND_DN | 176 | 175 | 116 | 109 | 25 | 0 |
| RANGE | 130 | 126 | 78 | 57 | 34 | 0 |
| BREAKOUT | 266 | 176 | 130 | 160 | 34 | 0 |
| REVERSAL | 157 | 160 | 101 | 143 | 16 | 0 |
| UNDEFINED | 0 | 0 | 0 | 0 | 0 | 0 |

## TA（n=2780）
| GT\PRED | TREND_UP | TREND_DN | RANGE | BREAKOUT | REVERSAL | UNDEFINED |
|---|---|---|---|---|---|---|
| TREND_UP | 124 | 109 | 70 | 74 | 17 | 0 |
| TREND_DN | 173 | 169 | 135 | 102 | 40 | 0 |
| RANGE | 123 | 146 | 89 | 63 | 50 | 0 |
| BREAKOUT | 222 | 189 | 129 | 177 | 26 | 0 |
| REVERSAL | 153 | 157 | 80 | 135 | 28 | 0 |
| UNDEFINED | 0 | 0 | 0 | 0 | 0 | 0 |

## 合并（n=19167）
| GT\PRED | TREND_UP | TREND_DN | RANGE | BREAKOUT | REVERSAL | UNDEFINED |
|---|---|---|---|---|---|---|
| TREND_UP | 887 | 816 | 461 | 580 | 152 | 0 |
| TREND_DN | 1121 | 1137 | 691 | 788 | 207 | 0 |
| RANGE | 1045 | 980 | 619 | 397 | 316 | 0 |
| BREAKOUT | 1632 | 1325 | 875 | 1220 | 230 | 0 |
| REVERSAL | 1085 | 973 | 611 | 851 | 168 | 0 |
| UNDEFINED | 0 | 0 | 0 | 0 | 0 | 0 |

## 预注册判读（勿临场修改）
- RANGE top-pred 精确率 31.1% <40% → **门控存疑**，触发 RS012 §4 预案
