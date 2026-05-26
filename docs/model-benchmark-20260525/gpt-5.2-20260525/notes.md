# GPT-5.2 单模型复测运行 notes

- started_at: `2026-05-25T20:02:36`
- model: `GPT-5.2`
- runtime: `traecli --yolo`
- cases: `11` = 原 benchmark 4 任务 x 2 次 + 3 个真实用例
- output_dir: `docs/model-benchmark-20260525/gpt-5.2-20260525`

## Running Log

- `2026-05-25T20:02:36` START `canonical_benchmark/short_judgment-1` timeout=180s prompt_chars=78
- `2026-05-25T20:02:36` START `canonical_benchmark/short_judgment-2` timeout=180s prompt_chars=78
  - `2026-05-25T20:02:40` `canonical_benchmark/short_judgment-2` permission_mode=bypass_permissions
  - `2026-05-25T20:02:40` `canonical_benchmark/short_judgment-1` permission_mode=bypass_permissions
  - `2026-05-25T20:02:41` `canonical_benchmark/short_judgment-2` tool_calls=1, tool_names={'Read': 1}
  - `2026-05-25T20:02:42` `canonical_benchmark/short_judgment-1` tool_calls=1, tool_names={'Read': 1}
  - `2026-05-25T20:02:54` `canonical_benchmark/short_judgment-1` first assistant content at stream line 23, chars=180
  - `2026-05-25T20:02:55` `canonical_benchmark/short_judgment-1` result subtype=success, is_error=False, duration_ms=15458, permission_mode=bypass_permissions
  - `2026-05-25T20:02:56` `canonical_benchmark/short_judgment-2` first assistant content at stream line 23, chars=200
- `2026-05-25T20:02:56` END `canonical_benchmark/short_judgment-1` status=ok latency=20.54s chars=180 parse_ok=True tools=1 error=None
- `2026-05-25T20:02:56` START `canonical_benchmark/structured_json-1` timeout=180s prompt_chars=104
  - `2026-05-25T20:02:57` `canonical_benchmark/short_judgment-2` result subtype=success, is_error=False, duration_ms=17244, permission_mode=bypass_permissions
- `2026-05-25T20:02:58` END `canonical_benchmark/short_judgment-2` status=ok latency=22.17s chars=200 parse_ok=True tools=1 error=None
- `2026-05-25T20:02:58` START `canonical_benchmark/structured_json-2` timeout=180s prompt_chars=104
  - `2026-05-25T20:03:00` `canonical_benchmark/structured_json-1` permission_mode=bypass_permissions
  - `2026-05-25T20:03:02` `canonical_benchmark/structured_json-2` permission_mode=bypass_permissions
  - `2026-05-25T20:03:02` `canonical_benchmark/structured_json-1` tool_calls=1, tool_names={'Read': 1}
  - `2026-05-25T20:03:04` `canonical_benchmark/structured_json-2` tool_calls=1, tool_names={'Read': 1}
  - `2026-05-25T20:03:20` `canonical_benchmark/structured_json-1` first assistant content at stream line 23, chars=513
  - `2026-05-25T20:03:22` `canonical_benchmark/structured_json-1` result subtype=success, is_error=False, duration_ms=21722, permission_mode=bypass_permissions
- `2026-05-25T20:03:22` END `canonical_benchmark/structured_json-1` status=ok latency=26.26s chars=513 parse_ok=True tools=1 error=None
- `2026-05-25T20:03:22` START `canonical_benchmark/stage2_ranking-1` timeout=180s prompt_chars=234
  - `2026-05-25T20:03:24` `canonical_benchmark/structured_json-2` first assistant content at stream line 23, chars=703
  - `2026-05-25T20:03:26` `canonical_benchmark/structured_json-2` result subtype=success, is_error=False, duration_ms=23651, permission_mode=bypass_permissions
- `2026-05-25T20:03:26` END `canonical_benchmark/structured_json-2` status=ok latency=28.47s chars=703 parse_ok=True tools=1 error=None
- `2026-05-25T20:03:26` START `canonical_benchmark/stage2_ranking-2` timeout=180s prompt_chars=234
  - `2026-05-25T20:03:26` `canonical_benchmark/stage2_ranking-1` permission_mode=bypass_permissions
  - `2026-05-25T20:03:28` `canonical_benchmark/stage2_ranking-1` tool_calls=1, tool_names={'Read': 1}
  - `2026-05-25T20:03:30` `canonical_benchmark/stage2_ranking-2` permission_mode=bypass_permissions
  - `2026-05-25T20:03:32` `canonical_benchmark/stage2_ranking-2` tool_calls=1, tool_names={'Read': 1}
  - `2026-05-25T20:03:41` `canonical_benchmark/stage2_ranking-1` first assistant content at stream line 23, chars=284
  - `2026-05-25T20:03:42` `canonical_benchmark/stage2_ranking-1` result subtype=success, is_error=False, duration_ms=15716, permission_mode=bypass_permissions
