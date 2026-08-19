"""
Verifiering av src/material.py -- uppslagningen i materialbiblioteken.

Testerna kontrollerar att uppslagningen ger rätt varden ur rätt tabell, och
sarskilt att de tva k_mod-serierna inte blandas: bojning och tvarkraft har
olika varden i ETA tab. 17, och skivor har helt egna varden ur EC5 tab. 3.1.
Att blanda dem ar det latta felet att gora och det svara att upptacka.
"""

import pytest

import material as M


# ---------------------------------------------------------------------------
# Balkuppslagning
# ---------------------------------------------------------------------------

def test_balk_ger_deklarerade_varden_ur_eta():
    """H300 med OSB-liv, ETA tab. 11."""
    b = M.balk("H300")
    assert (b.serie, b.liv, b.h) == ("H", "osb", 300)
    assert (b.M_k, b.EI, b.V_k, b.GA) == (12.7, 929, 20.5, 2499)
    assert (b.N_ck, b.N_tk) == (116.2, 92.0)


def test_balk_med_spanskiveliv():
    """H300s, ETA tab. 12. Hogre V_k men lagre EI an OSB-varianten."""
    osb, span = M.balk("H300"), M.balk("H300s")
    assert span.liv == "spanskiva"
    assert span.V_k > osb.V_k          # 23.1 mot 20.5
    assert span.EI < osb.EI            # 916 mot 929


def test_geometrin_harleds_ur_serien():
    """
    h_liv = h - 2*h_flans och c_flans = h - h_flans. For H300 blir det
    206 och 253 mm, vilket ar precis handbokens matt pa s. 288.
    """
    b = M.balk("H300")
    assert (b.h_flans, b.b_flans, b.t_liv) == (47.0, 47.0, 10.0)
    assert b.h_liv == 206.0
    assert b.c_flans == 253.0


def test_flansbredden_skiljer_serierna():
    """H 47, HM 60, HI 70, HB 97 mm flansbredd."""
    bredder = {n: M.balk(f"{n}300").b_flans for n in ("H", "HM", "HI", "HB")}
    assert bredder == {"H": 47.0, "HM": 60.0, "HI": 70.0, "HB": 97.0}


def test_okand_balk_ger_hjalpsamt_fel():
    with pytest.raises(KeyError, match="finns inte i balkbiblioteket"):
        M.balk("H999")


def test_biblioteket_innehaller_72_balkar():
    assert len(M.balknamn()) == 72
    assert len(M.balknamn(liv="osb")) == 36
    assert len(M.balknamn(serie="HB")) == 18


def test_filtrering_pa_serie_och_liv():
    namn = M.balknamn(liv="spanskiva", serie="HI")
    assert len(namn) == 9
    assert all(n.startswith("HI") and n.endswith("s") for n in namn)


def test_balkar_kommer_sorterade_pa_hojd():
    hojder = [b.h for b in M.balkar(liv="osb", serie="H")]
    assert hojder == sorted(hojder)


# ---------------------------------------------------------------------------
# Dragkapaciteten som saknas i ETA:n
# ---------------------------------------------------------------------------

def test_hb_med_osb_liv_vagrar_lamna_ut_dragkapacitet():
    """
    docs/ERRATA.md punkt 4. Att lasa N_tk pa en HB-balk med OSB-liv ska ge
    ett fel som forklarar varfor och pekar pa alternativen -- inte ett tal
    som rakar vara momentkapaciteten.
    """
    b = M.balk("HB300")
    assert not b.har_dragkapacitet
    with pytest.raises(ValueError, match="ERRATA"):
        _ = b.N_tk
    # men tryckkapaciteten ar opaverkad och ska ga att lasa
    assert b.N_ck == 229.0


def test_spanskivevarianten_av_hb_har_dragkapacitet():
    b = M.balk("HB300s")
    assert b.har_dragkapacitet
    assert b.N_tk == 177.0


def test_alla_ovriga_balkar_har_dragkapacitet():
    utan = [b.namn for b in M.balkar() if not b.har_dragkapacitet]
    assert utan == [f"HB{h}" for h in
                    (200, 220, 240, 250, 300, 350, 400, 450, 500)]


