import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as qec


# --- statevector core -------------------------------------------------
def test_zero_state_normalized():
    st = qec.zero_state(3)
    assert len(st) == 8 and st[0] == 1.0 + 0j and sum(abs(a) ** 2 for a in st) == 1.0


def test_x_gate_flips():
    st = qec.zero_state(1)
    qec.apply_1q(st, 1, 0, qec.X_GATE)
    assert st[0] == 0j and st[1] == 1.0 + 0j


def test_hadamard_superposition():
    st = qec.zero_state(1)
    qec.apply_1q(st, 1, 0, qec.H_GATE)
    assert abs(abs(st[0]) ** 2 - 0.5) < 1e-12 and abs(abs(st[1]) ** 2 - 0.5) < 1e-12


def test_cnot_entangles():
    st = qec.zero_state(2)
    qec.apply_1q(st, 2, 0, qec.H_GATE)
    qec.apply_cnot(st, 2, 0, 1)
    probs = [abs(a) ** 2 for a in st]
    assert abs(probs[0] - 0.5) < 1e-12 and abs(probs[3] - 0.5) < 1e-12
    assert probs[1] == 0.0 and probs[2] == 0.0


def test_fidelity_identical_and_orthogonal():
    a = qec.zero_state(2)
    b = qec.zero_state(2)
    assert qec.fidelity(a, b) == 1.0
    qec.apply_1q(b, 2, 0, qec.X_GATE)
    assert qec.fidelity(a, b) == 0.0


def test_pauli_expectation_signs():
    st = qec.zero_state(1)
    assert qec.pauli_expectation(st, 1, {0: "Z"}) == 1.0
    qec.apply_1q(st, 1, 0, qec.X_GATE)
    assert qec.pauli_expectation(st, 1, {0: "Z"}) == -1.0


# --- 3-qubit repetition codes -----------------------------------------
def _rep(kind, err_q=None, err="X"):
    st = qec.logical_state(0.6, 0.8, 3, lambda s: qec.encode_rep3(s, kind))
    if err_q is not None:
        qec.apply_pauli(st, 3, err_q, err)
    return st


def test_rep3_encode_basis():
    st = qec.logical_state(1.0, 0.0, 3, lambda s: qec.encode_rep3(s, "bit"))
    assert st[0] == 1.0 + 0j and all(a == 0j for a in st[1:])
    st = qec.logical_state(0.0, 1.0, 3, lambda s: qec.encode_rep3(s, "bit"))
    assert st[7] == 1.0 + 0j


def test_rep3_bitflip_each_qubit():
    ideal = _rep("bit")
    for q in range(3):
        st = _rep("bit", q, "X")
        syn, bad = qec.rep3_correct(st, "bit")
        assert bad == q and qec.fidelity(st, ideal) > 1 - 1e-12


def test_rep3_phaseflip_each_qubit():
    ideal = _rep("phase")
    for q in range(3):
        st = _rep("phase", q, "Z")
        syn, bad = qec.rep3_correct(st, "phase")
        assert bad == q and qec.fidelity(st, ideal) > 1 - 1e-12


def test_rep3_syndrome_table():
    assert qec.REP_LOOKUP[(0, 0)] is None and qec.REP_LOOKUP[(1, 0)] == 0
    assert qec.REP_LOOKUP[(1, 1)] == 1 and qec.REP_LOOKUP[(0, 1)] == 2


def test_rep3_no_error_clean_syndrome():
    syn, bad = qec.rep3_correct(_rep("bit"), "bit")
    assert syn == (0, 0) and bad is None


def test_rep3_analytic_values():
    assert abs(qec.rep3_logical_error_analytic(0.1) - 0.028) < 1e-12
    assert qec.rep3_logical_error_analytic(0.0) == 0.0
    assert abs(qec.rep3_logical_error_analytic(0.5) - 0.5) < 1e-12


def test_rep3_helps_and_hurts():
    assert qec.rep3_logical_error_analytic(0.1) < 0.1
    assert qec.rep3_logical_error_analytic(0.6) > 0.6
    assert qec.rep3_break_even() == 0.5


def test_mc_rep3_matches_analytic():
    assert abs(qec.mc_rep3(0.1) - qec.rep3_logical_error_analytic(0.1)) < 0.01


