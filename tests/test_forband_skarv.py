"""
Nockens rotationsstyvhet -- skivan ar en FRI kropp.

Det har ar tredje forsoket pa den har harledningen, sa den ar last med
en OBEROENDE metod: en numerisk energiminimering over skivans tre
frihetsgrader, som inte delar en rad kod med implementationen.

  forsok 1: K = K*n*I_egen/2 per grupp          RATT
  forsok 2: K = K*n*I_p,hel/4  ("Steiner")      FEL, 1,5x for styvt
  forsok 3: = forsok 1, nu belagt numeriskt

Felet i forsok 2 var att anta att skivan halls fast mot TRANSLATION.
Det gor ingenting -- den halls bara av spikarna.
"""

import numpy as np
import pytest

import berakning
import forbindare_ec5 as EC5
import material

FB = dict(skivmaterial="plywood_handbok", skiva_t=18.0,
          skiva_hojd_liv=206.0, skiva_hojd_ytter=300.0,
          forbindare_flans="ankarspik_2_5x50",
          forbindare_liv="ankarspik_2_5x50", cc_forbindare=25.0,
          rader_flans=7, kolumner_flans=1, kolumner_liv=4, rader_liv=4)


def _grupper():
    return berakning.spikgrupper(material.balk("H300"), FB, "C30plus")[0]


def K_ur_energi(coords, k, phi=1e-3):
    """
    OBEROENDE referens: minimera skivans tojningsenergi over dess tre
    frihetsgrader (ux, uy, theta_s) nar sparrarna roterar -phi/2 (y<0)
    och +phi/2 (y>0) kring fogen. Delar ingen kod med K_rot_skarv.

    Returnerar (K [kNm/rad], skivans rorelse).
    """
    A = np.zeros((3, 3))
    b = np.zeros(3)
    for x, y in coords:
        th = -phi / 2 if y < 0 else phi / 2
        ur = np.array([-th * y, th * x])
        B = np.array([[1.0, 0.0, -y], [0.0, 1.0, x]])
        A += k * B.T @ B
        b += k * B.T @ ur
    d = np.linalg.solve(A, b)
    E = 0.0
    for x, y in coords:
        th = -phi / 2 if y < 0 else phi / 2
        ur = np.array([-th * y, th * x])
        B = np.array([[1.0, 0.0, -y], [0.0, 1.0, x]])
        dl = ur - B @ d
        E += 0.5 * k * dl @ dl
    return 2 * E / phi ** 2 / 1e6, d


def test_energiminimering_bekraftar_formeln():
    """Formeln K*n*I_egen/2 mot en oberoende energiminimering."""
    rho_m = material.flanskvaliteter()["C30plus"]["rho_mean"]
    for gr in _grupper():
        k = EC5.K_ser(gr.forbindare, rho_m) * gr.n_snitt
        K_energi, _ = K_ur_energi(gr.grupp.coords, k)
        I_v, I_h = berakning.halvgruppernas_Ip(gr.grupp.coords)
        K_formel = EC5.K_rot_skarv([(gr.forbindare, gr.n_snitt, I_v, I_h)],
                                   rho_m)
        assert K_formel == pytest.approx(K_energi, rel=1e-9), gr.namn
        assert K_formel == pytest.approx(k * I_v / 2 / 1e6, rel=1e-9)


def test_skivan_translaterar_men_roterar_inte():
    """
    Sjalva anledningen till att Steinertermen inte hor hit: bada
    halvgruppernas tyngdpunkter ror sig at SAMMA hall, sa skivan foljer
    med utan att vrida sig. Da ser varje halva ren rotation kring sin
    egen tyngdpunkt.
    """
    rho_m = material.flanskvaliteter()["C30plus"]["rho_mean"]
    phi = 1e-3
    for gr in _grupper():
        k = EC5.K_ser(gr.forbindare, rho_m) * gr.n_snitt
        _, d = K_ur_energi(gr.grupp.coords, k, phi)
        halv = [(x, y) for x, y in gr.grupp.coords if y > 0]
        dm = sum(y for _, y in halv) / len(halv)
        assert d[0] == pytest.approx(-phi * dm / 2, rel=1e-9)   # ux
        assert d[1] == pytest.approx(0.0, abs=1e-12)            # uy
        assert d[2] == pytest.approx(0.0, abs=1e-12)            # theta_s