# ---------------------------------------------------------------------------
# Axialstyvhet, den harledda storheten
# ---------------------------------------------------------------------------

def test_EA_harleds_ur_flans_och_liv():
    """
    EA = E_flans*A_flans + E_liv*A_liv. For H300 med C30+-flansar:
    13000 * 2*47*47 + 3800 * 10*206 = 57.4e6 + 7.8e6 N = ca 65 200 kN.
    """
    b = M.balk("H300")
    assert b.A_flans == 2 * 47 * 47
    assert b.A_liv == 10 * 206
    EA = b.EA()
    assert EA == pytest.approx((13000 * 4418 + 3800 * 2060) / 1000, rel=1e-9)
    assert 60_000 < EA < 70_000


def test_flansarna_dominerar_axialstyvheten():
    """
    Livets bidrag ar knappt 12 % for en H300, vilket ar varfor osakerheten
    i E_liv inte spelar stor roll. Testet gor beroendet synligt.
    """
    b = M.balk("H300")
    E_flans = M.flanskvaliteter()["C30plus"]["E_f"]
    andel_flans = E_flans * b.A_flans / (b.EA() * 1000)
    assert 0.85 < andel_flans < 0.90


def test_EA_ar_hogre_an_den_gamla_platshallaren():
    """
    Den tidigare hardkodade platshallaren var 42 000 kN for alla balkar.
    Den harledda axialstyvheten ar avsevart hogre, precis som EI visade
    sig vara 22-29 % hogre an sin platshallare.
    """
    assert M.balk("H300").EA() > 42_000


# ---------------------------------------------------------------------------
# k_mod: de tre olika serierna far inte blandas
# ---------------------------------------------------------------------------

def test_kmod_bojning_ur_eta_tabell_17():
    assert M.k_mod_bojning(1, "medel") == 0.80
    assert M.k_mod_bojning(2, "medel") == 0.80      # samma i bada klasserna
    assert M.k_mod_bojning(1, "permanent") == 0.60


def test_kmod_tvarkraft_ar_lagre_och_beror_pa_livmaterialet():
    """
    ETA tab. 17. Vid medellang last i klimatklass 1: 0,70 for OSB-liv och
    0,65 for spanskiveliv -- inte bojningens 0,80.
    """
    assert M.k_mod_tvarkraft("osb", 1, "medel") == 0.70
    assert M.k_mod_tvarkraft("spanskiva", 1, "medel") == 0.65
    assert M.k_mod_tvarkraft("osb", 2, "medel") == 0.55
    assert M.k_mod_tvarkraft("spanskiva", 2, "medel") == 0.45

    for liv in ("osb", "spanskiva"):
        for kk in (1, 2):
            for v in M.VARAKTIGHETER:
                assert M.k_mod_tvarkraft(liv, kk, v) <= M.k_mod_bojning(kk, v)


def test_kmod_skiva_ar_en_egen_serie():
    """
    Skivmaterial har k_mod ur EC5 tab. 3.1. Plywood har 0,80 vid medellang
    last i klimatklass 1, OSB 0,70 och P5 0,65.
    """
    assert M.k_mod_skiva("plywood_handbok", 1, "medel") == 0.80
    assert M.k_mod_skiva("osb3", 1, "medel") == 0.70
    assert M.k_mod_skiva("p5", 1, "medel") == 0.65


def test_kdef_delas_i_bojning_och_skjuvning():
    """
    ETA tab. 18. Skjuvdeformationen kryper vasentligt mer, sa nedbojningen
    maste raknas i tva delar.
    """
    assert M.k_def_bojning(1) == 0.60
    assert M.k_def_bojning(2) == 0.80
    assert M.k_def_skjuvning("osb", 1) == 1.50
    assert M.k_def_skjuvning("spanskiva", 1) == 2.25
    assert M.k_def_skjuvning("osb", 2) == 2.25
    assert M.k_def_skjuvning("spanskiva", 2) == 3.00


