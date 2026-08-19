"""
Verifiering av src/dimensionera.py -- tomt falt = foresla.

Regeln: lagsta balkhojd som klarar ALLA kontroller, darefter minsta
spikantal. Alla kandidater redovisas med utnyttjande och vad som styr,
inte bara vinnaren.
"""

import copy
import tomllib
from pathlib import Path

import pytest

import dimensionera
import material

PROJEKTFIL = Path(__file__).parent.parent / "input" / "projekt.toml"


def sokbar_cfg(**extra):
    """
    Projektfilen med tom balk, filtrerad till HB-serien med spanskiveliv:
    lyftfallet kan ge drag i sparren, och HB med OSB-liv saknar anvandbar
    dragkapacitet i ETA:n (ERRATA punkt 4) -- da vagrar balkkontrollen.
    HB...s har deklarerad N_tk.

    Upplaget ar UTLYFT ur valet (anvandarbeslut 2026-08-18), sa
    projektfilens 45 mm oforstarkta upplag ligger kvar har -- testerna
    nedan bevisar att det redovisas men inte paverkar valet.
    """
    with open(PROJEKTFIL, "rb") as fh:
        cfg = tomllib.load(fh)
    cfg["geometri"]["balk"] = ""
    cfg["dimensionering"]["foresla_serie"] = "HB"
    cfg["dimensionering"]["foresla_liv"] = "spanskiva"
    # tomma skivhojder = folj balken
    cfg["forband"]["skiva_hojd_liv"] = 0.0
    cfg["forband"]["skiva_hojd_ytter"] = 0.0
    for stig, varde in extra.items():
        d = cfg
        *fore, sista = stig.split(".")
        for del_ in fore:
            d = d[del_]
        d[sista] = varde
    return cfg


@pytest.fixture(scope="module")
def forslag():
    return dimensionera.foresla(sokbar_cfg())


def test_alla_kandidater_redovisas(forslag):
    """Nio hojder i HB-serien, i stigande hojdordning, alla med siffror."""
    assert len(forslag.kandidater) == 9
    hojder = [k.h for k in forslag.kandidater]
    assert hojder == sorted(hojder)
    for k in forslag.kandidater:
        assert k.balk_u > 0 and k.forband_u > 0
        assert k.styrande in ("balken", "nockförbandet",
                              "nedböjningen")


def test_valet_ar_lagsta_balk_som_haller(forslag):
    assert forslag.vald, [f"{k.namn}: {k.styrande} {max(k.balk_u, k.forband_u, k.nedbojning_u):.2f}"
                          for k in forslag.kandidater]
    hallande = [k for k in forslag.kandidater if k.haller]
    assert forslag.vald == hallande[0].namn
    # ingen lagre balk haller
    for k in forslag.kandidater:
        if k.h < hallande[0].h:
            assert not k.haller


def test_kandidater_under_valet_har_en_styrande_orsak(forslag):
    vald_h = next(k.h for k in forslag.kandidater if k.namn == forslag.vald)
    for k in forslag.kandidater:
        if k.h < vald_h:
            assert max(k.balk_u, k.forband_u, k.nedbojning_u) > 1.0


def test_skivhojderna_foljer_balken_nar_de_ar_tomma(forslag):
    """
    Med skiva_hojd_liv = 0 ska livforstarkningen fa balkens fria livhojd
    -- annars raknar alla kandidater med samma skivor och jamforelsen
    haltar.
    """
    res = forslag.resultat
    b = material.balk(forslag.vald)
    skivor = {s.namn: s.h for s in res.skivor_handbok}
    assert skivor["Livforstarkning"] == b.h_liv
    assert skivor["Utanpaliggande skiva"] == b.h


