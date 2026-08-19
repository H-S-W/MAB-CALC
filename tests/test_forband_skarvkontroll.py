"""
Skarvkontrollen: varje halvgrupp ensam, ERRATA punkt 7.

Metoden ar last mot den ELASTISKA losningen -- skivan som fri styv
kropp, spikarna som fjadrar -- eftersom det ar den som avgjorde saken
mot handbokens 5.3.4.1. Referenslosningen delar ingen kod med
implementationen.
"""

import numpy as np
import pytest

import berakning
import material
from forband import kontrollera

FB = dict(skivmaterial="plywood_handbok", skiva_t=18.0,
          skiva_hojd_liv=206.0, skiva_hojd_ytter=300.0,
          forbindare_flans="ankarspik_2_5x50",
          forbindare_liv="ankarspik_2_5x50", cc_forbindare=25.0,
          rader_flans=7, kolumner_flans=1, kolumner_liv=4, rader_liv=4)


def _grupper():
    return berakning.spikgrupper(material.balk("H300"), FB, "C30plus")[0]


def elastisk_maxkraft_per_kNm(coords, phi=1e-3):
    """
    OBEROENDE referens: los skarven elastiskt med skivan som FRI styv
    kropp och returnera storsta spikkraft per overfort kNm. Fjader-
    styvheten forkortas bort, sa den behover inte vara den ratta.
    """
    k = 1.0
    A = np.zeros((3, 3))
    b = np.zeros(3)
    for x, y in coords:
        th = -phi / 2 if y < 0 else phi / 2
        B = np.array([[1.0, 0.0, -y], [0.0, 1.0, x]])
        A += k * B.T @ B
        b += k * B.T @ np.array([-th * y, th * x])
    d = np.linalg.solve(A, b)
    Fmax, M = 0.0, 0.0
    for x, y in coords:
        th = -phi / 2 if y < 0 else phi / 2
        B = np.array([[1.0, 0.0, -y], [0.0, 1.0, x]])
        f = k * (np.array([-th * y, th * x]) - B @ d)
        Fmax = max(Fmax, float(np.hypot(*f)))
        if y < 0:
            M += x * f[1] - y * f[0]
    return Fmax / (abs(M) / 1e6)          # kraft per kNm


def test_halvgruppsformeln_ar_den_elastiska_losningen():
    """
    Kardinalpunkten: M*r_egen/I_egen (om halvans EGEN tyngdpunkt) ska
    traffa den elastiska losningen exakt, medan handbokens
    M*r_hel/I_hel om fogen underskattar med faktor 2-2,5.
    """
    for gr in _grupper():
        elastisk = elastisk_maxkraft_per_kNm(gr.grupp.coords)
        _, Ip_egen, r_egen, _ = gr.grupp.halvdata()
        halv = r_egen / Ip_egen * 1e6
        handbok = gr.grupp.r / gr.grupp.Ip * 1e6
        assert halv == pytest.approx(elastisk, rel=1e-9), gr.namn
        # med stotfogsplaceringen (kant 15d) ligger raderna langre ut:
        # kvoten mot handbokens hela-bilden-formel ar 2,1-3,2
        assert 2.0 <= elastisk / handbok <= 3.3, gr.namn


def test_halvdata_ar_halften_av_spikarna():
    for gr in _grupper():
        n_halv, Ip_egen, r_egen, d = gr.grupp.halvdata()
        assert n_halv == gr.grupp.n / 2
        assert Ip_egen < gr.grupp.Ip / 2      # egen tyngdpunkt, ej fogen
        assert r_egen < gr.grupp.r
        assert d > 0


def test_excentricitetsmomentet_laggs_pa():
    """
    Snittkrafterna flyttas fran fogen till halvgruppens tyngdpunkt, sa
    tvarkraften ger ett extra moment V*d -- samma steg som 5.3.7 gor.
    """
    gr = _grupper()[0].grupp
    utan = gr.kraft_skarv(2.0, 5.0, 0.0)
    med = gr.kraft_skarv(2.0, 5.0, 5.0)
    _, Ip, r, d = gr.halvdata()
    vantat = (2.0 + 5.0 * d / 1000.0) * 1e3 * r / Ip + (5.0 ** 2 * 2) ** 0.5 / (gr.n / 2)
    assert med == pytest.approx(vantat, rel=1e-9)
    assert med > utan


def test_kontrollera_redovisar_bada_vagarna():
    """
    Skarvtalet ar det dimensionerande, men handbokens tal foljer med sa
    att avvikelsen mot exempel 5.3.4.1 gar att se.
    """
    grupper = [g.grupp for g in _grupper()]
    skivor = berakning._skivsatser(FB, material.skiva("plywood_handbok", 18.0),
                                   0.8, 1.2)[0]
    hb = kontrollera(skivor, grupper, 5.0, 10.0, 5.0)
    sk = kontrollera(skivor, grupper, 5.0, 10.0, 5.0, skarv=True)
    assert not hb.skarv and sk.skarv
    assert sk.utnyttjande > hb.utnyttjande
    assert sk.u_handbok == pytest.approx(hb.utnyttjande, rel=1e-9)
    assert sk.M_Rd < hb.M_Rd and sk.N_Rd < hb.N_Rd


def _projektcfg():
    import tomllib
    from pathlib import Path
    with open(Path(__file__).parent.parent / "input" / "projekt.toml",
              "rb") as fh:
        return tomllib.load(fh)


def test_metodvalet_styr_vilket_tal_som_galler():
    """
    nockmetod avgor vilken vag som blir dimensionerande, men BADA
    raknas alltid sa att skillnaden gar att se.
    """
    cfg = _projektcfg()
    hb = berakning.kor(cfg)
    assert not hb.kontroll.skarv
    assert hb.forband_utnyttjande == pytest.approx(
        hb.kontroll.u_handbok_totalt)

    cfg["forband"]["nockmetod"] = "halvgrupp"
    sk = berakning.kor(cfg)
    assert sk.kontroll.skarv
    assert sk.forband_utnyttjande == pytest.approx(
        sk.kontroll.u_skarv_totalt)

    # samma tva tal, oavsett vilket som valts
    assert hb.kontroll.u_skarv_totalt == pytest.approx(
        sk.kontroll.u_skarv_totalt, rel=1e-9)
    assert sk.kontroll.u_handbok_totalt == pytest.approx(
        hb.kontroll.u_handbok_totalt, rel=1e-9)
    assert sk.forband_utnyttjande > hb.forband_utnyttjande


def test_handboksvalet_varnar_om_halvgruppstalet():
    """Ett medvetet val ska synas, inte tystna."""
    r = berakning.kor(_projektcfg())
    varning = [v for v in r.varningar if "HALVGRUPP" in v]
    assert varning, r.varningar
    assert "provningsunderlag" in varning[0]


def test_ogiltig_nockmetod_sager_ifran():
    cfg = _projektcfg()
    cfg["forband"]["nockmetod"] = "gissning"
    with pytest.raises(ValueError, match="nockmetod"):
        berakning.kor(cfg)
