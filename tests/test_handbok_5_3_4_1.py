"""
Verifiering mot Masonite Beams I-joist Handbook, exempel 5.3.4.1 (s. 286-290)
"Moment rigid upper frame corner", H300.

Handbokens tryckta varden:
  W_liv        2.5e5 mm3       M_PL.web.d    3.8 kNm
  W_ytter      5.4e5 mm3       M_PL.reinf.d  8.1 kNm
  Ip_flans     1.5e6 mm2       r_flans     205.9 mm    M_flange 2.6 kNm
  Ip_liv       1.3e6 mm2       r_liv       184.6 mm    M_web    3.96 kNm
  M_Rd         6.52 kNm        N_Rd         38.7 kN

Se docs/ERRATA.md for de tva avvikelser som hittats.
"""

import sys, os
from math import sqrt
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from forband import Forbindargrupp, Skiva, rutnat, sym, kontrollera   # noqa: E402

K_MOD, GAMMA_M = 0.8, 1.20
T_PL, F_M_K = 18.0, 22.5
H, H_WEB = 300.0, 206.0


@pytest.fixture
def skivor():
    return [
        Skiva("Livforstarkning 18+18", T_PL, H_WEB, 2, F_M_K, K_MOD, GAMMA_M),
        Skiva("Utanpaliggande 18+18", T_PL, H, 2, F_M_K, K_MOD, GAMMA_M),
    ]


@pytest.fixture
def flansgrupp():
    # 14 spik per flans och sida, s = 25 mm, x = +/-126.5 mm, spik fran bada sidor
    return Forbindargrupp("Spik -> flans", F_plane=0.36, n_planes=1,
                          coords=rutnat([-126.5, 126.5], sym(12.5, 25, 7),
                                        n_sidor=2))


@pytest.fixture
def livgrupp():
    # Handbokens egna summationstermer for den icke-rektangulara gruppen
    Ip_x = 12*12.5**2 + 12*37.5**2 + 12*62.5**2 + 28*87.5**2
    Ip_y = (4*12.5**2 + 4*37.5**2 + 4*62.5**2 + 4*87.5**2
            + 16*112.5**2 + 16*137.5**2 + 16*162.5**2)
    return Forbindargrupp("Spik -> liv", F_plane=0.30, n_planes=1,
                          n=64, Ip=Ip_x + Ip_y, r=sqrt(87.5**2 + 162.5**2))


# --- plywood ---------------------------------------------------------------

def test_bojmotstand(skivor):
    assert skivor[0].W == pytest.approx(2.5e5, rel=0.02)
    assert skivor[1].W == pytest.approx(5.4e5, rel=0.01)


def test_plywood_momentkapacitet(skivor):
    assert skivor[0].M_d == pytest.approx(3.8, abs=0.05)
    assert skivor[1].M_d == pytest.approx(8.1, abs=0.05)


def test_errata_karakteristisk_kapacitet_ytterskiva(skivor):
    """
    Handboken trycker M_PL.reinf.k = 5.7 kNm. Ratt varde ar W*f_m,k = 12.2 kNm;
    det dimensionerande vardet 8.1 kNm ar dock korrekt.
    """
    assert skivor[1].M_k == pytest.approx(12.15, abs=0.05)
    assert skivor[1].M_k != pytest.approx(5.7, abs=0.1)


# --- flansgrupp ------------------------------------------------------------

def test_flans_antal(flansgrupp):
    assert flansgrupp.n == 56          # 4 * 14


def test_flans_polart_troghetsmoment(flansgrupp):
    assert flansgrupp.Ip == pytest.approx(1.465e6, rel=0.01)


def test_flans_radie(flansgrupp):
    assert flansgrupp.r == pytest.approx(205.9, abs=0.1)


def test_flans_momentkapacitet(flansgrupp):
    assert flansgrupp.M_Rd == pytest.approx(2.6, abs=0.05)


# --- livgrupp --------------------------------------------------------------

def test_liv_polart_troghetsmoment(livgrupp):
    assert livgrupp.Ip == pytest.approx(1.26e6, rel=0.01)


def test_liv_radie(livgrupp):
    assert livgrupp.r == pytest.approx(184.6, abs=0.1)


def test_errata_livgruppens_momentkapacitet(livgrupp):
    """
    Handboken trycker M_web = 3.96 kNm. Med de vardsen den sjalv anger
    (F = 0.30 kN, Ip = 1.26e6, r = 184.6) blir resultatet 2.05 kNm.
    3.96 forutsatter 2 skjuvsnitt, vilket handbokens eget exempel 5.3.4.2
    INTE gor for samma typ av grupp. Se docs/ERRATA.md.
    """
    assert livgrupp.M_Rd == pytest.approx(2.05, abs=0.05)

    tvasnittad = Forbindargrupp("2 snitt", F_plane=0.30, n_planes=2,
                                n=livgrupp.n, Ip=livgrupp.Ip, r=livgrupp.r)
    assert tvasnittad.M_Rd == pytest.approx(4.10, abs=0.05)


# --- sammansatt ------------------------------------------------------------

def test_normalkraftskapacitet(flansgrupp, livgrupp):
    """Handbokens N_Rd = 38.7 kN forutsatter 1 skjuvsnitt i bada grupperna."""
    N_Rd = flansgrupp.N_Rd + livgrupp.N_Rd
    assert N_Rd == pytest.approx(39.4, abs=0.5)


def test_momentkapacitet_konservativ(skivor, flansgrupp, livgrupp):
    """
    Med konsekvent enkelsnittade forbindare blir M_Rd = 4.6 kNm,
    inte handbokens 6.52 kNm. Anvand det lagre vardet.
    """
    res = kontrollera(skivor, [flansgrupp, livgrupp],
                      M_Ed=3.0, N_Ed=10.0)
    assert res.M_plywood == pytest.approx(11.9, abs=0.1)
    assert res.M_forbindare == pytest.approx(4.6, abs=0.1)
    assert res.M_Rd == pytest.approx(4.6, abs=0.1)
    assert res.dimensionerande == "forbindare"


def test_interaktion(skivor, flansgrupp, livgrupp):
    res = kontrollera(skivor, [flansgrupp, livgrupp], M_Ed=3.0, N_Ed=10.0)
    assert res.utnyttjande == pytest.approx(3.0/4.61 + 10.0/39.4, abs=0.01)
