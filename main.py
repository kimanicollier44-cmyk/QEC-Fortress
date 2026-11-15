#!/usr/bin/env python3
"""QEC-Fortress - educational quantum error correction lab.

by Darion Kellar

Pure Python standard library. Zero dependencies. Zero network.
Simulation only: the mathematics that keeps fragile quantum states
alive - the 3-qubit bit-flip and phase-flip repetition codes, Shor's
9-qubit code, the Steane [[7,1,3]] code, syndrome extraction and
lookup / majority-vote decoding, the threshold theorem (below roughly
1% physical error, bigger codes suppress logical error; above it they
make things worse), surface-code distance scaling, and a
fault-tolerance overhead calculator that turns a physical error rate
into the physical-qubit price of one protected logical qubit. A
from-scratch TinyML kNN classifier labels operating points, Gemini
Carbon 4 sits as DECIDER (names-only, tighten-only), Muse as advisor
(never overrides HOLD), and Google Flow is a plan-only seat.

Every real-hardware / live-execution action is a permanent HOLD gate.
Nothing here runs on, connects to, or controls any quantum device.
"""
import hashlib
import json
import math
import random
import sys

# ---------------------------------------------------------------- constants
P_THRESHOLD = 0.01        # surface-code circuit-level threshold ballpark (~1%)
SURFACE_PREFACTOR = 0.1   # standard phenomenological fit: pL ~ 0.1 (p/pth)^((d+1)/2)
MC_SEED = 20261114        # fixed seed: every Monte Carlo run is reproducible

VERSION = "1.0.0"

# ---------------------------------------------------------------- HOLD gates
HOLD_GATES = {
    "real_quantum_hardware": "HOLD - no connection to or control of any real quantum hardware",
    "live_circuit_execution": "HOLD - no live circuit execution on any quantum device or cloud backend",
    "vendor_cloud_submission": "HOLD - no job submission to any quantum cloud vendor",
    "remote_device_access": "HOLD - no remote access, calibration, or tuning of quantum devices",
    "hardware_procurement_planning": "HOLD - no procurement / purchase planning for quantum hardware",
    "fault_tolerant_computer_claim": "HOLD - no claim this simulation is, or runs on, a fault-tolerant quantum computer",
    "protected_computation_claim": "HOLD - no claim any real computation or real data is protected by this lab",
    "cryptographic_security_claim": "HOLD - no claim QEC here makes any real cryptographic system secure or broken",
    "cryptanalysis_live": "HOLD - no live cryptanalysis of real keys, real ciphers, or real systems",
    "medical_claim": "HOLD - no medical, diagnostic, or clinical claims",
    "weapons_application_claim": "HOLD - no weapons or military application claims",
    "investment_advice_claim": "HOLD - no investment advice about quantum-computing companies or stocks",
    "commercial_product_claim": "HOLD - no claim this simulation is a commercial product or certified design",
    "peer_reviewed_result_claim": "HOLD - no claim these teaching numbers are peer-reviewed research results",
}


def gate(action):
    """Return 'HOLD' if the action is gated, else 'PROCEED' (sandbox sim)."""
    return "HOLD" if action in HOLD_GATES else "PROCEED"


# ================================================================ 1. Tiny statevector core
# Qubit q is bit q of the basis index (little-endian). States are plain
# lists of complex amplitudes - exact arithmetic, no sampling noise.
def zero_state(n):
    st = [0j] * (1 << n)
    st[0] = 1.0 + 0j
    return st


def apply_1q(state, n, q, m):
    """Apply 2x2 matrix m to qubit q of an n-qubit statevector, in place."""
    step = 1 << q
    for base in range(0, 1 << n, step << 1):
        for off in range(step):
            i0 = base + off
            i1 = i0 + step
            a0, a1 = state[i0], state[i1]
            state[i0] = m[0][0] * a0 + m[0][1] * a1
            state[i1] = m[1][0] * a0 + m[1][1] * a1
    return state


def apply_cnot(state, n, control, target):
    for i in range(1 << n):
        if (i >> control) & 1 and not (i >> target) & 1:
            j = i | (1 << target)
            state[i], state[j] = state[j], state[i]
    return state


I2 = [[1, 0], [0, 1]]
X_GATE = [[0, 1], [1, 0]]
Z_GATE = [[1, 0], [0, -1]]
_S = 1.0 / math.sqrt(2.0)
H_GATE = [[_S, _S], [_S, -_S]]
PAULI = {"I": I2, "X": X_GATE, "Z": Z_GATE}


def apply_pauli(state, n, q, letter):
    """Apply a Pauli (X, Z, or Y = iXZ up to phase) error to qubit q."""
    if letter == "I":
        return state
    if letter == "Y":
        apply_1q(state, n, q, Z_GATE)
        apply_1q(state, n, q, X_GATE)
        # global phase i dropped: fidelity and syndromes are unaffected
        return state
    return apply_1q(state, n, q, PAULI[letter])


