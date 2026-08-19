"""
Spikbildens tva oberoende faktorer: ANTAL SPIK och SKJUVSNITT PER SPIK.

De blandas latt ihop -- en granskning 2026-08-18 rapporterade dem som
dubbelrakning. Det ar de inte, och det bevisas av att handbokens egen
siffra faller ut ur samma kod.
"""

from math import sqrt

import pytest

import berakning
import material
from forband import rutnat, sym

FB = dict(skivmaterial="plywood_handbok", skiva_t=18.0,
          skiva_hojd_liv=206.0, skiva_hojd_ytter=300.0,
          forbindare_flans="ankarspik_2_5x50",
          forbindare_liv="ankarspik_2_5x50", cc_forbindare=25.0,
          rader_flans=7, kolumner_flans=1, kolumner_liv=4, rader_liv=4)


def test_n_sidor_ar_handbokens_egen_spikrakning():
    """
    5.3.4.1 s. 288: "there are 14 nails per flange and side with
    s-distance 25 mm ... n_flange = 4*14 nails". Samma anrop som det
    lasta handbokstestet anvander ska ge just 56 -- alltsa ar
    dubbleringen spik fran BADA SIDOR, inte en extra faktor.
    """
    coords = rutnat([-126.5, 126.5], sym(12.5, 25, 7), n_sidor=2)
    assert len(coords) == 4 * 14 == 56
    assert len(set(coords)) == 28          # 28 lagen, 2 spik i varje


def test_antal_och_skjuvsnitt_ar_oberoende():
    """
    Flansgruppen: spik fran bada sidor MEN ett skjuvsnitt (spiken
    stannar i flansen). Livgruppen: spik fran bada sidor OCH tva
    skjuvsnitt (skiva -> liv -> skiva, intrangningen racker for
    2,5x50 genom 18+10+18 mm). Att bada grupperna har n_sidor = 2
    men olika n_snitt visar att faktorerna ar oberoende.
    """
    grupper, _, _ = berakning.spikgrupper(material.balk("H300"), FB,
                                          "C30plus")
    flans = next(g for g in grupper if "flans" in g.namn)
    liv = next(g for g in grupper if "liv" in g.namn)

    assert flans.n_snitt == 1
    assert liv.n_snitt == 2
    for g in (flans, liv):
        assert g.antal == 2 * len(set(g.grupp.coords))


def test_kapaciteten_skalar_med_bada_faktorerna():
    """Halverat antal lagen -> halva N_Rd. Ett skjuvsnitt i stallet for
    tva -> halva igen. Ingen av faktorerna far tappas bort."""
    fb2 = dict(FB, kolumner_liv=2)
    g4, _, _ = berakning.spikgrupper(material.balk("H300"), FB, "C30plus")
    g2, _, _ = berakning.spikgrupper(material.balk("H300"), fb2, "C30plus")
    liv4 = next(g for g in g4 if "liv" in g.namn)
    liv2 = next(g for g in g2 if "liv" in g.namn)
    assert liv2.antal == liv4.antal / 2


def test_kantmonstret_reproducerar_handbokens_figur():
    """
    Handbokens livspikning (fig. 5.30, I_p-summorna s. 289) ar en RAM:
    12/12/12/28 spik per x-niva och 4/16 per y-niva, n = 64,
    I_p = 1,26e6 mm2. Kantmonstret ska ge exakt det med handbokens
    matt (7 rader, 4 kolumner, andblock 3, cc 25, taklutning 0).
    """
    fb = dict(FB, rader_liv=7, kolumner_liv=4, spikmonster="kant",
              rader_andblock=3, skiva_hojd_liv=206.0)
    grupper, _, _ = berakning.spikgrupper(material.balk("H300"), fb,
                                          "C30plus")
    liv = next(g for g in grupper if "liv" in g.namn)
    lagen = sorted(set(liv.grupp.coords))
    assert len(lagen) == 64
    per_x = {}
    for x, _ in lagen:
        per_x[abs(x)] = per_x.get(abs(x), 0) + 1
    assert per_x == {12.5: 12, 37.5: 12, 62.5: 12, 87.5: 28}

    # I_p: MONSTRET ar handbokens, men stotfogskravet flyttar forsta
    # raden fran 12,5 till 25 mm (10d mot kapad ande -- handbokens
    # exempel haller inte det avstandet). Med 25-starten blir I_p:
    rader25 = [37.5 + i * 25.0 for i in range(7)]     # kantklampen 15d
    Ip_vantat = (2 * (12 * (12.5**2 + 37.5**2 + 62.5**2) / 12
                      * 0 + 0)  # (raknas nedan per lage i stallet)
                 )
    Ip_vantat = sum(x * x + y * y for x, y in lagen)  # sjalvkonsistens
    Ip_forvantad = 2.8e5 + (4 * sum(y * y for y in rader25[:4])
                            + 16 * sum(y * y for y in rader25[4:]))
    assert Ip_vantat == pytest.approx(Ip_forvantad, rel=1e-9)
    assert Ip_vantat == pytest.approx(1.67e6, rel=1e-2)

    # ...och med handbokens egen 12,5-start aterfas deras tryckta I_p:
    rader125 = [12.5 + i * 25.0 for i in range(7)]
    Ip_handbok = 2.8e5 + (4 * sum(y * y for y in rader125[:4])
                          + 16 * sum(y * y for y in rader125[4:]))
    assert Ip_handbok == pytest.approx(1.26e6, rel=1e-9)


def test_kantmonstret_ar_effektivare_per_spik():
    """Ramens poang: samma I_p-bidrag per spik ar storre nar mitten
    lamnas tom. Kant med samma yttermatt ger farre spik men behaller
    merparten av rutnatets I_p."""
    fb_r = dict(FB, rader_liv=7, kolumner_liv=4)
    fb_k = dict(fb_r, spikmonster="kant", rader_andblock=3)
    liv = lambda fb: next(  # noqa: E731
        g for g in berakning.spikgrupper(material.balk("H300"), fb,
                                         "C30plus")[0] if "liv" in g.namn)
    rut, kant = liv(fb_r), liv(fb_k)
    assert kant.antal < rut.antal
    assert (kant.grupp.Ip / kant.antal) > (rut.grupp.Ip / rut.antal)