- `2026-05-25T20:03:43` END `canonical_benchmark/stage2_ranking-1` status=ok latency=20.33s chars=284 parse_ok=True tools=1 error=None
- `2026-05-25T20:03:43` START `canonical_benchmark/stage3_synthesis-1` timeout=180s prompt_chars=224
  - `2026-05-25T20:03:44` `canonical_benchmark/stage2_ranking-2` first assistant content at stream line 23, chars=282
  - `2026-05-25T20:03:46` `canonical_benchmark/stage2_ranking-2` result subtype=success, is_error=False, duration_ms=15645, permission_mode=bypass_permissions
- `2026-05-25T20:03:47` END `canonical_benchmark/stage2_ranking-2` status=ok latency=20.4s chars=282 parse_ok=True tools=1 error=None
- `2026-05-25T20:03:47` START `canonical_benchmark/stage3_synthesis-2` timeout=180s prompt_chars=224
  - `2026-05-25T20:03:48` `canonical_benchmark/stage3_synthesis-1` permission_mode=bypass_permissions
  - `2026-05-25T20:03:49` `canonical_benchmark/stage3_synthesis-1` tool_calls=1, tool_names={'Read': 1}
  - `2026-05-25T20:03:51` `canonical_benchmark/stage3_synthesis-2` permission_mode=bypass_permissions
  - `2026-05-25T20:03:52` `canonical_benchmark/stage3_synthesis-2` tool_calls=1, tool_names={'Read': 1}
  - `2026-05-25T20:04:09` `canonical_benchmark/stage3_synthesis-1` first assistant content at stream line 23, chars=795
  - `2026-05-25T20:04:11` `canonical_benchmark/stage3_synthesis-1` result subtype=success, is_error=False, duration_ms=22974, permission_mode=bypass_permissions
- `2026-05-25T20:04:11` END `canonical_benchmark/stage3_synthesis-1` status=ok latency=28.61s chars=795 parse_ok=True tools=1 error=None
- `2026-05-25T20:04:11` START `real_usecase/usecase_1` timeout=660s prompt_chars=234
  - `2026-05-25T20:04:13` `canonical_benchmark/stage3_synthesis-2` first assistant content at stream line 23, chars=700
  - `2026-05-25T20:04:14` `canonical_benchmark/stage3_synthesis-2` result subtype=success, is_error=False, duration_ms=23442, permission_mode=bypass_permissions
- `2026-05-25T20:04:15` END `canonical_benchmark/stage3_synthesis-2` status=ok latency=28.23s chars=700 parse_ok=True tools=1 error=None
- `2026-05-25T20:04:15` START `real_usecase/usecase_2` timeout=660s prompt_chars=811
  - `2026-05-25T20:04:15` `real_usecase/usecase_1` permission_mode=bypass_permissions
  - `2026-05-25T20:04:17` `real_usecase/usecase_1` tool_calls=1, tool_names={'Read': 1}
  - `2026-05-25T20:04:19` `real_usecase/usecase_2` permission_mode=bypass_permissions
  - `2026-05-25T20:04:21` `real_usecase/usecase_2` tool_calls=1, tool_names={'Read': 1}
  - `2026-05-25T20:05:14` `real_usecase/usecase_1` first assistant content at stream line 23, chars=3085
  - `2026-05-25T20:05:16` `real_usecase/usecase_1` result subtype=success, is_error=False, duration_ms=60601, permission_mode=bypass_permissions
- `2026-05-25T20:05:16` END `real_usecase/usecase_1` status=ok latency=64.81s chars=3085 parse_ok=True tools=1 error=None
- `2026-05-25T20:05:16` START `real_usecase/usecase_3` timeout=660s prompt_chars=589
  - `2026-05-25T20:05:21` `real_usecase/usecase_3` permission_mode=bypass_permissions
  - `2026-05-25T20:05:22` `real_usecase/usecase_3` tool_calls=1, tool_names={'Read': 1}
  - `2026-05-25T20:05:31` `real_usecase/usecase_2` tool_calls=5, tool_names={'Read': 1, 'WebSearch': 4}
  - `2026-05-25T20:06:27` `real_usecase/usecase_2` tool_calls=10, tool_names={'Read': 1, 'WebSearch': 9}
  - `2026-05-25T20:07:06` `real_usecase/usecase_3` first assistant content at stream line 23, chars=6231
  - `2026-05-25T20:07:07` `real_usecase/usecase_3` result subtype=success, is_error=False, duration_ms=106657, permission_mode=bypass_permissions