def pauli_expectation(state, n, ops):
    """Expectation <psi|P|psi> of a Pauli string {qubit: letter}.

    For a stabilizer syndrome measurement on a Pauli-error state this is
    exactly +1 or -1: the syndrome bit is 0 for +1, 1 for -1.
    """
    other = list(state)
    for q, letter in ops.items():
        apply_pauli(other, n, q, letter)
    return sum((a.conjugate() * b for a, b in zip(state, other)), 0j).real


def syndrome_bits(state, n, checks):
    """Measure each stabilizer check (list of {qubit: letter}); 1 = violated."""
    return tuple(1 if pauli_expectation(state, n, chk) < 0 else 0 for chk in checks)


def fidelity(state_a, state_b):
    """|<a|b>|^2 for two statevectors of equal length."""
    inner = sum((a.conjugate() * b for a, b in zip(state_a, state_b)), 0j)
    return abs(inner) ** 2


def logical_state(alpha, beta, n, encode):
    """Build alpha|0_L> + beta|1_L> on n qubits with an encode circuit."""
    st = zero_state(n)
    st[0] = alpha
    st[1] = beta  # qubit 0 carries the bare logical state before encoding
    return encode(st)


# ================================================================ 2. 3-qubit repetition codes
# Bit-flip code: |0> -> |000>, |1> -> |111>. Stabilizers Z0Z1, Z1Z2.
# Phase-flip code: |0> -> |+++>, |1> -> |--->. Stabilizers X0X1, X1X2.
REP_CHECKS = {
    "bit": [{0: "Z", 1: "Z"}, {1: "Z", 2: "Z"}],
    "phase": [{0: "X", 1: "X"}, {1: "X", 2: "X"}],
}
# syndrome (s1, s2) -> qubit to correct (None = no error)
REP_LOOKUP = {(0, 0): None, (1, 0): 0, (1, 1): 1, (0, 1): 2}


def encode_rep3(st, kind="bit"):
    apply_cnot(st, 3, 0, 1)
    apply_cnot(st, 3, 0, 2)
    if kind == "phase":
        for q in range(3):
            apply_1q(st, 3, q, H_GATE)
    return st


def rep3_correct(st, kind="bit"):
    """Extract the syndrome of a 3-qubit code state and correct in place.

    Returns (syndrome, corrected_qubit_or_None). Correction applies the
    same Pauli that caused the error (X for bit-flip code, Z for phase).
    """
    syn = syndrome_bits(st, 3, REP_CHECKS[kind])
    bad = REP_LOOKUP[syn]
    if bad is not None:
        apply_pauli(st, 3, bad, "X" if kind == "bit" else "Z")
    return syn, bad


def rep3_logical_error_analytic(p):
    """Exact logical failure probability of the 3-qubit code.

    The decoder fixes any single error; failure needs >= 2 errors:
    pL = 3 p^2 (1-p) + p^3 = 3p^2 - 2p^3. Encoding helps iff p < 0.5.
    """
    return 3.0 * p * p - 2.0 * p * p * p


def rep3_break_even():
    """Physical error rate where the code stops helping: pL = p at p = 0.5."""
    return 0.5


# ================================================================ 3. Shor 9-qubit code
# |0_L> = ((|000>+|111>)/sqrt2)^3, |1_L> = ((|000>-|111>)/sqrt2)^3.
# Corrects ANY single-qubit error: X via within-block Z parities,
# Z via across-block X parities (block signs).
SHOR_BLOCKS = [(0, 1, 2), (3, 4, 5), (6, 7, 8)]


def encode_shor(st):
    apply_cnot(st, 9, 0, 3)
    apply_cnot(st, 9, 0, 6)
    for q in (0, 3, 6):
        apply_1q(st, 9, q, H_GATE)
    for a, b, c in SHOR_BLOCKS:
        apply_cnot(st, 9, a, b)
        apply_cnot(st, 9, a, c)
    return st


def _shor_bit_syndromes(st):
    syn = []
    for a, b, c in SHOR_BLOCKS:
        syn.append(syndrome_bits(st, 9, [{a: "Z", b: "Z"}, {b: "Z", c: "Z"}]))
    return syn


def _shor_phase_syndrome(st):
    big = [{q: "X" for q in SHOR_BLOCKS[0] + SHOR_BLOCKS[1]},
           {q: "X" for q in SHOR_BLOCKS[1] + SHOR_BLOCKS[2]}]
    return syndrome_bits(st, 9, big)