def test_mc_deterministic():
    assert qec.mc_rep3(0.1, trials=1500) == qec.mc_rep3(0.1, trials=1500)
    assert qec.mc_shor(0.05, trials=1500) == qec.mc_shor(0.05, trials=1500)
    assert qec.mc_steane(0.05, trials=1500) == qec.mc_steane(0.05, trials=1500)


def test_mc_bare_rate():
    assert abs(qec.mc_bare(0.05) - 0.05) < 0.01


# --- Shor 9-qubit code --------------------------------------------------
def test_shor_encode_basis_states():
    st = qec.logical_state(1.0, 0.0, 9, qec.encode_shor)
    nz = [i for i, a in enumerate(st) if abs(a) > 1e-12]
    assert len(nz) == 8 and all(abs(st[i] - 1 / (2 * math.sqrt(2))) < 1e-12 for i in nz)


def test_shor_corrects_every_single_pauli():
    ideal = qec.logical_state(0.6, 0.8, 9, qec.encode_shor)
    for q in range(9):
        for letter in ("X", "Z", "Y"):
            st = qec.logical_state(0.6, 0.8, 9, qec.encode_shor)
            qec.apply_pauli(st, 9, q, letter)
            qec.shor_correct(st)
            assert qec.fidelity(st, ideal) > 1 - 1e-9, (q, letter)


def test_shor_phase_syndrome_block():
    st = qec.logical_state(0.6, 0.8, 9, qec.encode_shor)
    qec.apply_pauli(st, 9, 4, "Z")
    rep = qec.shor_correct(st)
    assert rep["phase_syndrome"] == (1, 1) and rep["corrected_z_block"] == 1


def test_shor_bit_syndrome_block():
    st = qec.logical_state(0.6, 0.8, 9, qec.encode_shor)
    qec.apply_pauli(st, 9, 8, "X")
    rep = qec.shor_correct(st)
    assert rep["corrected_x"] == [8]


def test_shor_mc_beats_bare():
    assert qec.mc_shor(0.05) < qec.mc_bare(0.05)
    assert qec.mc_shor(0.05) < 0.04


# --- Steane [[7,1,3]] code ----------------------------------------------
def test_hamming_syndrome_zero():
    assert qec.hamming_syndrome([0] * 7) == (0, 0, 0)


def test_steane_lookup_complete():
    assert len(qec.STEANE_LOOKUP) == 7 and (0, 0, 0) not in qec.STEANE_LOOKUP


def test_steane_corrects_all_single_errors():
    for j in range(7):
        e = [0] * 7
        e[j] = 1
        corr, ok = qec.steane_decode(e)
        assert ok and corr == e


def test_steane_zero_error():
    corr, ok = qec.steane_decode([0] * 7)
    assert ok and corr == [0] * 7


def test_steane_stabilizer_is_harmless():
    stab = next(s for s in qec.STEANE_STABILIZERS if sum(s) == 4)
    corr, ok = qec.steane_decode(list(stab))
    assert ok


def test_steane_pair_fails():
    corr, ok = qec.steane_decode([1, 1, 0, 0, 0, 0, 0])
    assert ok is False


def test_steane_analytic_leading_order():
    assert abs(qec.steane_logical_error_analytic(0.1) - 0.21) < 1e-12
    assert qec.steane_logical_error_analytic(0.0) == 0.0


def test_steane_mc_beats_bare():
    assert qec.mc_steane(0.05) < qec.mc_bare(0.05)


# --- surface code + threshold -------------------------------------------
def test_surface_qubit_counts():
    assert qec.surface_data_qubits(3) == 9 and qec.surface_total_qubits(3) == 17
    assert qec.surface_data_qubits(5) == 25 and qec.surface_total_qubits(5) == 49
    assert qec.surface_total_qubits(21) == 881


def test_surface_fit_values():
    assert abs(qec.surface_logical_error(0.001, 3) - 1e-3) < 1e-15
    assert abs(qec.surface_logical_error(0.001, 5) - 1e-4) < 1e-16
    assert abs(qec.surface_logical_error(0.01, 7) - 0.1) < 1e-15


def test_threshold_below_helps():
    vals = [qec.surface_logical_error(0.005, d) for d in (3, 5, 7, 9)]
    assert vals == sorted(vals, reverse=True)


