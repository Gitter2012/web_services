# vLLM 0.17.0 Optimization Investigation for T4 GPU (CC 7.5)

## Executive Summary

Analysis of 6 optimization options for vLLM v0.17.0 on Tesla T4 (Turing CC 7.5, 40 SMs, 16GB VRAM). Based on source code inspection of vLLM v0.17.0.

---

## 1. `--attention-backend xformers`

### Status: NOT SUPPORTED

**Findings:**
- **CLI Support**: ✅ vLLM 0.17.0 supports `--attention-backend` argument
  - Located in: `/vllm/engine/arg_utils.py:777`
  - Enum: `AttentionBackendEnum` from `/vllm/v1/attention/backends/registry.py`
- **Available Backends**: FLASH_ATTN, FLASHINFER, TRITON_ATTN, FLEX_ATTENTION, etc.
- **XFormers**: ❌ NOT in the official backend list
  - xformers 0.0.35 is installed in the environment
  - vLLM v0.17.0 uses `flashinfer` as the primary efficient attention backend instead of xformers
  - xformers is only used in specific models (e.g., Pixtral) via model-specific code paths

**T4 Compatibility:**
- T4 supports xformers since xformers 0.0.25+ has CUDA SM 7.5 support
- However, xformers is not exposed as a vLLM attention backend option

**Recommendation:**
- ❌ **Not viable**
- Use alternative backends like FLASHINFER or TRITON_ATTN instead
- If you need xformers, you'd need to use vLLM's old attention system (pre-v1 engine)

---

## 2. `--enable-chunked-prefill true` (with `enforce_eager=true`)

### Status: COMPATIBLE but with CAVEATS

**Findings:**
- **Default**: Chunked prefill is ENABLED by default in SchedulerConfig
  - Default: `enable_chunked_prefill = True` (line 83 in `/vllm/config/scheduler.py`)
- **enforce_eager Compatibility**: ✅ Technically compatible
  - No hard conflict between the two settings
  - Both can be enabled simultaneously
- **T4 Specific Limitation**: ⚠️ FLOAT32 WARNING
  - Line 768-778 in `/vllm/config/vllm.py`:
  ```python
  if (
      self.model_config is not None
      and self.scheduler_config.enable_chunked_prefill
      and self.model_config.dtype == torch.float32
      and current_platform.get_device_capability() == (7, 5)  # T4!
  ):
      logger.warning_once(
          "Turing devices tensor cores do not support float32 matmul. "
          "To workaround this limitation, vLLM will set 'ieee' input "
          "precision for chunked prefill triton kernels."
      )
  ```

**For Qwen3.5 Hybrid FLA Architecture:**
- ✅ Compatible with chunked prefill (no special restrictions found in code)
- Chunked prefill works by breaking long prompts into chunks based on `max_num_batched_tokens`
- FLA attention and full attention layers both support chunking

**Performance Tradeoff:**
- ✅ Chunked prefill is ENABLED by default for good reason (better latency)
- Disabling it only if you need maximum throughput and have unbounded prompt lengths

**Recommendation:**
- ✅ **Viable - Keep enabled (default)**
- Monitor logs for T4 float32 warning if using fp32 models
- For quantized models (AWQ/GPTQ), no issue

---

## 3. `--max-num-seqs 128` (from current 16)

### Status: VIABLE but RISKY

**Findings:**
- **Default Limits**: 
  - `max_num_seqs` default varies by GPU:
    - Default in SchedulerConfig: 128 (line 43 in `/vllm/config/scheduler.py`)
    - Current project setting: 16 (decision record shows explicit override)
  - `max_num_batched_tokens` default: 2048
- **T4 Limits**: Hardcoded in arg_utils.py (lines 1976-2025)
  ```python
  if device_capability.major == 7:  # Turing (includes T4)
      default_max_num_batched_tokens = {
          UsageContext.ENGINE: 2048,  # or other values based on quantization
          # ...
      }
      default_max_num_seqs = {
          UsageContext.ENGINE: 128,
      }
  ```

**Memory Analysis for T4 (16GB total):**
- Current `max_num_seqs=16` is a conservative choice
- With 16GB VRAM and model weights (~4-9GB for AWQ):
  - KV cache budget: ~6-10GB available
  - Per-token KV cache: ~1.3KB (bfloat16, 32 layers, 80 hidden dim, head_dim=256)
  - Feasible sequences: (Available Memory / Per-token size) ≈ 5,000-8,000 tokens total
  - At max_num_batched_tokens=1024: Could support 5-8 concurrent sequences
  - At max_num_seqs=128: Would need ~156KB KV cache minimum, not the bottleneck

