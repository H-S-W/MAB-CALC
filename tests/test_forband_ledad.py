"""
Ledat nockforband, handboken 5.3.7.

Tva saker last har: att axelkonventionen ar densamma som i den
momentstyva vagen (berakning.spikgrupper), och att handbokens eget
raknexempel gar att reproducera -- det senare ar grunden for
docs/ERRATA.md punkt 3, som avgjorde att `n` i F = M*r/Ip + N/n ar
spikantalet PER GRUPP.
"""

from math import sqrt

import pytest

from forband import Forbindargrupp, ledad_nock

# Handbokens 5.3.7: 18+18 mm plywood spikad direkt mot livet, 42 spik
# 2,5x50 med halften fran varje sida, tva skjuvsnitt -> 0,6 kN/spik.
S = dict(t_skiva=18.0, h_skiva=206.0, f_t_skiva=9.4, f_v_skiva=6.8,
         k_mod=0.8, gamma_M=1.2, F_Rd_per_snitt=0.3, n_snitt=2)


def test_handbokens_5_3_7_exempel_reproduceras():
    """
    Handboken (s. 301-302) anger I_p = 1,35e5 mm2, r = 135 mm,
    e = 121 mm, N = V = 3,5 kN och far F = 0,592 kN. Med n = 21 (halva
    det tryckta antalet 42, dvs gruppen pa EN sida av fogen) blir

        F = 0,424e6 * 135 / 135 000 + 3 500 / 21 = 424 + 167 = 591 N

    Handbokens egen spikbild gar inte att bygga med ett symmetriskt
    rutnat (21 ar udda), sa gruppen byggs har direkt ur de tryckta
    storheterna. Det som lases ar formeln och tolkningen av n.
    """
    grupp = Forbindargrupp("5.3.7", 0.3, 2, n=21, Ip=1.35e5, r=135.0)
    M = 3.5 * 0.121                      # V * e
    F = grupp.kraft(M, 3.5, 0.0)         # handboken utelamnar V/n
    assert F == pytest.approx(0.591, abs=0.002)
    assert F <= 0.6                       # handbokens V_ed per spik

    # Med n = 42 (hela spikantalet) gar exemplet INTE ihop -- det ar
    # bevisningen bakom ERRATA punkt 3.
    fel = Forbindargrupp("5.3.7 fel n", 0.3, 2, n=42, Ip=1.35e5, r=135.0)
    assert fel.kraft(M, 3.5, 0.0) < 0.55


def test_axlarna_foljer_den_momentstyva_vagen():
    """
    KOLUMNER tvars balken (skivhojdens led), RADER langs balken ut fran
    fogen -- samma som berakning.spikgrupper. Det ar radernas avstand
    som ger excentriciteten, for tvarkraften flyttas LANGS balken fran
    ena gruppen till den andra.
    """
    s = 25.0
    led = ledad_nock(N=5.0, V=5.0, kolumner=2, rader=6, s=s, **S)
    # 6 rader: 12,5 / 37,5 / ... / 137,5 -> medel 75,0 mm
    assert led.e == pytest.approx(75.0)

    coords = led.grupp.coords
    # sym() ger +/-par, sa kolumner=2 betyder 2 PER SIDA om mittlinjen:
    # x = +/-12,5 och +/-37,5. Samma konvention som spikgrupper.
    assert sorted({round(x, 2) for x, _ in coords}) ==         [-37.5, -12.5, 12.5, 37.5]
    # raderna loper langs balken, centrerade kring tyngdpunkten
    assert max(abs(y) for _, y in coords) == pytest.approx(62.5)
    # (2 kolumner per sida x 2) x 6 rader x 2 skivsidor
    assert len(coords) == (2 * 2) * 6 * 2


def test_excentriciteten_vaxer_med_antalet_rader():
    """Fler rader -> gruppens tyngdpunkt hamnar langre fran fogen ->
    storre excentricitetsmoment. Kolumnerna ska inte paverka e."""
    s = 25.0
    e2 = ledad_nock(5.0, 5.0, kolumner=3, rader=2, s=s, **S).e
    e6 = ledad_nock(5.0, 5.0, kolumner=3, rader=6, s=s, **S).e
    assert e6 > e2
    assert ledad_nock(5.0, 5.0, kolumner=8, rader=2, s=s,
                      **{**S, "h_skiva": 400.0}).e == pytest.approx(e2)


def test_spik_utanfor_skivan_varnar():
    """Skyddet maste traffa skivhojdens led, dvs KOLUMNERNA."""
    s = 25.0
    ok = ledad_nock(5.0, 5.0, kolumner=4, rader=3, s=s, **S)
    assert not ok.varningar                     # +/-87,5 ryms i 206 mm

    fel = ledad_nock(5.0, 5.0, kolumner=10, rader=3, s=s, **S)
    assert fel.varningar and "utanför skivan" in fel.varningar[0]


def test_tvarkraften_ingar_i_forbindarkraften():
    """Metodvalet: F = M*r/Ip + sqrt(N^2+V^2)/n, strangare an
    handbokens N/n. Skillnaden ska synas."""
    med_v = ledad_nock(N=5.0, V=5.0, kolumner=3, rader=3, s=25.0, **S)
    utan_v = ledad_nock(N=5.0, V=0.0, kolumner=3, rader=3, s=25.0, **S)
    assert med_v.F > utan_v.F
    assert sqrt(5.0 ** 2 + 5.0 ** 2) > 5.0


def test_ledad_nock_haller_stotfogen():
    """
    Granskning 2026-08-19: ledad_nock lade spikbilden platt -- 4 av 32
    lagen hamnade inne i motstaende sparre och e underskattades 43 %.
    Med taklutning och kantavstand ska ALLA spik ligga pa ratt sida med
    minst kantavstandet, och excentriciteten vaxa.
    """
    from math import cos, radians, sin

    platt = ledad_nock(N=5.0, V=5.0, kolumner=4, rader=4, s=25.0, **S)
    klampad = ledad_nock(N=5.0, V=5.0, kolumner=4, rader=4, s=25.0,
                         taklutning_grader=27.0, kant_ande=37.5, **S)
    assert klampad.e > platt.e
    assert klampad.M > platt.M

    alfa = radians(27.0)
    for x, yc in klampad.grupp.coords:
        y = yc + klampad.e                    # absolut avstand fran fogen
        X = y * cos(alfa) + x * sin(alfa)
        assert X >= 37.5 - 1e-9, (x, y, X)