def test_spikforslaget_ar_minsta_antalet_som_haller(forslag):
    s = forslag.spik
    assert s.get("hittad"), s
    assert s["utnyttjande"] <= 1.0
    assert s["verifierad"], "spikforslaget holl inte i full verifiering"
    fullt = 8 * s["rader_flans"] * s.get("kolumner_flans", 1) + \
        8 * s["kolumner_liv"] * s["rader_liv"]
    if s.get("spikmonster", "rutnat") == "rutnat":
        assert s["totalt"] == fullt
    else:
        # kantmonstret glesar ur mitten: farre spik an fulla rutnatet
        assert s["totalt"] < fullt


def test_spikforslaget_verifieras_med_full_korning(forslag):
    """K_r-aterkopplingen: forslaget kors om med full kedja innan det
    godkanns, sa att den fasta snittkraftsforenklingen inte kan ge ett
    falskt godkannande."""
    assert "utnyttjande_verifierad" in forslag.spik
    assert forslag.spik["utnyttjande_verifierad"] <= 1.0


def test_upplaget_styr_inte_valet(forslag):
    """Alla kandidater overskrider upplaget med 45 mm oforstarkt upplag
    -- valet gar anda igenom, med en anmarkning som pekar pa
    L1/forstarkning i stallet for balkbyte."""
    assert forslag.vald
    assert all(k.upplag_u > 1.0 for k in forslag.kandidater)
    assert any("Upplaget överskrids" in a for a in forslag.anmarkningar)
    assert forslag.resultat.haller
    assert not forslag.resultat.upplaget_haller


def test_battre_upplag_andrar_inte_valet(forslag):
    """Samma balk ska valjas oavsett upplagsdetalj -- beviset for att
    upplaget ar utlyft ur valet."""
    f2 = dimensionera.foresla_balk(sokbar_cfg(**{
        "upplag.L1": 145.0, "upplag.forstarkning": True}))
    assert f2.vald == forslag.vald


def test_omojlig_sokning_sager_det_rakt_ut():
    """Nar ingen balk racker (har: dubbel spannvidd) ska anmarkningen
    saga det rakt ut, och den styrande kolumnen forklara varfor."""
    cfg = sokbar_cfg(**{"geometri.spannvidd": 20.0})
    f = dimensionera.foresla_balk(cfg)
    assert not f.vald
    assert any("Ingen balk" in a for a in f.anmarkningar)


def test_filtret_pa_serie_och_liv_respekteras():
    cfg = sokbar_cfg()
    cfg["dimensionering"]["foresla_serie"] = "HB"
    cfg["dimensionering"]["foresla_liv"] = "spanskiva"
    f = dimensionera.foresla_balk(cfg)
    assert all(k.serie == "HB" and k.liv == "spanskiva"
               for k in f.kandidater)


def test_tom_filter_ger_hela_biblioteket_med_anmarkning():
    cfg = sokbar_cfg()
    cfg["dimensionering"]["foresla_serie"] = ""
    cfg["dimensionering"]["foresla_liv"] = ""
    lista = dimensionera._kandidatlista(cfg)
    assert len(lista) == 72


def test_monstret_ingar_i_optimeringen(forslag):
    """
    Sokningen provar bade rutnatet och handbokens ram (fig. 5.30) per
    geometri och sorterar pa (totalt antal, utnyttjande) -- sa ramen
    vinner exakt dar den racker med farre spik. Kandidatlistan ska
    innehalla BADA monstren och vara sorterad pa antalet, och varje
    kant-kandidat ska ha inre kolumner att glesa ur.
    """
    c = dimensionera._med_balk(sokbar_cfg(), forslag.vald)
    kand = dimensionera.foresla_spik(c, forslag.resultat)
    monster = {sp["spikmonster"] for sp in kand}
    assert monster == {"rutnat", "kant"}
    tot = [sp["totalt"] for sp in kand]
    assert tot == sorted(tot)
    for sp in kand:
        if sp["spikmonster"] == "kant":
            assert sp["kolumner_liv"] >= 3
            assert sp["rader_liv"] > sp["rader_andblock"]