def test_steinervarianten_ar_for_styv():
    """
    Fallan: K_rot/4 (skiva last mot translation) ger 1,5 ganger for hog
    styvhet for projektfilens spikning. Testet star kvar som en sparr
    mot att harledningen "rattas" tillbaka.
    """
    rho_m = material.flanskvaliteter()["C30plus"]["rho_mean"]
    grupper = _grupper()
    ratt = sum(EC5.K_rot_skarv(
        [(g.forbindare, g.n_snitt, *berakning.halvgruppernas_Ip(
            g.grupp.coords))], rho_m) for g in grupper)
    steiner = EC5.K_rot([(g.forbindare, g.n_snitt, g.grupp.Ip)
                         for g in grupper], rho_m) / 4
    # I_egen ar oforandrad av att raderna skjuts ut likformigt (kant
    # 15d), sa 355,3 star sig -- medan Ip-om-fogen vaxer med kvadraten
    # pa forskjutningen: kvoten ar nu 2,04.
    assert ratt == pytest.approx(355.3, rel=0.01)
    assert steiner == pytest.approx(723.0, rel=0.01)
    assert steiner / ratt == pytest.approx(2.04, abs=0.02)


def test_osymmetriska_halvor_seriekopplas():
    """
    Lika halvor ger K*n*I/2. Olika halvor ska seriekopplas, alltsa
    ligga UNDER det harmoniska medelvardet av de tva -- inte medelvarde.
    """
    f = material.forbindare("ankarspik_2_5x50")
    rho_m = 460.0
    lika = EC5.K_rot_skarv([(f, 1, 1.0e6, 1.0e6)], rho_m)
    olika = EC5.K_rot_skarv([(f, 1, 0.5e6, 1.5e6)], rho_m)
    k = EC5.K_ser(f, rho_m)
    assert lika == pytest.approx(k * 1.0e6 / 2 / 1e6, rel=1e-9)
    assert olika == pytest.approx(
        1 / (1 / (k * 0.5e6) + 1 / (k * 1.5e6)) / 1e6, rel=1e-9)
    assert olika < lika                      # serien straffar den svaga


def test_tom_halva_ger_ingen_styvhet():
    """Sitter alla spik pa en sida av fogen overfors inget moment."""
    f = material.forbindare("ankarspik_2_5x50")
    assert EC5.K_rot_skarv([(f, 1, 1.0e6, 0.0)], 460.0) == 0.0


def test_vriden_geometri_ar_alfa_noll_vid_platt():
    """
    K_rot_skarv_vriden ar den allmanna losningen; vid alfa = 0 maste den
    aterge den slutna formeln K*n*I_egen/2 exakt. Det ar lasningen som
    hindrar en regression i endera riktningen.
    """
    rho_m = material.flanskvaliteter()["C30plus"]["rho_mean"]
    grupper = _grupper()
    data = [(g.forbindare, g.n_snitt, g.grupp.coords) for g in grupper]
    halvor = [(g.forbindare, g.n_snitt,
               *berakning.halvgruppernas_Ip(g.grupp.coords))
              for g in grupper]
    assert EC5.K_rot_skarv_vriden(data, rho_m, 0.0) ==         pytest.approx(EC5.K_rot_skarv(halvor, rho_m), rel=1e-9)


def test_taklutningen_hojer_skarvstyvheten():
    """
    I vriden geometri ror sig halvornas tyngdpunkter inte parallellt, sa
    skivans translation kan inte avlasta bada -- en del av Steinertermen
    kommer tillbaka och styvheten stiger monotont med taklutningen.
    27 grader ger 393,0 kNm/rad: talet reproducerades OBEROENDE av
    granskningsomgang 4:s egen losare innan den har implementationen
    skrevs, och lases dar for som regressionsvarde.
    """
    from math import radians

    rho_m = material.flanskvaliteter()["C30plus"]["rho_mean"]
    data = [(g.forbindare, g.n_snitt, g.grupp.coords) for g in _grupper()]
    K = [EC5.K_rot_skarv_vriden(data, rho_m, radians(a))
         for a in (0.0, 15.0, 27.0, 40.0)]
    assert K == sorted(K)                       # monotont stigande
    # 410,3 galler spikbilden MED stotfogskravet (forsta raden 25 mm ut);
    # den aldre platta bilden gav 393,0, oberoende reproducerat av
    # granskningsomgang 4 -- kvar som historik i ERRATA punkt 7.
    assert K[2] == pytest.approx(431.1, rel=0.005)
    # och ligger alltid under en-stel-del-taket
    tak = EC5.K_rot([(g.forbindare, g.n_snitt, g.grupp.Ip)
                     for g in _grupper()], rho_m)
    assert K[-1] < tak