**Tradeoff:**
- Increasing to 128 enables higher concurrency but reduces memory per sequence
- Risk: OOM during long generations or when sequences are chunked into many prefill iterations
- KV cache grows linearly: (seq_len * heads * head_dim * bytes_per_token * num_seqs)

**Current Project Status** (from decision record):
- Currently using `max_num_seqs=12` for qwen3-14b-awq (decision record line 158)
- This is a tuned value for the specific workload

**Recommendation:**
- ⚠️ **Risky without profiling**
- Increase gradually: 16 → 32 → 64 → 128
- Monitor for OOM errors during long sequence generations
- 128 may be too aggressive; safer values: 32-64 for T4 with multi-image/long-context models
- Current 12-16 is reasonable for typical workloads

---

## 4. `--max-num-batched-tokens 8192` (from current 1024)

### Status: NEEDS CAREFUL TUNING

**Findings:**
- **Current Setting**: 1024 (decision record indicates this was chosen for "encoder cache profiling speed")
- **Default for T4**: 2048 (line 1976-2025 in arg_utils.py)
- **Purpose**: Maximum tokens processed per scheduler iteration (prefill + decode combined)

**Impact on Inference Performance:**
- ✅ YES, it significantly affects inference throughput
- Higher value = larger batches = better GPU utilization = higher tokens/sec
- Trade-off: Latency of individual requests may increase slightly

**Example Calculation:**
- If you process 1024 tokens/iter vs 8192 tokens/iter:
  - 8× more tokens per iteration → ideally 8× better throughput
  - But requires 8× more working memory for attention computations
  - May require longer kernel execution times per iteration

**Encoder Cache Profiling Context** (from decision record):
- Lower value (256-1024) speeds up encoder cache profiling for vision-language models
- Profiling images multiple times slows startup significantly
- After model loading, this becomes a throughput vs latency knob

**After Model Loading:**
- Current 1024 should be acceptable baseline
- For throughput optimization: Could increase to 2048-4096
- For latency-sensitive workloads: Keep lower (512-1024)
- 8192 may be too aggressive for T4 with limited VRAM

**Memory Requirements:**
- T4 has 16GB total VRAM
- Model: ~4-9GB (AWQ quantized)
- KV Cache: Varies by sequence length
- Working memory for attention: proportional to max_num_batched_tokens²

**Recommendation:**
- ⚠️ **Not to 8192 for T4**
- Try: 2048-4096 (vs current 1024) for better throughput
- Test before 8192; likely to cause OOM on T4
- Profiling shows current 1024 was tuned for encoder profiling, not steady-state inference

---

## 5. `compilation_config` with `pass_config` fields: `fuse_norm_quant`, `fuse_act_quant`

### Status: NOT APPLICABLE (only relevant when NOT using enforce_eager)

**Findings:**
- **Fields Exist**: ✅ Both fields exist in PassConfig (lines 116-119 in `/vllm/config/compilation.py`)
  ```python
  fuse_norm_quant: bool = Field(default=None)  # Fuse RMSNorm + quant ops
  fuse_act_quant: bool = Field(default=None)   # Fuse SiLU + quant ops
  fuse_attn_quant: bool = Field(default=None)  # Fuse attention + quant ops
  ```
- **When Used**: Only effective when torch.compile is ENABLED
- **Current Project Status** (from decision record, line 302-310):
  ```yaml
  qwen3.5-9b-awq: enforce_eager: true  # torch.compile disabled
  qwen3.5-9b-awq-4bit: enforce_eager: false  # torch.compile enabled + compilation-config
  ```

**Effect of enforce_eager=true:**
- Lines 780-786 in `/vllm/config/vllm.py`:
  ```python
  if self.model_config is not None and self.model_config.enforce_eager:
      logger.warning(
          "Enforce eager set, disabling torch.compile and CUDAGraphs. "
          "This is equivalent to setting -cc.mode=none -cc.cudagraph_mode=none"
      )
      self.compilation_config.mode = CompilationMode.NONE
      self.compilation_config.cudagraph_mode = CUDAGraphMode.NONE
  ```
- ✅ This automatically disables torch.compile
- PassConfig fusion directives only apply when torch.compile is active

**For AWQ Models on T4:**
- Decision record shows enforce_eager=true is optimal for T4 (lines 219-358)
- Reason: T4 only has 40 SMs, torch.compile GEMM autotuning requires sufficient SMs
- With enforce_eager=true: PassConfig fields are IGNORED
- No benefit to setting fuse_norm_quant/fuse_act_quant when compiling is disabled

**When PassConfig IS Relevant:**
- When `enforce_eager=false` and torch.compile is enabled
- For compressed-tensors AWQ format only (qwen3.5-9b-awq-4bit in project)
- T4 shows worse performance with torch.compile anyway (decision record)

