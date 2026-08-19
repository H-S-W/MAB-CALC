"""
Verifiering av ram.py:s utokningar: skjuvdeformation (Timoshenko),
rotationsfjader i elementanda och last vinkelratt elementet.

Precis som tests/test_ram.py galler bara slutna losningar som facit --
ingen kontroll mot programmets egna resultat.
"""

import numpy as np
import pytest

from ram import Frame, sadeltak

EA, EI, GA = 1e6, 929.0, 2499.0        # H300-varden dar det spelar roll
L, W = 6.0, -10.0                      # spann [m], last [kN/m] nedat


def fritt_upplagd(GA=None, n_elem=8, w=W, L=L, EI=EI):
    fr = Frame()
    a = fr.add_node(0, 0)
    noder = [a]
    for k in range(1, n_elem + 1):
        noder.append(fr.add_node(L * k / n_elem, 0))
    for i in range(n_elem):
        e = fr.add_element(noder[i], noder[i + 1], EA, EI, GA=GA)
        fr.set_udl(e, w)
    fr.add_support(noder[0], ux=True, uy=True)
    fr.add_support(noder[-1], uy=True)
    fr.solve()
    return fr, noder


# ---------------------------------------------------------------------------
# Timoshenko
# ---------------------------------------------------------------------------

def test_utan_GA_ar_allt_som_forut():
    """GA=None ska ge exakt Euler-Bernoulli: u = 5wL^4/384EI i mittspann."""
    fr, noder = fritt_upplagd(GA=None)
    u_mitt = fr.node_disp(noder[len(noder) // 2])[1]
    assert u_mitt == pytest.approx(5 * W * L**4 / (384 * EI), rel=1e-9)


def test_timoshenko_mittnedbojning_mot_sluten_losning():
    """
    Fritt upplagd balk med jamn last:

        u = 5wL^4/(384EI) + wL^2/(8GA)

    Skjuvtermen ar 10 % av bojtermen for en H300 pa 6 m -- inte en
    randkorrektion utan en storlek som maste med, sarskilt som den kryper
    med k_def 1,50-3,00 mot bojningens 0,60-0,80 (ETA tab. 18).
    """
    fr, noder = fritt_upplagd(GA=GA)
    u_mitt = fr.node_disp(noder[len(noder) // 2])[1]
    u_boj = 5 * W * L**4 / (384 * EI)
    u_skjuv = W * L**2 / (8 * GA)
    assert u_mitt == pytest.approx(u_boj + u_skjuv, rel=1e-9)
    assert abs(u_skjuv / u_boj) > 0.08


def test_skjuvdelen_ar_skillnaden_mellan_tva_korningar():
    """
    Sa har delas nedbojningen i boj- och skjuvdel i berakningskedjan:
    samma modell kors med och utan GA, differensen ar skjuvdelen. De tva
    delarna har OLIKA k_def enligt ETA tab. 18.
    """
    u_tot = fritt_upplagd(GA=GA)[0].node_disp(4)[1]
    u_boj = fritt_upplagd(GA=None)[0].node_disp(4)[1]
    assert u_tot - u_boj == pytest.approx(W * L**2 / (8 * GA), rel=1e-9)


def test_timoshenko_paverkar_inte_snittkrafterna_i_statiskt_bestamd_balk():
    """Fritt upplagd balk ar statiskt bestamd: M och V ar lastberoende."""
    fr_t, _ = fritt_upplagd(GA=GA)
    fr_e, _ = fritt_upplagd(GA=None)
    for e in range(4):
        _, _, V_t, M_t = fr_t.internal(e)
        _, _, V_e, M_e = fr_e.internal(e)
        assert np.allclose(M_t, M_e, atol=1e-9)
        assert np.allclose(V_t, V_e, atol=1e-9)


def test_timoshenko_omfordelar_i_statiskt_obestamd_balk():
    """
    I en tvasidigt inspand balk mjukar skjuvdeformationen inte upp
    nagonting relativt sett -- andmomenten wL^2/12 star kvar av
    symmetriskal. Det ar precis darfor fastinspanningskrafterna inte
    behover andras, och det testas har.
    """
    for ga in (None, GA):
        fr = Frame()
        a = fr.add_node(0, 0)
        b = fr.add_node(L / 2, 0)
        c = fr.add_node(L, 0)
        for i, j in ((a, b), (b, c)):
            e = fr.add_element(i, j, EA, EI, GA=ga)
            fr.set_udl(e, W)
        fr.add_support(a, ux=True, uy=True, rz=True)
        fr.add_support(c, ux=True, uy=True, rz=True)
        fr.solve()
        _, _, _, M = fr.internal(0)
        assert M[0] == pytest.approx(W * L**2 / 12, rel=1e-9)


# ---------------------------------------------------------------------------
# Rotationsfjader
# ---------------------------------------------------------------------------

def fjaderbalk(S):
    """Inspand i A, i B vertikalt stod + rotationsfjader S mot grunden."""
    fr = Frame()
    a = fr.add_node(0, 0)
    b = fr.add_node(L, 0)
    e = fr.add_element(a, b, EA, EI, spring_j=S)
    fr.set_udl(e, W)
    fr.add_support(a, ux=True, uy=True, rz=True)
    fr.add_support(b, uy=True, rz=True)      # fjadern sitter mot fast nod
    fr.solve()
    return fr


def test_fjadermomentet_mot_sluten_losning():
    """
    Balk inspand i A, rotationsfjader S mot fast grund i B, jamn last.
    Jamvikt i B med slope-deflection ger

        M_B = (wL^2/12) * S / (S + 4EI/L)

    Kontrolleras for fjadrar fran mycket vek till mycket styv.
    """
    for S in (10.0, 4 * EI / L, 619.0, 5000.0):
        fr = fjaderbalk(S)
        _, _, _, M = fr.internal(0)
        vantat = (W * L**2 / 12) * S / (S + 4 * EI / L)
        assert M[-1] == pytest.approx(vantat, rel=1e-9), f"S={S}"


def test_fjader_noll_ar_en_led():
    """S = 0 ska ge exakt samma sak som release: propped cantilever."""
    fr = fjaderbalk(0.0)
    _, _, _, M = fr.internal(0)
    assert M[-1] == pytest.approx(0.0, abs=1e-9)
    assert M[0] == pytest.approx(W * L**2 / 8, rel=1e-9)   # inspanningen


def test_mycket_styv_fjader_ar_en_styv_anslutning():
    fr = fjaderbalk(1e9)
    _, _, _, M = fr.internal(0)
    assert M[-1] == pytest.approx(W * L**2 / 12, rel=1e-5)


def test_fjadern_ar_monoton_i_styvheten():
    varden = [fjaderbalk(S).internal(0)[3][-1]
              for S in (0.0, 100.0, 500.0, 2000.0, 1e7)]
    belopp = [abs(v) for v in varden]
    assert belopp == sorted(belopp)


# ---------------------------------------------------------------------------
# Fjadern i sadeltaket
# ---------------------------------------------------------------------------

def sadeltak_nockmoment(**kwargs):
    fr, ix = sadeltak(10.0, 27.0, EA=65262, EI=EI, n_elem=8, **kwargs)
    for e in ix["vanster"] + ix["hoger"]:
        fr.set_udl_projected(e, -5.0)
    fr.solve()
    return fr.internal(ix["vanster"][-1])[3][-1]


def test_K_r_interpolerar_mellan_ledad_och_styv_nock():
    """
    K_r = 0 ska ge den ledade nockens moment (noll), K_r -> oandligt den
    styva nockens, och en andlig fjader nagot daremellan. Det ar hela
    poangen med rotationsfjadern: den styva nocken OVERSKATTAR nockmomentet
    och underskattar faltmoment och nedbojning.
    """
    M_styv = sadeltak_nockmoment(nock_styv=True)
    M_ledad = sadeltak_nockmoment(nock_styv=False)
    M_fjader = sadeltak_nockmoment(K_r=1400.0)

    assert M_ledad == pytest.approx(0.0, abs=1e-9)
    assert abs(M_styv) > 1.0
    assert 0.05 * abs(M_styv) < abs(M_fjader) < 0.95 * abs(M_styv)

    M_extrem_vek = sadeltak_nockmoment(K_r=1e-6)
    M_extrem_styv = sadeltak_nockmoment(K_r=1e9)
    assert M_extrem_vek == pytest.approx(M_ledad, abs=1e-6)
    assert M_extrem_styv == pytest.approx(M_styv, rel=1e-4)


def test_vekare_nock_ger_storre_faltmoment():
    """Momentet som lamnar nocken maste dyka upp i faltet."""
    def falt(**kw):
        fr, ix = sadeltak(10.0, 27.0, EA=65262, EI=EI, n_elem=8, **kw)
        for e in ix["vanster"] + ix["hoger"]:
            fr.set_udl_projected(e, -5.0)
        fr.solve()
        return max(fr.internal(e)[3].max() for e in ix["vanster"])

    assert falt(nock_styv=True) < falt(K_r=1400.0) < falt(nock_styv=False)


# ---------------------------------------------------------------------------
# Last vinkelratt elementet
# ---------------------------------------------------------------------------

def test_lokal_last_pa_horisontell_balk_ar_samma_som_global():
    """For ett horisontellt element ar lokal y = global y."""
    resultat = []
    for satt in ("global", "lokal"):
        fr = Frame()
        a = fr.add_node(0, 0)
        b = fr.add_node(L, 0)
        e = fr.add_element(a, b, EA, EI)
        if satt == "global":
            fr.set_udl(e, W)
        else:
            fr.set_udl_local(e, W)
        fr.add_support(a, ux=True, uy=True)
        fr.add_support(b, uy=True)
        fr.solve()
        resultat.append(fr.internal(e)[3])
    assert np.allclose(resultat[0], resultat[1])


def test_lokal_last_ar_vinkelrat_pa_lutande_element():
    """
    En lutande konsol med lokal last q_perp ska fa inspanningsmomentet
    q*l^2/2 med l = ELEMENTLANGDEN, oberoende av lutningen -- lasten
    foljer med elementet. En global last hade gett projektionseffekter.
    """
    langd = 4.0
    for vinkel in (0.0, 27.0, 45.0):
        v = np.radians(vinkel)
        fr = Frame()
        a = fr.add_node(0, 0)
        b = fr.add_node(langd * np.cos(v), langd * np.sin(v))
        e = fr.add_element(a, b, EA, EI)
        fr.set_udl_local(e, -3.0)
        fr.add_support(a, ux=True, uy=True, rz=True)
        fr.solve()
        _, _, _, M = fr.internal(e)
        assert M[0] == pytest.approx(-3.0 * langd**2 / 2, rel=1e-9), vinkel


def test_global_och_lokal_last_adderas():
    fr = Frame()
    a = fr.add_node(0, 0)
    b = fr.add_node(L, 0)
    e = fr.add_element(a, b, EA, EI)
    fr.set_udl(e, -4.0)
    fr.set_udl_local(e, -6.0)
    fr.add_support(a, ux=True, uy=True)
    fr.add_support(b, uy=True)
    fr.solve()
    _, _, _, M = fr.internal(e)
    assert max(M) == pytest.approx(abs(-10.0) * L**2 / 8, rel=1e-6)