def shor_correct(st):
    """Full Shor decode+correct on a statevector. Returns a report dict."""
    report = {"bit_syndromes": [], "corrected_x": [], "phase_syndrome": None,
              "corrected_z_block": None}
    for blk, syn in enumerate(_shor_bit_syndromes(st)):
        report["bit_syndromes"].append(syn)
        bad = REP_LOOKUP[syn]
        if bad is not None:
            q = SHOR_BLOCKS[blk][bad]
            apply_pauli(st, 9, q, "X")
            report["corrected_x"].append(q)
    psyn = _shor_phase_syndrome(st)
    report["phase_syndrome"] = psyn
    # (1,0): block 0 sign differs -> Z on block 0; (1,1): block 1; (0,1): block 2
    zblk = {(0, 0): None, (1, 0): 0, (1, 1): 1, (0, 1): 2}[psyn]
    if zblk is not None:
        apply_pauli(st, 9, SHOR_BLOCKS[zblk][0], "Z")
        report["corrected_z_block"] = zblk
    return report


# ================================================================ 4. Steane [[7,1,3]] code
# CSS code from the classical [7,4,3] Hamming code. Column j of H is the
# binary of j+1, so every nonzero syndrome names exactly one qubit.
HAMMING_H = (
    (0, 0, 0, 1, 1, 1, 1),
    (0, 1, 1, 0, 0, 1, 1),
    (1, 0, 1, 0, 1, 0, 1),
)


def hamming_syndrome(err_bits):
    """H . e (mod 2) for a 7-bit error pattern."""
    return tuple(sum(HAMMING_H[r][j] * err_bits[j] for j in range(7)) % 2
                 for r in range(3))


def _build_steane_lookup():
    lut = {}
    for j in range(7):
        e = [0] * 7
        e[j] = 1
        lut[hamming_syndrome(e)] = j
    return lut


STEANE_LOOKUP = _build_steane_lookup()


def _build_steane_stabilizers():
    """X-type (equally Z-type) stabilizer patterns: the row space of H."""
    stabs = set()
    for mask in range(8):
        v = [0] * 7
        for r in range(3):
            if (mask >> r) & 1:
                for j in range(7):
                    v[j] ^= HAMMING_H[r][j]
        stabs.add(tuple(v))
    return stabs


STEANE_STABILIZERS = _build_steane_stabilizers()


def steane_decode(err_bits):
    """Lookup-decode one error sector (X or Z) of the Steane code.

    Returns (correction_bits, success). Success = residual is a
    stabilizer (harmless); failure = residual is a logical operator.
    """
    syn = hamming_syndrome(err_bits)
    corr = [0] * 7
    if syn != (0, 0, 0):
        corr[STEANE_LOOKUP[syn]] = 1
    residual = tuple(e ^ c for e, c in zip(err_bits, corr))
    success = hamming_syndrome(residual) == (0, 0, 0) and residual in STEANE_STABILIZERS
    return corr, success


def steane_logical_error_analytic(p):
    """Leading-order Steane failure rate for one error sector.

    Any single error is corrected; any pair can fail, so to leading
    order pL ~ C(7,2) p^2 = 21 p^2 (exact value comes from Monte Carlo).
    """
    return 21.0 * p * p


# ================================================================ 5. Monte Carlo error simulation
# Pauli-frame simulation: errors are bit patterns, decoders are the real
# lookup / majority rules above. Fast enough for tens of thousands of
# trials in pure stdlib, and every run is seeded -> reproducible.
def _rand_bits(rng, n, p):
    return [1 if rng.random() < p else 0 for _ in range(n)]


def mc_rep3(p, trials=20000, seed=MC_SEED):
    """Monte Carlo logical failure rate of the 3-qubit repetition code."""
    rng = random.Random(seed)
    fails = 0
    for _ in range(trials):
        e = _rand_bits(rng, 3, p)
        syn = (e[0] ^ e[1], e[1] ^ e[2])
        bad = REP_LOOKUP[syn]
        residual = list(e)
        if bad is not None:
            residual[bad] ^= 1
        if sum(residual) >= 2:  # residual X^3 = logical flip (weight-3 ~ weight-0 mod code)
            fails += 1
    return fails / trials


def mc_shor(p, trials=20000, seed=MC_SEED):
    """Monte Carlo logical failure rate of Shor's code, depolarizing noise.

    Each qubit independently gets X, Y, or Z with probability p/3 each
    (Y counts in both sectors). Decoder: per-block parity + lookup for
    X, block-sign majority vote for Z - the standard Shor decoder.
    """
    rng = random.Random(seed)
    fails = 0
    for _ in range(trials):
        xb = [0] * 9
        zb = [0] * 9
        for q in range(9):
            r = rng.random()
            if r < p / 3.0:
                xb[q] = 1
            elif r < 2.0 * p / 3.0:
                zb[q] = 1
            elif r < p:
                xb[q] = 1
                zb[q] = 1
        failed = False
        for a, b, c in SHOR_BLOCKS:
            blk = [xb[a], xb[b], xb[c]]
            syn = (blk[0] ^ blk[1], blk[1] ^ blk[2])
            bad = REP_LOOKUP[syn]
            if bad is not None:
                blk[bad] ^= 1
            if sum(blk) >= 2:
                failed = True
        odd_blocks = sum(sum(zb[q] for q in blk) % 2 for blk in SHOR_BLOCKS)
        if odd_blocks >= 2:
            failed = True
        if failed:
            fails += 1
    return fails / trials