def test_threshold_above_hurts():
    vals = [qec.surface_logical_error(0.02, d) for d in (3, 5, 7, 9)]
    assert vals == sorted(vals)


def test_threshold_at_is_flat():
    assert qec.surface_logical_error(0.01, 3) == qec.surface_logical_error(0.01, 13)


def test_required_distance():
    assert qec.required_distance(0.001, 1e-12) == 21
    assert qec.required_distance(0.001, 1e-6) == 9
    assert qec.required_distance(0.02, 1e-12) is None
    assert qec.required_distance(0.01, 1e-12) is None


def test_threshold_table_shape():
    tt = qec.threshold_table()
    assert len(tt) == 4 and all(len(v) == 4 for v in tt.values())


def test_logical_vs_physical_keys():
    row = qec.logical_vs_physical(0.001)
    assert set(row) == {3, 5, 7, 9, 11, 13}


# --- overhead calculator --------------------------------------------------
def test_overhead_headline():
    ov = qec.fault_tolerance_overhead(0.001, 1e-12, 1000)
    assert ov["feasible"] is True and ov["distance"] == 21
    assert ov["physical_per_logical"] == 881
    assert ov["total_physical_qubits"] == 881000


def test_overhead_single_logical():
    ov = qec.fault_tolerance_overhead(0.001, 1e-12, 1)
    assert ov["total_physical_qubits"] == 881 and ov["overhead_factor"] == 881


def test_overhead_infeasible_above_threshold():
    ov = qec.fault_tolerance_overhead(0.02, 1e-12, 100)
    assert ov["feasible"] is False and "threshold" in ov["reason"]


def test_overhead_ops_budget_spreads_target():
    ov = qec.fault_tolerance_overhead(0.005, 1e-2, 100, 10 ** 9)
    assert ov["feasible"] is True and abs(ov["per_op_target"] - 1e-11) < 1e-20


def test_overhead_achieved_meets_target():
    ov = qec.fault_tolerance_overhead(0.001, 1e-9, 10)
    assert ov["achieved_logical_error"] <= 1e-9 * 1.0000001


def test_overhead_report_has_four_scenarios():
    assert len(qec.overhead_report()) == 4


# --- kNN classifier -------------------------------------------------------
def test_classifier_fortress():
    assert qec.classify_point(0.001, 21) == "fortress"


def test_classifier_unprotected_above_threshold():
    assert qec.classify_point(0.02, 25) == "unprotected"


def test_classifier_labels_valid():
    valid = {"fortress", "protected", "marginal", "unprotected"}
    for p in (0.0005, 0.001, 0.004, 0.008, 0.015):
        for d in (3, 7, 13, 21):
            assert qec.classify_point(p, d) in valid


def test_classifier_report_scenarios():
    rep = qec.classify_report()
    assert len(rep) == 6 and rep["p=0.001, d=21"] == "fortress"


def test_knn_train_size():
    assert len(qec.KNNClassifier().train) == 90


# --- HOLD gates + advisory seats ------------------------------------------
def test_hold_gates_14():
    assert len(qec.HOLD_GATES) == 14
    assert all(v.startswith("HOLD") for v in qec.HOLD_GATES.values())


def test_gate_outcomes():
    assert qec.gate("real_quantum_hardware") == "HOLD"
    assert qec.gate("live_circuit_execution") == "HOLD"
    assert qec.gate("run_simulation") == "PROCEED"


def test_hold_demo_exit_code():
    assert qec.main(["hold-demo", "live_circuit_execution"]) == 2
    assert qec.main(["hold-demo", "run_simulation"]) == 0


def test_seats_never_override():
    b = qec.brains_report()
    assert b["decider"]["can_override_hold"] is False
    assert b["advisor"]["can_override_hold"] is False
    assert b["decider"]["live_calls"] == 0 and b["advisor"]["live_calls"] == 0


def test_flow_plan_only():
    f = qec.google_flow_plan()
    assert f["rendered"] is False and f["live"] == 0


def test_checks_all_pass():
    checks = qec.run_checks()
    assert all(ok for _, ok in checks) and len(checks) >= 40


def test_cli_checks_exit_zero():
    assert qec.main(["checks"]) == 0
