"""Function-local FPCR for recomp/gen.py (fastball).

Every FP op of the SIMD lowering (runtime/core/simd.h) checks the guest FPCR for a directed rounding mode, flush to
zero or default NaN. It read c->fpcr each time, and since guest stores may alias the Cpu, that was a load per op: 5 %
of the samples in game code during a match once the V registers were in XMM registers (recomp/vregs.py). The helpers
now take the FPCR value (`Fpcr c`), and a generated function that calls them passes a local copy, FPCR, loaded at its
entry and again where the guest FPCR may have changed: after a call (fesetround and the like are ordinary
functions), after an SVC, and after its own MSR FPCR (`c->fpcr = ...; rt_fpcr_sync(c);`). gen.py puts RELOAD at
those places; finish() turns the markers into reloads in functions that use FPCR and drops them elsewhere.
"""
import re

# simd.h / simd_fp.h functions whose first parameter is `Fpcr c`.
HELPERS = [
    'cmp_d', 'cmp_s', 'fix_d', 'fix_s', 'fp_fma_d', 'fp_fma_s', 'fp_op_d', 'fp_op_s', 'frint_d', 'frint_s',
    'fromint_d', 'fromint_s', 'fromint_slow_d', 'fromint_slow_s', 'fz_d', 'fz_s', 'minmax_d', 'minmax_s', 'nan1_d',
    'nan1_s', 'nan2_d', 'nan2_s', 'nan3_d', 'nan3_s', 'op_d', 'op_s', 'pair_d', 'pair_s', 'recpe_d', 'recpe_s',
    'recpx_d', 'recpx_s', 'redo_d', 'redo_s', 'rsqrte_d', 'rsqrte_s', 'sfix_d', 'sfix_s', 'simd_d2h', 'simd_d2s',
    'simd_d2s_odd', 'simd_d2s_slow', 'simd_dd2h', 'simd_directed', 'simd_h2d', 'simd_h2dbits', 'simd_h2s',
    'simd_s2d', 'simd_s2h', 'sl_across', 'sl_addlp', 'sl_gen', 'sl_ldm', 'sl_ldr', 'sl_lds', 'sl_pmull64', 'sl_stm',
    'sl_sts', 'slow_d', 'slow_s', 'sv_aes', 'sv_fcvtl', 'sv_fcvtn', 'sv_fred_s', 'sv_sha1hash', 'sv_sha256hash',
    'sv_sha_misc', 'sv_tbl', 'toint_d', 'toint_s', 'vcmp_d', 'vcmp_s', 'vfix_d', 'vfix_s', 'vfrint_d', 'vfrint_s',
    'vfromint_d', 'vfromint_s', 'vfz_d', 'vfz_s', 'vop_d', 'vop_s', 'vrecpe_d', 'vrecpe_s', 'vrsqrte_d', 'vrsqrte_s',
    'vslow_d', 'vslow_s', 'vtoint_d', 'vtoint_s',
]
CALL = re.compile(r'\b(' + '|'.join(HELPERS) + r')\(c\b')
USES = re.compile(r'\bFPCR\b|\bSV_FOP_[SD]\(')   # simd.h's SV_FOP_S/D pass FPCR themselves
RELOAD = '\x00F'
MSR = 'rt_fpcr_sync(c);'


def finish(lines):
    """(function lines with the helpers on FPCR and the reload markers resolved, whether the function uses FPCR)."""
    lines = [CALL.sub(lambda m: f'{m.group(1)}(FPCR', ln) for ln in lines]
    used = any(USES.search(ln) for ln in lines)
    reload = ' FPCR = c->fpcr;' if used else ''
    return [ln.replace(RELOAD, reload) for ln in lines], used


DECL = '    uint64_t FPCR = c->fpcr;'
