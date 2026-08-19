"""
Verifiering mot Masonite Beams I-joist Handbook, exempel 5.3.4.2 (s. 291-294)
"Eaves connection - articulated upper frame & clamped lower frame".

Handbokens tryckta varden:
  V_Rd (skjuv i plywood langs flans, 300 mm snitt)   14.4 kN
  N (tryck i overram)                                14.4 kN
  M i underram = N * 0.300 m                          4.3 kNm
  Ip_flans  8.4e5 + 4.55e5 = 1.3e6 mm2
  Ip_liv    6.3e5 + 1.52e6 = 2.1e6 mm2
  M_underram = M_web + M_flange                       6.0 kNm

Detta exempel ar internt konsekvent med ETT skjuvsnitt i bada grupperna,
vilket ar skalet till att projektet defaultar till n_planes=1.
"""

import sys, os
from math import sqrt
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from forband import (Forbindargrupp, rutnat, sym,                  # noqa: E402
                     skjuvkontroll_skiva)

K_MOD, GAMMA_M = 0.8, 1.20
T_PL, F_V_K = 18.0, 3.0


def test_skjuvkapacitet_plywood():
    """V_Rd = 2 * k_cr * t * 300 * f_v_k / 1.5 * k_mod/gamma_M = 14.4 kN"""
    V_Rd = skjuvkontroll_skiva(T_PL, 300.0, F_V_K, K_MOD, GAMMA_M,
                               n_skivor=2, k_cr=1.0)
    assert V_Rd == pytest.approx(14.4, abs=0.05)


def test_moment_fran_havarm():
    """M = N * l med l = 300 mm mellan over- och underramens tyngdpunkter."""
    N = 14.4
    assert N * 0.300 == pytest.approx(4.3, abs=0.05)


def flansgrupp():
    # 13 spik per flans och sida, y = 127 mm, x fran 0 med steg 25 mm, 7 kolumner
    x_pos = sym(0.0, 25.0, 7)[7:] + [-v for v in sym(0.0, 25.0, 7)[7:]]
    x_pos = sorted(set([0.0] + [25.0*i for i in range(1, 7)]
                       + [-25.0*i for i in range(1, 7)]))
    coords = []
    for s in (+127.0, -127.0):
        for x in [0.0] + [25.0*i for i in range(1, 7)]:
            coords += [(x, s), (-x, s)] if x else [(x, s)]
    return Forbindargrupp("Spik -> flans", F_plane=0.36, n_planes=1,
                          coords=coords * 2)


def test_flans_ip():
    g = flansgrupp()
    assert g.n == 52                                   # 4 * 13
    assert g.Ip == pytest.approx(1.294e6, rel=0.02)    # handbok 1.3e6
    assert g.r == pytest.approx(196.5, abs=0.5)


def test_livgrupp_ip():
    Ip_y = 2*(8*12.5**2 + 8*37.5**2 + 26*62.5**2 + 26*87.5**2)
    Ip_x = 2*(4*0.0**2 + 8*25.0**2 + 8*50.0**2 + 8*75.0**2
              + 8*100.0**2 + 16*125.0**2 + 16*150.0**2)
    assert Ip_y == pytest.approx(6.3e5, rel=0.02)
    assert Ip_x == pytest.approx(1.52e6, rel=0.02)
    g = Forbindargrupp("Spik -> liv", F_plane=0.30, n_planes=1,
                       n=68, Ip=Ip_x + Ip_y,
                       r=sqrt(150.0**2 + 87.5**2))
    assert g.Ip == pytest.approx(2.146e6, rel=0.02)    # handbok 2.1e6
    assert g.r == pytest.approx(173.7, abs=0.5)


def test_underram_total_momentkapacitet():
    """
    M_underram = M_flange + M_web = 6.0 kNm enligt handboken.
    Reproduceras med ETT skjuvsnitt i bada grupperna (0.36 resp 0.30 kN).
    """
    fl = flansgrupp()
    Ip_y = 2*(8*12.5**2 + 8*37.5**2 + 26*62.5**2 + 26*87.5**2)
    Ip_x = 2*(4*0.0**2 + 8*25.0**2 + 8*50.0**2 + 8*75.0**2
              + 8*100.0**2 + 16*125.0**2 + 16*150.0**2)
    liv = Forbindargrupp("Spik -> liv", F_plane=0.30, n_planes=1,
                         n=68, Ip=Ip_x + Ip_y, r=sqrt(150.0**2 + 87.5**2))
    assert fl.M_Rd + liv.M_Rd == pytest.approx(6.0, abs=0.15)


def test_forbandet_racker():
    fl = flansgrupp()
    Ip_y = 2*(8*12.5**2 + 8*37.5**2 + 26*62.5**2 + 26*87.5**2)
    Ip_x = 2*(4*0.0**2 + 8*25.0**2 + 8*50.0**2 + 8*75.0**2
              + 8*100.0**2 + 16*125.0**2 + 16*150.0**2)
    liv = Forbindargrupp("Spik -> liv", F_plane=0.30, n_planes=1,
                         n=68, Ip=Ip_x + Ip_y, r=sqrt(150.0**2 + 87.5**2))
    assert fl.M_Rd + liv.M_Rd > 4.3