def test_ogiltig_klimatklass_avvisas():
    """ETA avsn. 2 begransar produkten till klimatklass 1 och 2."""
    for kk in (0, 3, 4):
        with pytest.raises(ValueError, match="klimatklass"):
            M.k_mod_bojning(kk, "medel")


def test_ogiltig_lastvaraktighet_avvisas():
    with pytest.raises(ValueError, match="lastvaraktighet"):
        M.k_mod_bojning(1, "ganska lang")


# ---------------------------------------------------------------------------
# Skivuppslagning
# ---------------------------------------------------------------------------

def test_skiva_loser_upp_tjockleksintervallet():
    """18 mm OSB/3 ska ge vardena for intervallet >10-18."""
    s = M.skiva("osb3", 18.0)
    assert s.anisotrop
    assert s.bojhallfasthet() == 16.4
    assert s.draghallfasthet() == 9.4
    assert s.tryckhallfasthet() == 15.4
    assert s.skivskjuvhallfasthet() == 6.8


def test_skiva_p5_ar_isotrop_i_planet():
    """Spanskiva har inga riktningssuffix. 18 mm ger intervallet >10-18."""
    s = M.skiva("p5", 18.0)
    assert not s.anisotrop
    assert s.bojhallfasthet() == 13.3
    assert s.draghallfasthet() == 8.5
    assert s.skivskjuvhallfasthet() == 6.5


def test_tjockare_skiva_ger_lagre_hallfasthet():
    assert M.skiva("osb3", 22.0).bojhallfasthet() < \
        M.skiva("osb3", 18.0).bojhallfasthet()


def test_plywood_kraver_exakt_18_mm():
    """
    Plywoodposten ar en enda tjocklek, inte en tabell. Uppslagning pa nagot
    annat ska faila -- EN 12369-2 ger inte generiska plywoodvarden.
    """
    assert M.skiva("plywood_handbok", 18.0).bojhallfasthet() == 22.5
    with pytest.raises(ValueError, match="Giltiga intervall"):
        M.skiva("plywood_handbok", 15.0)


def test_tjocklek_utanfor_tabellen_ger_hjalpsamt_fel():
    with pytest.raises(ValueError, match="Giltiga intervall"):
        M.skiva("osb3", 40.0)


def test_plywood_ar_markt_for_dop_kontroll():
    assert M.skiva("plywood_handbok", 18.0).kontrollera_mot_dop
    assert not M.skiva("osb3", 18.0).kontrollera_mot_dop


def test_densitet_finns_bara_dar_den_behovs():
    """
    rho_k behovs for halkantshallfastheten i plywood, ekv. 8.20. For OSB och
    spanskiva raknas den ur tjockleken, ekv. 8.22, sa EN 12369-1 anger
    ingen densitet -- och da ska uppslagningen forklara det, inte gissa.
    """
    assert M.skiva("plywood_handbok", 18.0).rho_k == 410.0
    with pytest.raises(ValueError, match="ekv. 8.22"):
        _ = M.skiva("osb3", 18.0).rho_k


def test_dimensionerande_skivbojning_ar_i_planet():
    """[metod] i skivor.toml. Se motiveringen dar."""
    assert M.skivbojning_dimensionerande() == "i_planet"


# ---------------------------------------------------------------------------
# Forbindaruppslagning
# ---------------------------------------------------------------------------

def test_forbindare_ger_ec5_objekt():
    f = M.forbindare("ankarspik_2_5x50")
    assert (f.d, f.langd, f.typ) == (2.5, 50.0, "rillad")
    assert f.f_u == 600.0


def test_okand_forbindare_ger_hjalpsamt_fel():
    with pytest.raises(KeyError, match="finns inte i förbindarbiblioteket"):
        M.forbindare("spik_9x9")


def test_biblioteken_ar_inte_tomma():
    assert len(M.forbindarnamn()) >= 5
    assert set(M.skivnamn()) >= {"osb3", "p5", "plywood_handbok"}
    assert set(M.flanskvaliteter()) == {"C30plus", "C24plus", "C18"}


def test_gamma_M_for_forband():
    assert M.GAMMA_M_FORBAND == 1.30