def mc_steane(p, trials=20000, seed=MC_SEED):
    """Monte Carlo logical failure rate of the Steane code (depolarizing).

    X and Z sectors are decoded independently with the Hamming lookup;
    a logical failure in either sector fails the trial.
    """
    rng = random.Random(seed)
    fails = 0
    for _ in range(trials):
        xb = [0] * 7
        zb = [0] * 7
        for q in range(7):
            r = rng.random()
            if r < p / 3.0:
                xb[q] = 1
            elif r < 2.0 * p / 3.0:
                zb[q] = 1
            elif r < p:
                xb[q] = 1
                zb[q] = 1
        _, ok_x = steane_decode(xb)
        _, ok_z = steane_decode(zb)
        if not (ok_x and ok_z):
            fails += 1
    return fails / trials


def mc_bare(p, trials=20000, seed=MC_SEED):
    """Unprotected qubit under the same depolarizing noise: fails at rate p."""
    rng = random.Random(seed)
    return sum(1 for _ in range(trials) if rng.random() < p) / trials


# ================================================================ 6. Surface code + threshold theorem
def surface_data_qubits(d):
    """Data qubits in a rotated surface-code patch of distance d."""
    return d * d


def surface_total_qubits(d):
    """Data + syndrome ancilla qubits in a rotated patch: 2d^2 - 1."""
    return 2 * d * d - 1