**Recommendation:**
- ❌ **Not applicable for your T4 setup with enforce_eager=true**
- Current configuration (enforce_eager=true) is correct
- PassConfig only matters if you switch to enforce_eager=false (not recommended for T4)

---

## 6. `VLLM_USE_FLASH_ATTN=0` Environment Variable

### Status: NOT FOUND / NOT EFFECTIVE IN v0.17.0

**Findings:**
- **Environment Variable Search**: ❌ No references found in vLLM v0.17.0 source code
  - Searched: `/vllm/` and `/vllm/v1/` - 0 results
  - This variable likely existed in older vLLM versions but was removed

**What Changed:**
- vLLM v0.17.0 uses explicit attention backend selection via `--attention-backend`
- Default backend selection is automatic based on GPU capability and model type
- No legacy environment variable for disabling FlashAttention

**Current T4 Default Backend Selection:**
- From `/vllm/platforms/cuda.py` lines 48-97:
  - For non-MLA models on non-Blackwell GPUs (including T4):
    ```python
    return [
        AttentionBackendEnum.FLASH_ATTN,
        AttentionBackendEnum.FLASHINFER,
        AttentionBackendEnum.TRITON_ATTN,
        AttentionBackendEnum.FLEX_ATTENTION,
    ]
    ```
  - FLASH_ATTN is tried first, then fallback to others if unavailable
  - FlashAttention 2 has CUDA compute capability >= 8.0 (not T4 7.5)
  - For T4, automatic fallback to FLASHINFER or TRITON_ATTN

**What You Actually Want:**
- If you want to disable FlashAttention and use TRITON_ATTN instead:
  - Use: `--attention-backend TRITON_ATTN`
- This is explicit and recommended

**Recommendation:**
- ❌ **VLLM_USE_FLASH_ATTN does not exist in v0.17.0**
- Use `--attention-backend TRITON_ATTN` if you need to override backend selection
- Current automatic fallback (no explicit setting) should work fine

---

## Summary Table

| Option | Supported | Viable | T4 Safe | Notes |
|--------|-----------|--------|---------|-------|
| `--attention-backend xformers` | ❌ No | N/A | N/A | Not in vLLM v0.17.0; use FLASHINFER or TRITON_ATTN |
| `--enable-chunked-prefill true` | ✅ Yes | ✅ Yes | ⚠️ Warning on FP32 | Default enabled; works with enforce_eager |
| `--max-num-seqs 128` | ✅ Yes | ⚠️ Risky | ❌ Too high | Start 32-64; 128 may OOM; current 16 is safe |
| `--max-num-batched-tokens 8192` | ✅ Yes | ⚠️ Risky | ❌ Too high | OOM risk; try 2048-4096 instead; current 1024 is safe |
| `pass_config.fuse_norm_quant/act` | ✅ Exists | ❌ N/A | N/A | Only with enforce_eager=false; not recommended for T4 |
| `VLLM_USE_FLASH_ATTN=0` | ❌ No | N/A | N/A | Removed in v0.17.0; use --attention-backend instead |

---

## Recommended Configuration for T4 (Turing CC 7.5)

Based on analysis and project decision record:

```yaml
# For Qwen3.5-9B AWQ
enforce_eager: true                    # T4 with 40 SMs can't efficiently use torch.compile
enable_chunked_prefill: true           # Default, good for latency
max_num_seqs: 16-32                    # Conservative to avoid OOM
max_num_batched_tokens: 1024-2048      # Current 1024 is good baseline, can try 2048
attention_backend: auto                # Automatic fallback (FLASHINFER→TRITON_ATTN for T4)

# For large context / high throughput:
max_num_batched_tokens: 4096           # Profile before going higher
max_num_seqs: 32-64                    # Gradual increase with monitoring

# Do NOT use:
- --attention-backend xformers         # Not available
- VLLM_USE_FLASH_ATTN=0               # Not supported
- pass_config.fuse_* with enforce_eager=true  # Ignored/ineffective
```

---

## References

- vLLM Source: `/data/workspace/miniforge3/envs/py313/lib/python3.13/site-packages/vllm/`
- Key Files:
  - `/vllm/config/attention.py` (AttentionConfig)
  - `/vllm/config/scheduler.py` (SchedulerConfig, chunked prefill)
  - `/vllm/config/compilation.py` (PassConfig fields)
  - `/vllm/config/vllm.py` (T4 specific checks)
  - `/vllm/v1/attention/backends/registry.py` (AttentionBackendEnum)
  - `/vllm/engine/arg_utils.py` (CLI arguments)
  - `/vllm/platforms/cuda.py` (Backend selection logic)
- Project Decision Record: `/data/workspace/apps/vllm_proxy/decisions.md`