- `2026-05-25T20:07:08` END `real_usecase/usecase_3` status=ok latency=111.66s chars=6231 parse_ok=True tools=1 error=None
  - `2026-05-25T20:08:31` `real_usecase/usecase_2` first assistant content at stream line 43, chars=7264
  - `2026-05-25T20:08:32` `real_usecase/usecase_2` result subtype=success, is_error=False, duration_ms=252882, permission_mode=bypass_permissions
- `2026-05-25T20:08:32` END `real_usecase/usecase_2` status=ok latency=257.54s chars=7264 parse_ok=True tools=11 error=None

## Final Summary
```json
{
  "created_at": "2026-05-25T12:08:32Z",
  "model": "GPT-5.2",
  "used_traecli_y": true,
  "total_cases": 11,
  "success": 11,
  "failed": 0,
  "canonical_cases": 8,
  "canonical_success": 8,
  "canonical_parse_ok": 8,
  "real_cases": 3,
  "real_success": 3,
  "latency_seconds": {
    "p50": 28.23,
    "max": 257.54
  },
  "cases": [
    {
      "suite": "canonical_benchmark",
      "case_id": "short_judgment-1",
      "status": "ok",
      "latency_seconds": 20.54,
      "response_chars": 180,
      "parse_ok": true,
      "tool_calls": 1,
      "tool_result_errors": 0,
      "error": null,
      "actual_model": "GPT-5.2"
    },
    {
      "suite": "canonical_benchmark",
      "case_id": "short_judgment-2",
      "status": "ok",
      "latency_seconds": 22.17,
      "response_chars": 200,
      "parse_ok": true,
      "tool_calls": 1,
      "tool_result_errors": 0,
      "error": null,
      "actual_model": "GPT-5.2"
    },
    {
      "suite": "canonical_benchmark",
      "case_id": "structured_json-1",
      "status": "ok",
      "latency_seconds": 26.26,
      "response_chars": 513,
      "parse_ok": true,
      "tool_calls": 1,
      "tool_result_errors": 0,
      "error": null,
      "actual_model": "GPT-5.2"
    },
    {
      "suite": "canonical_benchmark",
      "case_id": "structured_json-2",
      "status": "ok",
      "latency_seconds": 28.47,
      "response_chars": 703,
      "parse_ok": true,
      "tool_calls": 1,
      "tool_result_errors": 0,
      "error": null,
      "actual_model": "GPT-5.2"
    },
    {
      "suite": "canonical_benchmark",
      "case_id": "stage2_ranking-1",
      "status": "ok",
      "latency_seconds": 20.33,
      "response_chars": 284,
      "parse_ok": true,
      "tool_calls": 1,
      "tool_result_errors": 0,
      "error": null,
      "actual_model": "GPT-5.2"
    },
    {
      "suite": "canonical_benchmark",
      "case_id": "stage2_ranking-2",
      "status": "ok",
      "latency_seconds": 20.4,
      "response_chars": 282,
      "parse_ok": true,
      "tool_calls": 1,
      "tool_result_errors": 0,
      "error": null,
      "actual_model": "GPT-5.2"
    },
    {
      "suite": "canonical_benchmark",
      "case_id": "stage3_synthesis-1",
      "status": "ok",
      "latency_seconds": 28.61,
      "response_chars": 795,
      "parse_ok": true,
      "tool_calls": 1,
      "tool_result_errors": 0,
      "error": null,
      "actual_model": "GPT-5.2"
    },
    {
      "suite": "canonical_benchmark",
      "case_id": "stage3_synthesis-2",
      "status": "ok",
      "latency_seconds": 28.23,
      "response_chars": 700,
      "parse_ok": true,
      "tool_calls": 1,
      "tool_result_errors": 0,
      "error": null,
      "actual_model": "GPT-5.2"
    },
    {
      "suite": "real_usecase",
      "case_id": "usecase_1",
      "status": "ok",
      "latency_seconds": 64.81,
      "response_chars": 3085,
      "parse_ok": true,
      "tool_calls": 1,
      "tool_result_errors": 0,
      "error": null,
      "actual_model": "GPT-5.2"
    },
    {
      "suite": "real_usecase",
      "case_id": "usecase_2",
      "status": "ok",
      "latency_seconds": 257.54,
      "response_chars": 7264,
      "parse_ok": true,
      "tool_calls": 11,
      "tool_result_errors": 0,
      "error": null,
      "actual_model": "GPT-5.2"
    },
    {
      "suite": "real_usecase",
      "case_id": "usecase_3",
      "status": "ok",
      "latency_seconds": 111.66,
      "response_chars": 6231,
      "parse_ok": true,
      "tool_calls": 1,
      "tool_result_errors": 0,
      "error": null,
      "actual_model": "GPT-5.2"
    }
  ]
}
```