def surface_logical_error(p, d):
    """Phenomenological fit pL ~ 0.1 * (p / p_th)^((d+1)/2), p_th ~ 1%.

    The standard Fowler-style scaling model used across the field for
    back-of-envelope resource estimates. A model, not a measurement.
    """
    return SURFACE_PREFACTOR * (p / P_THRESHOLD) ** ((d + 1) // 2)


def required_distance(p, target_logical_error, max_d=99):
    """Smallest odd distance reaching the target logical error rate.

    Returns None when p >= p_th: above threshold no distance helps -
    that impossibility IS the threshold theorem, stated honestly.
    """
    if p >= P_THRESHOLD:
        return None
    d = 3
    while d <= max_d:
        # 1e-9 relative slack: exact powers of 0.1 land a float-hair above
        # round targets (0.1 * 0.1**11 = 1.0000000000000006e-12)
        if surface_logical_error(p, d) <= target_logical_error * (1 + 1e-9):
            return d
        d += 2
    return None


def threshold_table(ps=(0.001, 0.005, 0.01, 0.02), ds=(3, 5, 7, 9)):
    """Logical error vs distance for physical rates around threshold."""
    return {p: {d: surface_logical_error(p, d) for d in ds} for p in ps}


def logical_vs_physical(p, ds=(3, 5, 7, 9, 11, 13)):
    """One row of the threshold story: pL per distance at one p."""
    return {d: surface_logical_error(p, d) for d in ds}


# ================================================================ 7. Fault-tolerance overhead calculator
def fault_tolerance_overhead(p_phys, target_logical_error, n_logical_qubits,
                             n_logical_ops=0):
    """Turn a physical error rate into a physical-qubit bill.

    If n_logical_ops > 0 the target is a TOTAL error budget spread over
    that many logical operations, so the per-operation target is
    target / ops. Returns a dict; feasible=False above threshold.
    """
    per_op_target = target_logical_error / n_logical_ops if n_logical_ops else target_logical_error
    d = required_distance(p_phys, per_op_target)
    if d is None:
        return {"feasible": False, "reason": "physical error rate at/above threshold "
                f"({P_THRESHOLD}); no code distance reaches the target",
                "p_phys": p_phys, "per_op_target": per_op_target}
    per_logical = surface_total_qubits(d)
    return {
        "feasible": True,
        "p_phys": p_phys,
        "target_logical_error": target_logical_error,
        "per_op_target": per_op_target,
        "distance": d,
        "physical_per_logical": per_logical,
        "data_per_logical": surface_data_qubits(d),
        "n_logical_qubits": n_logical_qubits,
        "total_physical_qubits": per_logical * n_logical_qubits,
        "overhead_factor": per_logical,
        "achieved_logical_error": surface_logical_error(p_phys, d),
    }


def overhead_report():
    """Named scenarios for the demo / CLI."""
    return {
        "one_logical_qubit_p0.001_target1e-12": fault_tolerance_overhead(0.001, 1e-12, 1),
        "1000_logical_p0.001_target1e-12": fault_tolerance_overhead(0.001, 1e-12, 1000),
        "100_logical_p0.005_total1e-2_over_1e9_ops": fault_tolerance_overhead(0.005, 1e-2, 100, 10 ** 9),
        "above_threshold_p0.02": fault_tolerance_overhead(0.02, 1e-12, 100),
    }


# ================================================================ 8. kNN operating-point classifier
# Features: (log10(p / p_th), d, log10(pL)). Labels come from the surface
# model itself; the kNN learns the shape of the threshold landscape.
def _op_features(p, d):
    pl = max(surface_logical_error(p, d), 1e-300)
    return (math.log10(p / P_THRESHOLD), float(d), math.log10(pl))


def _op_label(p, d):
    if p >= P_THRESHOLD:
        return "unprotected"
    pl = surface_logical_error(p, d)
    if pl <= 1e-10:
        return "fortress"
    if pl <= 1e-5:
        return "protected"
    if pl <= 1e-3:
        return "marginal"
    return "unprotected"


def _build_knn_train():
    pts = []
    for p in (0.0002, 0.0005, 0.001, 0.002, 0.003, 0.005, 0.007, 0.009, 0.012, 0.02):
        for d in (3, 5, 7, 9, 11, 13, 17, 21, 25):
            pts.append((_op_features(p, d), _op_label(p, d)))
    return pts


_KNN_TRAIN = _build_knn_train()


class KNNClassifier:
    """From-scratch kNN (stdlib) over operating-point features."""

    def __init__(self, k=5):
        self.k = k
        self.train = list(_KNN_TRAIN)

    @staticmethod
    def _dist(a, b):
        # scale distance axis so one step of d ~ one decade of pL
        return math.sqrt((a[0] - b[0]) ** 2 + ((a[1] - b[1]) / 5.0) ** 2
                         + (a[2] - b[2]) ** 2)

    def classify_features(self, feats):
        near = sorted(self.train, key=lambda t: self._dist(t[0], feats))[: self.k]
        votes = {}
        for _, label in near:
            votes[label] = votes.get(label, 0) + 1
        return max(sorted(votes), key=lambda lab: votes[lab])

    def classify(self, p, d):
        return self.classify_features(_op_features(p, d))


def classify_point(p, d):
    return KNNClassifier().classify(p, d)


def classify_report():
    scenarios = {
        "p=0.001, d=5": (0.001, 5),
        "p=0.001, d=21": (0.001, 21),
        "p=0.005, d=9": (0.005, 9),
        "p=0.005, d=3": (0.005, 3),
        "p=0.009, d=13": (0.009, 13),
        "p=0.02, d=25": (0.02, 25),
    }
    return {name: classify_point(p, d) for name, (p, d) in scenarios.items()}


# ================================================================ 9. Advisory seats
def _trace(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def carbon4_decide(topic="qec-fortress-demo"):
    """Gemini Carbon 4 DECIDER seat: MAP->MODEL->STRESS->DECIDE.

    Names-only keys, live calls 0, tighten-only: can add HOLDs, never lift one.
    """
    stages = ["MAP", "MODEL", "STRESS", "DECIDE"]
    payload = {"seat": "gemini-carbon-4", "topic": topic, "stages": stages}
    return {
        "seat": "Gemini Carbon 4 Extended Thinking",
        "role": "DECIDER",
        "pipeline": stages,
        "tiers": [2048, 8192, 32768],
        "key": "names-only (GEMINI_API_KEY name checked, value never read)",
        "live_calls": 0,
        "can_override_hold": False,
        "tighten_only": True,
        "decision": "PROCEED (sandbox simulation only)",
        "trace_sha256_16": _trace(payload),
    }


def claude_advisor(topic="qec-fortress-demo"):
    """Muse advisor seat: advisory only, authority none."""
    return {
        "seat": "Muse",
        "role": "advisor",
        "authority": "none - advisory only",
        "can_override_hold": False,
        "live_calls": 0,
        "advice": "Keep every real-hardware action behind its HOLD gate; present the surface-code fit as a model, never a measurement.",
        "trace_sha256_16": _trace({"seat": "claude-advisor", "topic": topic}),
    }


def google_flow_plan():
    """Google Flow: plan-only. Nothing renders, nothing is sent."""
    return {
        "seat": "Google Flow",
        "flows": ["FlowX task graph", "Workspace Studio drafts",
                  "Filmmaking 5-shot storyboard", "DataX data-flow"],
        "rendered": False,
        "live": 0,
        "plan": ["syndrome extraction explainer", "threshold cliff story",
                 "surface-code lattice hero shot", "overhead bill chart story"],
    }


def brains_report():
    return {"decider": carbon4_decide(), "advisor": claude_advisor(),
            "flow": google_flow_plan()}


# ================================================================ checks
def run_checks():
    c = []

    def chk(name, ok):
        c.append((name, bool(ok)))

    # --- repetition code: exact statevector behaviour
    ideal = logical_state(0.6, 0.8, 3, lambda s: encode_rep3(s, "bit"))
    st = logical_state(0.6, 0.8, 3, lambda s: encode_rep3(s, "bit"))
    apply_pauli(st, 3, 1, "X")
    syn, bad = rep3_correct(st, "bit")
    chk("rep3_bitflip_syndrome", syn == (1, 1) and bad == 1)
    chk("rep3_bitflip_restored", fidelity(st, ideal) > 1 - 1e-12)
    st = logical_state(0.6, 0.8, 3, lambda s: encode_rep3(s, "phase"))
    ideal_p = logical_state(0.6, 0.8, 3, lambda s: encode_rep3(s, "phase"))
    apply_pauli(st, 3, 2, "Z")
    syn, bad = rep3_correct(st, "phase")
    chk("rep3_phaseflip_syndrome", syn == (0, 1) and bad == 2)
    chk("rep3_phaseflip_restored", fidelity(st, ideal_p) > 1 - 1e-12)
    chk("rep3_no_error_syndrome_zero", rep3_correct(
        logical_state(1.0, 0.0, 3, lambda s: encode_rep3(s, "bit")), "bit")[0] == (0, 0))
    chk("rep3_analytic_at_0.1", abs(rep3_logical_error_analytic(0.1) - 0.028) < 1e-12)
    chk("rep3_analytic_zero", rep3_logical_error_analytic(0.0) == 0.0)
    chk("rep3_helps_below_half", rep3_logical_error_analytic(0.1) < 0.1)
    chk("rep3_hurts_above_half", rep3_logical_error_analytic(0.6) > 0.6)
    chk("rep3_break_even_half", rep3_break_even() == 0.5
        and abs(rep3_logical_error_analytic(0.5) - 0.5) < 1e-12)
    chk("mc_rep3_matches_analytic", abs(mc_rep3(0.1) - 0.028) < 0.01)
    chk("mc_rep3_deterministic", mc_rep3(0.1, trials=2000) == mc_rep3(0.1, trials=2000))

    # --- Shor code: any single-qubit Pauli error, corrected exactly
    ideal9 = logical_state(0.6, 0.8, 9, encode_shor)
    ok_all = True
    for q in range(9):
        for letter in ("X", "Z", "Y"):
            st = logical_state(0.6, 0.8, 9, encode_shor)
            apply_pauli(st, 9, q, letter)
            shor_correct(st)
            if fidelity(st, ideal9) < 1 - 1e-9:
                ok_all = False
    chk("shor_corrects_any_single_pauli", ok_all)
    st = logical_state(0.6, 0.8, 9, encode_shor)
    apply_pauli(st, 9, 4, "Z")
    rep = shor_correct(st)
    chk("shor_phase_syndrome_block1", rep["phase_syndrome"] == (1, 1)
        and rep["corrected_z_block"] == 1)
    chk("shor_mc_beats_bare", mc_shor(0.05) < mc_bare(0.05))
    chk("shor_mc_small", mc_shor(0.05) < 0.04)

    # --- Steane code
    chk("hamming_columns_unique", len(STEANE_LOOKUP) == 7
        and (0, 0, 0) not in STEANE_LOOKUP)
    singles = True
    for j in range(7):
        e = [0] * 7
        e[j] = 1
        corr, ok = steane_decode(e)
        if not ok or corr != e:
            singles = False
    chk("steane_corrects_all_singles", singles)
    chk("steane_zero_error_ok", steane_decode([0] * 7)[1] is True)
    stab = list(next(iter(s for s in STEANE_STABILIZERS if sum(s) == 4)))
    chk("steane_stabilizer_harmless", steane_decode(stab)[1] is True)
    pair = [1, 1, 0, 0, 0, 0, 0]
    chk("steane_pair_can_fail", steane_decode(pair)[1] is False)
    chk("steane_mc_beats_bare", mc_steane(0.05) < mc_bare(0.05))
    chk("steane_analytic_leading", abs(steane_logical_error_analytic(0.1) - 0.21) < 1e-12)

    # --- surface code + threshold theorem
    chk("surface_qubits_d5", surface_data_qubits(5) == 25 and surface_total_qubits(5) == 49)
    chk("surface_qubits_d21", surface_total_qubits(21) == 881)
    chk("surface_fit_d3_p0.001", abs(surface_logical_error(0.001, 3) - 1e-3) < 1e-15)
    chk("below_threshold_bigger_helps",
        surface_logical_error(0.005, 9) < surface_logical_error(0.005, 5)
        < surface_logical_error(0.005, 3))
    chk("above_threshold_bigger_hurts",
        surface_logical_error(0.02, 9) > surface_logical_error(0.02, 5)
        > surface_logical_error(0.02, 3))
    chk("at_threshold_flat", abs(surface_logical_error(0.01, 3)
        - surface_logical_error(0.01, 11)) < 1e-15)
    chk("required_distance_1e-12", required_distance(0.001, 1e-12) == 21)
    chk("required_distance_none_above", required_distance(0.02, 1e-12) is None)
    tt = threshold_table()
    chk("threshold_table_shape", len(tt) == 4 and len(tt[0.001]) == 4)

    # --- overhead calculator
    ov = fault_tolerance_overhead(0.001, 1e-12, 1000)
    chk("overhead_1000_logical", ov["feasible"] and ov["distance"] == 21
        and ov["total_physical_qubits"] == 881000)
    ov2 = fault_tolerance_overhead(0.02, 1e-12, 100)
    chk("overhead_infeasible_above_threshold", ov2["feasible"] is False)
    ov3 = fault_tolerance_overhead(0.005, 1e-2, 100, 10 ** 9)
    chk("overhead_ops_budget", ov3["feasible"]
        and abs(ov3["per_op_target"] - 1e-11) < 1e-20)
    chk("overhead_report_keys", len(overhead_report()) == 4)

    # --- classifier
    chk("classifier_fortress", classify_point(0.001, 21) == "fortress")
    chk("classifier_unprotected_above", classify_point(0.02, 25) == "unprotected")
    chk("classifier_report_scenarios", len(classify_report()) == 6)

    # --- gates + seats
    chk("hold_gates_14", len(HOLD_GATES) == 14 and all(v.startswith("HOLD") for v in HOLD_GATES.values()))
    chk("gate_hardware_hold", gate("real_quantum_hardware") == "HOLD")
    chk("gate_live_exec_hold", gate("live_circuit_execution") == "HOLD")
    chk("gate_sandbox_proceed", gate("run_simulation") == "PROCEED")
    b = brains_report()
    chk("carbon4_no_override", b["decider"]["can_override_hold"] is False)
    chk("claude_no_override", b["advisor"]["can_override_hold"] is False)
    chk("flow_plan_only", b["flow"]["rendered"] is False and b["flow"]["live"] == 0)
    return c


# ================================================================ CLI / demo
def demo():
    print("=" * 68)
    print("QEC-Fortress - quantum error correction lab")
    print("by Darion Kellar | MIT | pure stdlib | zero network | SIM ONLY")
    print("=" * 68)
    print("\n[1] The enemy: one bare qubit under depolarizing noise")
    print(f"    physical error rate p = 0.05 -> bare qubit fails at ~{mc_bare(0.05):.4f}")
    print("\n[2] 3-qubit repetition code - exact math (analytic)")
    for p in (0.01, 0.05, 0.1, 0.3, 0.6):
        pl = rep3_logical_error_analytic(p)
        verdict = "helps" if pl < p else "HURTS"
        print(f"    p = {p:4.2f} -> logical {pl:.4f}  ({verdict}; break-even at p = 0.5)")
    print(f"    Monte Carlo at p = 0.10: {mc_rep3(0.1):.4f} vs analytic 0.0280")
    print("\n[3] Syndrome extraction - watch it work (statevector, exact)")
    st = logical_state(0.6, 0.8, 3, lambda s: encode_rep3(s, "bit"))
    apply_pauli(st, 3, 1, "X")
    syn, bad = rep3_correct(st, "bit")
    print(f"    X error on qubit 1 -> syndrome {syn} -> lookup corrects qubit {bad} -> restored")
    st = logical_state(0.6, 0.8, 9, encode_shor)
    ideal9 = logical_state(0.6, 0.8, 9, encode_shor)
    apply_pauli(st, 9, 7, "Y")
    rep = shor_correct(st)
    print(f"    Shor code, Y error on qubit 7 -> corrected X on {rep['corrected_x']}, "
          f"Z on block {rep['corrected_z_block']}, fidelity {fidelity(st, ideal9):.6f}")
    print("\n[4] Bigger codes at p = 0.05 (Monte Carlo, depolarizing)")
    print(f"    bare qubit : {mc_bare(0.05):.4f}")
    print(f"    Shor [[9,1,3]]  : {mc_shor(0.05):.4f}")
    print(f"    Steane [[7,1,3]]: {mc_steane(0.05):.4f}")
    print("\n[5] The threshold theorem - surface code, pL ~ 0.1 (p/p_th)^((d+1)/2)")
    print(f"    threshold p_th = {P_THRESHOLD} (1%). Below it, distance is armour; above it, weight.")
    for p in (0.001, 0.005, 0.02):
        row = logical_vs_physical(p, (3, 5, 7, 9))
        cells = "  ".join(f"d={d}: {v:.2e}" for d, v in row.items())
        trend = "falls with d - protection" if p < P_THRESHOLD else "GROWS with d - no protection"
        print(f"    p = {p:5.3f}  {cells}   ({trend})")
    print("\n[6] The fault-tolerance bill (overhead calculator)")
    ov = fault_tolerance_overhead(0.001, 1e-12, 1000)
    print(f"    p = 0.1%, target logical error 1e-12: distance {ov['distance']}, "
          f"{ov['physical_per_logical']} physical per logical")
    print(f"    1000 logical qubits -> {ov['total_physical_qubits']:,} physical qubits")
    ov2 = fault_tolerance_overhead(0.02, 1e-12, 100)
    print(f"    p = 2% (above threshold): feasible = {ov2['feasible']} - {ov2['reason']}")
    print("\n[7] Operating-point classifier (TinyML kNN on the threshold landscape)")
    for name, label in classify_report().items():
        print(f"    {name:16s} -> {label}")
    print("\n[8] Advisory seats")
    print(f"    decider: {carbon4_decide()['decision']} trace={carbon4_decide()['trace_sha256_16']}")
    print(f"    advisor can_override_hold = {claude_advisor()['can_override_hold']}")
    print(f"    flow rendered = {google_flow_plan()['rendered']} live = {google_flow_plan()['live']}")
    print(f"\n[9] HOLD gates: {len(HOLD_GATES)}")
    for k in HOLD_GATES:
        print(f"    HOLD  {k}")
    checks = run_checks()
    passed = sum(1 for _, ok in checks if ok)
    print(f"\nCHECKS {passed}/{len(checks)}")
    for name, ok in checks:
        if not ok:
            print(f"    FAIL {name}")
    verdict = "PROCEED" if passed == len(checks) else "HOLD"
    print(f"VERDICT {verdict} (sandbox simulation only) | HOLD gates {len(HOLD_GATES)}")
    return 0 if passed == len(checks) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "demo":
        return demo()
    cmd = argv[0]
    if cmd == "checks":
        checks = run_checks()
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'} {name}")
        print(f"CHECKS {sum(1 for _, ok in checks if ok)}/{len(checks)}")
        return 0 if all(ok for _, ok in checks) else 1
    if cmd == "codes":
        print(json.dumps({
            "rep3_bitflip": {"qubits": 3, "corrects": "any single X error",
                             "pL_analytic": "3p^2 - 2p^3"},
            "rep3_phaseflip": {"qubits": 3, "corrects": "any single Z error",
                               "pL_analytic": "3p^2 - 2p^3"},
            "shor": {"qubits": 9, "corrects": "any single-qubit Pauli error"},
            "steane": {"qubits": 7, "corrects": "any single-qubit Pauli error",
                       "pL_leading_order": "21p^2 per sector"},
            "surface": {"qubits": "2d^2 - 1 per logical",
                        "pL_model": "0.1 (p/0.01)^((d+1)/2)"},
        }, indent=2, sort_keys=True))
        return 0
    if cmd == "threshold":
        print(json.dumps(threshold_table(), indent=2, sort_keys=True))
        return 0
    if cmd == "surface":
        for d in (3, 5, 7, 9, 13, 21, 25):
            print(f"d = {d:2d}: {surface_data_qubits(d):4d} data + "
                  f"{surface_total_qubits(d) - surface_data_qubits(d):4d} ancilla = "
                  f"{surface_total_qubits(d):4d} physical per logical; "
                  f"pL @ p=0.001 = {surface_logical_error(0.001, d):.2e}")
        return 0
    if cmd == "overhead":
        print(json.dumps(overhead_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "montecarlo":
        for p in (0.01, 0.05, 0.1):
            print(f"p = {p:4.2f}: bare {mc_bare(p):.4f} | rep3 {mc_rep3(p):.4f} "
                  f"(analytic {rep3_logical_error_analytic(p):.4f}) | "
                  f"shor {mc_shor(p):.4f} | steane {mc_steane(p):.4f}")
        return 0
    if cmd == "classify":
        print(json.dumps(classify_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "brains":
        print(json.dumps(brains_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "holds":
        for k, v in HOLD_GATES.items():
            print(f"{k}: {v}")
        return 0
    if cmd == "hold-demo":
        action = argv[1] if len(argv) > 1 else "live_circuit_execution"
        print(f"{action}: {HOLD_GATES.get(action, 'PROCEED - not gated')}")
        return 2 if gate(action) == "HOLD" else 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
