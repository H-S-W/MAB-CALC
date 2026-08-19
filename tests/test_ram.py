"""
Verifiering av ramanalysen mot slutna losningar.
"""

import sys, os
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ram import Frame, sadeltak      # noqa: E402


def test_fritt_upplagd_balk():
    """M_mitt = q*L^2/8"""
    q, L = 10.0, 6.0
    fr = Frame()
    a, b = fr.add_node(0, 0), fr.add_node(L, 0)
    e = fr.add_element(a, b, EA=1e6, EI=1e4)
    fr.set_udl(e, -q)
    fr.add_support(a, ux=True, uy=True)
    fr.add_support(b, uy=True)
    fr.solve()
    _, _, V, M = fr.internal(e, npts=101)
    assert M.max() == pytest.approx(q*L**2/8, rel=1e-9)
    assert M[0] == pytest.approx(0.0, abs=1e-9)
    assert M[-1] == pytest.approx(0.0, abs=1e-9)
    assert V[0] == pytest.approx(q*L/2, rel=1e-9)


def test_inspand_balk():
    """M_stod = q*L^2/12, M_falt = q*L^2/24"""
    q, L = 10.0, 6.0
    fr = Frame()
    a, b = fr.add_node(0, 0), fr.add_node(L, 0)
    e = fr.add_element(a, b, EA=1e6, EI=1e4)
    fr.set_udl(e, -q)
    fr.add_support(a, ux=True, uy=True, rz=True)
    fr.add_support(b, ux=True, uy=True, rz=True)
    fr.solve()
    _, _, _, M = fr.internal(e, npts=101)
    assert M[0] == pytest.approx(-q*L**2/12, rel=1e-6)
    assert M.max() == pytest.approx(q*L**2/24, rel=1e-6)


def test_dragstang_normalkraft():
    fr = Frame()
    a, b = fr.add_node(0, 0), fr.add_node(4, 0)
    e = fr.add_element(a, b, EA=1e5, EI=1e3,
                       release_i=True, release_j=True)
    fr.add_support(a, ux=True, uy=True, rz=True)
    fr.add_support(b, uy=True, rz=True)
    fr.add_nodal_load(b, Fx=50.0)
    fr.solve()
    _, N, _, _ = fr.internal(e)
    assert N[0] == pytest.approx(50.0, rel=1e-9)


def test_treledsram_horisontalkraft():
    """H = q*L^2/(8*f) for symmetrisk treledsram med jamn last."""
    L, alpha, q = 10.0, 27.0, 4.0
    fr, ix = sadeltak(L, alpha, EA=42000, EI=760,
                      nock_styv=False, n_elem=12)
    for e in ix["vanster"] + ix["hoger"]:
        fr.set_udl_projected(e, -q)
    fr.solve()
    rise = L/2 * np.tan(np.radians(alpha))
    H = fr.reactions[3*ix["left"]]
    assert H == pytest.approx(q*L**2/(8*rise), rel=1e-6)


def test_treledsram_nockmoment_ar_noll():
    L, alpha, q = 10.0, 27.0, 4.0
    fr, ix = sadeltak(L, alpha, EA=42000, EI=760,
                      nock_styv=False, n_elem=12)
    for e in ix["vanster"] + ix["hoger"]:
        fr.set_udl_projected(e, -q)
    fr.solve()
    _, _, _, M = fr.internal(ix["vanster"][-1])
    assert M[-1] == pytest.approx(0.0, abs=1e-6)


def test_vertikal_jamvikt():
    L, alpha, q = 10.0, 27.0, 4.0
    fr, ix = sadeltak(L, alpha, EA=42000, EI=760,
                      nock_styv=True, n_elem=12)
    for e in ix["vanster"] + ix["hoger"]:
        fr.set_udl_projected(e, -q)
    fr.solve()
    Rv = fr.reactions[3*ix["left"]+1] + fr.reactions[3*ix["right"]+1]
    assert Rv == pytest.approx(q*L, rel=1e-6)


def test_dragband_tar_horisontalkraften():
    L, alpha, q = 10.0, 27.0, 4.0
    fr, ix = sadeltak(L, alpha, EA=42000, EI=760, nock_styv=True,
                      dragband=True, n_elem=12)
    for e in ix["vanster"] + ix["hoger"]:
        fr.set_udl_projected(e, -q)
    fr.solve()
    assert fr.reactions[3*ix["left"]] == pytest.approx(0.0, abs=1e-6)


def test_momentstyv_nock_ger_nockmoment():
    """Momentstyv nock flyttar moment till nocken och okar horisontalkraften."""
    L, alpha, q = 10.0, 27.0, 4.0
    res = {}
    for styv in (False, True):
        fr, ix = sadeltak(L, alpha, EA=42000, EI=760,
                          nock_styv=styv, n_elem=12)
        for e in ix["vanster"] + ix["hoger"]:
            fr.set_udl_projected(e, -q)
        fr.solve()
        _, _, _, M = fr.internal(ix["vanster"][-1])
        res[styv] = (abs(M[-1]), fr.reactions[3*ix["left"]])
    assert res[True][0] > 1.0
    assert res[False][0] < 1e-6
    assert res[True][1] > res[False][1]
